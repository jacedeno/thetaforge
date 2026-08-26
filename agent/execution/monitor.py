"""Position monitor — the exit half of the trade lifecycle.

Reconstructs open credit spreads from broker positions (short + long put
on the same underlying and expiration), prices the cost to close from
live quotes, and applies the exit rules:

    profit target  — close when cost-to-close <= (1 - profit_target_pct) x credit
    stop           — close when loss >= stop_loss_credit_mult x credit
    time stop      — close at <= 2 DTE, never carry into expiration

Both credit-relative rules are floored by min_exit_band_usd: a credit small
enough that no floored profitable exit exists is HELD to the time stop —
closing it means crossing a bid/ask wider than the position is worth.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from agent.config import StrategyConfig

TIME_STOP_DTE = 2

_OCC = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")


@dataclass(frozen=True)
class OccContract:
    root: str
    expiration: date
    kind: str       # "C" or "P"
    strike: float


def parse_occ(symbol: str) -> OccContract:
    m = _OCC.match(symbol)
    if not m:
        raise ValueError(f"not an OCC option symbol: {symbol}")
    root, ymd, kind, strike = m.groups()
    return OccContract(
        root=root,
        expiration=date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6])),
        kind=kind,
        strike=int(strike) / 1000,
    )


@dataclass(frozen=True)
class OpenSpread:
    underlying: str
    short_symbol: str
    long_symbol: str
    qty: int
    entry_credit: float      # per spread
    expiration: date
    width: float             # short strike - long strike
    credit_source: str = "avg_entry_price"   # or "journal" (fill-derived)


@dataclass(frozen=True)
class ExitDecision:
    action: str              # "HOLD" or "CLOSE"
    reason: str
    cost_to_close: float | None = None
    flag: str | None = None  # "unmanageable" | "non_positive_credit"


def reconstruct_spreads(
    positions: list, credits: dict[tuple[str, str], float] | None = None
) -> list[OpenSpread]:
    """Pair short and long option legs into credit spreads.

    Expects broker position objects with .symbol, .qty (negative = short),
    and .avg_entry_price. Legs pair on (root, expiration, kind); unpaired
    legs are ignored (never traded by this agent).

    `credits` maps (short_symbol, long_symbol) -> the journal's fill-derived
    entry credit. Positions vanish the moment a trade closes but fills are
    permanent, so the journal wins whenever it has the pair; avg_entry_price
    is the fallback, not the source of truth.
    """
    shorts, longs = {}, {}
    for p in positions:
        c = parse_occ(p.symbol)
        key = (c.root, c.expiration, c.kind)
        if float(p.qty) < 0:
            shorts[key] = (p, c)
        else:
            longs[key] = (p, c)

    spreads = []
    for key, (sp, sc) in shorts.items():
        if key not in longs:
            continue
        lp, lc = longs[key]
        journal_credit = (credits or {}).get((sp.symbol, lp.symbol))
        if journal_credit is not None:
            entry_credit, credit_source = round(float(journal_credit), 2), "journal"
        else:
            entry_credit = round(float(sp.avg_entry_price) - float(lp.avg_entry_price), 2)
            credit_source = "avg_entry_price"
        spreads.append(
            OpenSpread(
                underlying=sc.root,
                short_symbol=sp.symbol,
                long_symbol=lp.symbol,
                qty=int(abs(float(sp.qty))),
                entry_credit=entry_credit,
                expiration=sc.expiration,
                width=round(sc.strike - lc.strike, 2),
                credit_source=credit_source,
            )
        )
    return spreads


def evaluate_exit(
    spread: OpenSpread,
    short_mid: float,
    long_mid: float,
    strategy: StrategyConfig,
    today: date | None = None,
) -> ExitDecision:
    """Apply exit rules in precedence order: time stop > stop > profit target.

    The credit-relative thresholds are floored by min_exit_band_usd so quote
    flicker on a tiny credit can never satisfy an exit rule by itself.
    """
    today = today or date.today()
    cost = round(short_mid - long_mid, 2)   # debit to buy the spread back

    dte = (spread.expiration - today).days
    if dte <= TIME_STOP_DTE:
        return ExitDecision("CLOSE", f"time stop ({dte} DTE)", cost)

    credit = spread.entry_credit
    if credit <= 0:
        # A zero or negative reconstructed credit (assigned leg, partial fill)
        # would make the stop test trivially true on the next pass.
        return ExitDecision(
            "HOLD", f"non-positive credit {credit:.2f} — deferring to time stop",
            cost, flag="non_positive_credit",
        )

    loss = cost - credit
    stop_at = max(strategy.stop_loss_credit_mult * credit, strategy.min_exit_band_usd)
    if loss >= stop_at:
        return ExitDecision("CLOSE", f"stop loss (loss {loss:.2f} >= {stop_at:.2f})", cost)

    target_cost = round(credit - max(strategy.profit_target_pct * credit, strategy.min_exit_band_usd), 2)
    if target_cost < 0:
        # No floored profitable exit exists: closing means crossing a bid/ask
        # wider than the position is worth. Risk is defined and collateralized;
        # the time stop retires it for free. Hold, loudly.
        return ExitDecision(
            "HOLD", f"unmanageable credit {credit:.2f} — holding to time stop",
            cost, flag="unmanageable",
        )
    if cost <= target_cost:
        return ExitDecision("CLOSE", f"profit target (cost {cost:.2f} <= {target_cost:.2f})", cost)

    return ExitDecision(
        "HOLD", f"dte={dte} cost={cost:.2f} credit={credit:.2f} ({spread.credit_source})", cost
    )


def exit_limit(cost: float, width: float, strategy: StrategyConfig) -> float:
    """Closing limit: cross the spread a little to actually fill.

    Floored so a near-zero cost cannot produce a sub-penny limit, never
    negative (an inverted quote pair must not flip into a debit via abs()
    downstream), and capped at the width — no rational close pays more than
    the spread is ever worth.
    """
    pad = max(strategy.min_exit_limit_usd, round(0.02 * max(cost, 0.0), 2))
    return round(min(max(cost, 0.0) + pad, width), 2)
