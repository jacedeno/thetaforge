"""Position monitor — the exit half of the trade lifecycle.

Reconstructs open credit spreads from broker positions (short + long put
on the same underlying and expiration), prices the cost to close from
live quotes, and applies the exit rules:

    profit target  — close when cost-to-close <= (1 - profit_target_pct) x credit
    stop           — close when loss >= stop_loss_credit_mult x credit
    time stop      — close at <= 2 DTE, never carry into expiration
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
    entry_credit: float      # per spread, from avg entry prices
    expiration: date


@dataclass(frozen=True)
class ExitDecision:
    action: str              # "HOLD" or "CLOSE"
    reason: str
    cost_to_close: float | None = None


def reconstruct_spreads(positions: list) -> list[OpenSpread]:
    """Pair short and long option legs into credit spreads.

    Expects broker position objects with .symbol, .qty (negative = short),
    and .avg_entry_price. Legs pair on (root, expiration, kind); unpaired
    legs are ignored (never traded by this agent).
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
        spreads.append(
            OpenSpread(
                underlying=sc.root,
                short_symbol=sp.symbol,
                long_symbol=lp.symbol,
                qty=int(abs(float(sp.qty))),
                entry_credit=round(
                    float(sp.avg_entry_price) - float(lp.avg_entry_price), 2
                ),
                expiration=sc.expiration,
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
    """Apply exit rules in precedence order: time stop > stop > profit target."""
    today = today or date.today()
    cost = round(short_mid - long_mid, 2)   # debit to buy the spread back

    dte = (spread.expiration - today).days
    if dte <= TIME_STOP_DTE:
        return ExitDecision("CLOSE", f"time stop ({dte} DTE)", cost)

    loss = cost - spread.entry_credit
    if loss >= strategy.stop_loss_credit_mult * spread.entry_credit:
        return ExitDecision("CLOSE", f"stop loss (loss {loss:.2f} >= {strategy.stop_loss_credit_mult}x credit)", cost)

    if cost <= spread.entry_credit * (1 - strategy.profit_target_pct):
        return ExitDecision("CLOSE", f"profit target (cost {cost:.2f} <= {1 - strategy.profit_target_pct:.0%} of credit)", cost)

    return ExitDecision("HOLD", f"dte={dte} cost={cost:.2f} credit={spread.entry_credit:.2f}", cost)
