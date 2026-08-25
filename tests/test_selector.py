from types import SimpleNamespace

from agent.config import RiskConfig, StrategyConfig
from agent.options.selector import is_tradable, target_width

S, R = StrategyConfig(), RiskConfig()


def q(bid, ask):
    return SimpleNamespace(bid_price=bid, ask_price=ask)


def test_width_scales_with_price():
    assert target_width(28.05, S) == S.spread_width_min_usd      # cheap -> floor
    assert target_width(1251.81, S) == S.spread_width_max_usd    # expensive -> cap
    assert 4.0 < target_width(488.79, S) < 7.0                   # mid -> proportional


def test_tight_relative_quote_passes():
    assert is_tradable(q(4.00, 4.20), R)          # 5% wide


def test_cheap_contract_passes_on_absolute_cents():
    """0.10/0.20 is 67% wide but only six cents from the mid — tradable."""
    assert is_tradable(q(0.12, 0.18), R)


def test_expensive_wide_quote_rejected():
    """25%+ on a $10 contract is real slippage, not a rounding artifact."""
    assert not is_tradable(q(8.00, 12.00), R)


def test_missing_or_zero_quote_rejected():
    assert not is_tradable(None, R)
    assert not is_tradable(q(0, 1.00), R)


def test_delta_band_excludes_at_the_money():
    assert S.min_short_delta <= 0.25 <= S.max_short_delta
    assert 0.42 > S.max_short_delta          # near-ATM strikes are out of band
    assert 0.10 < S.min_short_delta          # far-OTM strikes are out of band


def test_credit_quality_floors_are_set():
    assert S.min_credit_usd > 0
    assert 0 < S.min_credit_to_width < 1
