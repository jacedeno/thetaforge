"""Options structure selection.

Maps a directional signal to a defined-risk credit spread:
LONG -> put credit spread (sell a ~25-delta put, buy a put one width lower).

Two details matter more than they look:

* **Width scales with the underlying.** A fixed $5 width is 18% of a $28 stock
  and 0.4% of a $1,250 one. The target width is a fraction of spot, clamped,
  and then snapped to whatever strikes the chain actually lists.
* **Liquidity is judged in relative *or* absolute terms.** A $0.15 contract
  quoted 0.10/0.20 is 67% wide but only six cents away from the mid — perfectly
  tradable. A $10 contract quoted 25% wide is $2.50 of slippage. Requiring both
  tests to pass rejects nearly every equity chain; requiring either one keeps
  the judgment closer to how a trader reads a quote.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import OptionChainRequest

from agent.config import RiskConfig, StrategyConfig
from agent.execution.monitor import occ_root


@dataclass(frozen=True)
class SpreadCandidate:
    underlying: str
    short_symbol: str
    long_symbol: str
    short_strike: float
    long_strike: float
    expiration: date
    short_delta: float
    credit_mid: float           # positive = credit collected per spread
    width: float

    @property
    def max_risk_per_spread(self) -> float:
        return (self.width - self.credit_mid) * 100


def target_width(spot: float, strategy: StrategyConfig) -> float:
    """Width in dollars, scaled to the underlying and clamped."""
    return min(
        max(spot * strategy.spread_width_pct, strategy.spread_width_min_usd),
        strategy.spread_width_max_usd,
    )


def _mid(quote) -> float | None:
    if quote is None or quote.bid_price is None or quote.ask_price is None:
        return None
    if quote.bid_price <= 0 or quote.ask_price <= 0:
        return None
    if quote.ask_price < quote.bid_price:
        # A crossed quote is a stale or bogus tick. Its "mid" looks plausible
        # and its negative spread passes every width test unconditionally —
        # one bad tick would defeat the credit and liquidity gates at once.
        return None
    return (quote.bid_price + quote.ask_price) / 2


def is_tradable(quote, risk: RiskConfig, min_mid: float = 0.0) -> bool:
    """Tight enough relatively, or tight enough absolutely.

    `min_mid` gates the absolute branch: it exists for cheap-but-real
    contracts, not for penny dust whose 0.01/0.10 quote is "six cents from
    a mid" that is itself noise. Callers set it for the short leg; the
    protective wing may be legitimately cheap.
    """
    mid = _mid(quote)
    if mid is None:
        return False
    spread = quote.ask_price - quote.bid_price
    if (spread / mid) <= risk.max_bid_ask_width_pct:
        return True
    return spread <= risk.max_bid_ask_width_usd and mid >= min_mid


def parse_strike(symbol: str, root: str) -> tuple[date, float]:
    # OCC symbols use the dotted-class-stripped root (BRK.B -> BRKB) —
    # slicing the ticker's own length crashed the scanner on 2026-08-27.
    core = symbol[len(occ_root(root)):]
    exp = date(2000 + int(core[0:2]), int(core[2:4]), int(core[4:6]))
    return exp, int(core[7:15]) / 1000


def chain_request(
    underlying: str, spot: float, strategy: StrategyConfig, today: date
) -> OptionChainRequest:
    """The chain window the selector scans — shared with diagnostics."""
    width = target_width(spot, strategy)
    # The lower bound must leave room for the long leg beneath the short strike,
    # or the partner contract falls outside the window we ask for.
    return OptionChainRequest(
        underlying_symbol=underlying,
        type="put",
        expiration_date_gte=today + timedelta(days=strategy.min_dte),
        expiration_date_lte=today + timedelta(days=strategy.max_dte),
        strike_price_gte=spot * 0.80 - width,
        strike_price_lte=spot,
    )


def _trace_candidates(chain, underlying, width, strategy, risk):
    """Walk every short-strike candidate and yield its outcome.

    The selector keeps the accepted candidates; scripts/diagnose_trade.py
    prints every yield, reject reasons included — same code, no logic drift.
    """
    by_key: dict[tuple[date, float], tuple[str, object]] = {}
    for symbol, snap in chain.items():
        by_key[parse_strike(symbol, underlying)] = (symbol, snap)

    for (exp, strike), (symbol, snap) in sorted(by_key.items()):
        greeks = getattr(snap, "greeks", None)
        quote = getattr(snap, "latest_quote", None)
        t = {
            "symbol": symbol, "expiration": exp, "strike": strike,
            "delta": None, "mid": _mid(quote), "credit": None, "width": None,
            "reject": None, "candidate": None,
        }
        if greeks is None or greeks.delta is None:
            t["reject"] = "no greeks"
            yield t
            continue
        # Only sell strikes inside the intended delta band. Taking whatever the
        # chain offers drifts the short leg toward the money, which is a
        # different trade than the one this strategy is built on.
        delta = abs(greeks.delta)
        t["delta"] = delta
        if not (strategy.min_short_delta <= delta <= strategy.max_short_delta):
            t["reject"] = f"delta {delta:.2f} outside band"
            yield t
            continue
        if not is_tradable(quote, risk, min_mid=risk.min_mid_for_abs_width):
            t["reject"] = "short quote not tradable"
            yield t
            continue

        # Snap the long leg to the listed strike closest to the target width.
        partners = [
            (abs((strike - k) - width), k)
            for (e, k) in by_key
            if e == exp and k < strike
        ]
        if not partners:
            t["reject"] = "no long strike below"
            yield t
            continue
        _, long_strike = min(partners)
        long_symbol, long_snap = by_key[(exp, long_strike)]
        long_quote = getattr(long_snap, "latest_quote", None)
        if not is_tradable(long_quote, risk):
            t["reject"] = "long quote not tradable"
            yield t
            continue

        credit = _mid(quote) - _mid(long_quote)
        actual_width = strike - long_strike
        t["credit"], t["width"] = round(credit, 2), actual_width
        if credit <= 0 or credit >= actual_width:
            t["reject"] = f"credit {credit:.2f} outside (0, width)"
            yield t
            continue
        # Thin premium is not worth the defined risk behind it.
        if credit < strategy.min_credit_usd:
            t["reject"] = f"credit {credit:.2f} below floor"
            yield t
            continue
        if credit / actual_width < strategy.min_credit_to_width:
            t["reject"] = f"credit/width {credit / actual_width:.2f} below floor"
            yield t
            continue

        t["candidate"] = SpreadCandidate(
            underlying=underlying,
            short_symbol=symbol,
            long_symbol=long_symbol,
            short_strike=strike,
            long_strike=long_strike,
            expiration=exp,
            short_delta=delta,
            credit_mid=round(credit, 2),
            width=round(actual_width, 2),
        )
        yield t


def build_put_credit_spread(
    client: OptionHistoricalDataClient,
    underlying: str,
    spot: float,
    strategy: StrategyConfig,
    risk: RiskConfig,
    today: date | None = None,
    oi_lookup=None,
) -> SpreadCandidate | None:
    """Short strike nearest the target delta; long leg nearest the target width below it.

    `oi_lookup(symbol) -> int | None` enforces min_open_interest per leg.
    Open interest lives in the trading API's contracts endpoint, not the
    chain snapshot, so it is verified on the best few candidates only —
    two lookups each. Unknown OI rejects; it never passes by default.
    """
    today = today or date.today()
    width = target_width(spot, strategy)
    chain = client.get_option_chain(chain_request(underlying, spot, strategy, today))
    if not chain:
        return None

    candidates = [
        t["candidate"]
        for t in _trace_candidates(chain, underlying, width, strategy, risk)
        if t["candidate"] is not None
    ]
    candidates.sort(key=lambda c: abs(c.short_delta - strategy.target_short_delta))
    if oi_lookup is None:
        return candidates[0] if candidates else None
    for cand in candidates[:5]:
        ois = [oi_lookup(s) for s in (cand.short_symbol, cand.long_symbol)]
        if all(oi is not None and oi >= risk.min_open_interest for oi in ois):
            return cand
    return None
