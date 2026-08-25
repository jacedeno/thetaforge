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
    return (quote.bid_price + quote.ask_price) / 2


def is_tradable(quote, risk: RiskConfig) -> bool:
    """Tight enough relatively, or tight enough absolutely."""
    mid = _mid(quote)
    if mid is None:
        return False
    spread = quote.ask_price - quote.bid_price
    return (spread / mid) <= risk.max_bid_ask_width_pct or spread <= risk.max_bid_ask_width_usd


def parse_strike(symbol: str, root: str) -> tuple[date, float]:
    core = symbol[len(root):]
    exp = date(2000 + int(core[0:2]), int(core[2:4]), int(core[4:6]))
    return exp, int(core[7:15]) / 1000


def build_put_credit_spread(
    client: OptionHistoricalDataClient,
    underlying: str,
    spot: float,
    strategy: StrategyConfig,
    risk: RiskConfig,
    today: date | None = None,
) -> SpreadCandidate | None:
    """Short strike nearest the target delta; long leg nearest the target width below it."""
    today = today or date.today()
    width = target_width(spot, strategy)

    # The lower bound must leave room for the long leg beneath the short strike,
    # or the partner contract falls outside the window we ask for.
    req = OptionChainRequest(
        underlying_symbol=underlying,
        type="put",
        expiration_date_gte=today + timedelta(days=strategy.min_dte),
        expiration_date_lte=today + timedelta(days=strategy.max_dte),
        strike_price_gte=spot * 0.80 - width,
        strike_price_lte=spot,
    )
    chain = client.get_option_chain(req)
    if not chain:
        return None

    by_key: dict[tuple[date, float], tuple[str, object]] = {}
    for symbol, snap in chain.items():
        by_key[parse_strike(symbol, underlying)] = (symbol, snap)

    best = None
    for (exp, strike), (symbol, snap) in by_key.items():
        greeks = getattr(snap, "greeks", None)
        quote = getattr(snap, "latest_quote", None)
        if greeks is None or greeks.delta is None:
            continue
        # Only sell strikes inside the intended delta band. Taking whatever the
        # chain offers drifts the short leg toward the money, which is a
        # different trade than the one this strategy is built on.
        delta = abs(greeks.delta)
        if not (strategy.min_short_delta <= delta <= strategy.max_short_delta):
            continue
        if not is_tradable(quote, risk):
            continue

        # Snap the long leg to the listed strike closest to the target width.
        partners = [
            (abs((strike - k) - width), k)
            for (e, k) in by_key
            if e == exp and k < strike
        ]
        if not partners:
            continue
        _, long_strike = min(partners)
        long_symbol, long_snap = by_key[(exp, long_strike)]
        long_quote = getattr(long_snap, "latest_quote", None)
        if not is_tradable(long_quote, risk):
            continue

        credit = _mid(quote) - _mid(long_quote)
        actual_width = strike - long_strike
        if credit <= 0 or credit >= actual_width:
            continue
        # Thin premium is not worth the defined risk behind it.
        if credit < strategy.min_credit_usd:
            continue
        if credit / actual_width < strategy.min_credit_to_width:
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
                    long_strike=long_strike,
                    expiration=exp,
                    short_delta=delta,
                    credit_mid=round(credit, 2),
                    width=round(actual_width, 2),
                ),
            )
    return best[1] if best else None
