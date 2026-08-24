"""Options structure selection.

Maps a directional signal to a defined-risk credit spread:
LONG -> put credit spread (sell ~25-delta put, buy a put one width lower).

Chain data comes from Alpaca's options snapshots (quotes + greeks).
Every candidate passes liquidity gates before it is returned.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import OptionChainRequest

from agent.config import RiskConfig, StrategyConfig


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


def _mid(quote) -> float | None:
    if quote is None or quote.bid_price is None or quote.ask_price is None:
        return None
    if quote.bid_price <= 0 or quote.ask_price <= 0:
        return None
    return (quote.bid_price + quote.ask_price) / 2


def _spread_pct(quote) -> float | None:
    m = _mid(quote)
    if m is None or m == 0:
        return None
    return (quote.ask_price - quote.bid_price) / m


def build_put_credit_spread(
    client: OptionHistoricalDataClient,
    underlying: str,
    spot: float,
    strategy: StrategyConfig,
    risk: RiskConfig,
    today: date | None = None,
) -> SpreadCandidate | None:
    """Pick short strike nearest target delta within the DTE window, long leg one width below."""
    today = today or date.today()
    req = OptionChainRequest(
        underlying_symbol=underlying,
        type="put",
        expiration_date_gte=today + timedelta(days=strategy.min_dte),
        expiration_date_lte=today + timedelta(days=strategy.max_dte),
        strike_price_gte=spot * 0.85,
        strike_price_lte=spot * 1.0,
    )
    chain = client.get_option_chain(req)
    if not chain:
        return None

    # Index snapshots by (expiration, strike) parsed from the OCC symbol.
    def parse(symbol: str) -> tuple[date, float]:
        core = symbol[len(underlying):]
        exp = date(2000 + int(core[0:2]), int(core[2:4]), int(core[4:6]))
        strike = int(core[7:15]) / 1000
        return exp, strike

    by_key: dict[tuple[date, float], tuple[str, object]] = {}
    for symbol, snap in chain.items():
        by_key[parse(symbol)] = (symbol, snap)

    # Short-leg candidates: delta near target, liquidity gates pass.
    best = None
    for (exp, strike), (symbol, snap) in by_key.items():
        greeks = getattr(snap, "greeks", None)
        quote = getattr(snap, "latest_quote", None)
        if greeks is None or greeks.delta is None or quote is None:
            continue
        delta = abs(greeks.delta)
        if _spread_pct(quote) is None or _spread_pct(quote) > risk.max_bid_ask_width_pct:
            continue
        long_key = (exp, strike - strategy.spread_width_usd)
        if long_key not in by_key:
            continue
        long_symbol, long_snap = by_key[long_key]
        long_quote = getattr(long_snap, "latest_quote", None)
        if long_quote is None or _spread_pct(long_quote) is None:
            continue
        if _spread_pct(long_quote) > risk.max_bid_ask_width_pct:
            continue
        credit = _mid(quote) - _mid(long_quote)
        if credit <= 0:
            continue
        score = abs(delta - strategy.target_short_delta)
        if best is None or score < best[0]:
            best = (
                score,
                SpreadCandidate(
                    underlying=underlying,
                    short_symbol=symbol,
                    long_symbol=long_symbol,
                    short_strike=strike,
                    long_strike=strike - strategy.spread_width_usd,
                    expiration=exp,
                    short_delta=delta,
                    credit_mid=round(credit, 2),
                    width=strategy.spread_width_usd,
                ),
            )
    return best[1] if best else None
