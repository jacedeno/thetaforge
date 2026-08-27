from datetime import date
from types import SimpleNamespace

from agent.config import RiskConfig, StrategyConfig
from agent.options.selector import _mid, build_put_credit_spread, is_tradable, target_width

S, R = StrategyConfig(), RiskConfig()


def q(bid, ask):
    return SimpleNamespace(bid_price=bid, ask_price=ask)


def snap(delta, bid, ask):
    return SimpleNamespace(greeks=SimpleNamespace(delta=delta), latest_quote=q(bid, ask))


class FakeChainClient:
    def __init__(self, chain):
        self.chain = chain

    def get_option_chain(self, req):
        return self.chain


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


def test_crossed_quote_rejected():
    """bid 1.20 / ask 0.03 passed both branches before 2026-08-26: the
    negative spread satisfies every width test and the mid looks plausible."""
    assert _mid(q(1.20, 0.03)) is None
    assert not is_tradable(q(1.20, 0.03), R)


def test_penny_contract_not_rescued_by_absolute_width():
    """0.01/0.10 is 'nine cents from the mid' — but the mid is noise."""
    assert not is_tradable(q(0.01, 0.10), R, min_mid=R.min_mid_for_abs_width)
    # The default keeps the documented cheap-but-real behavior for wings.
    assert is_tradable(q(0.12, 0.18), R)


# ---- build_put_credit_spread on a fake chain -----------------------------

TODAY = date(2026, 8, 26)


def spy_chain():
    """The validated 2026-09-11 spread from docs/alpaca-notes.md: 749/744."""
    return {
        "SPY260911P00749000": snap(-0.25, 1.24, 1.36),   # mid 1.30
        "SPY260911P00744000": snap(-0.21, 0.48, 0.56),   # mid 0.52 -> credit 0.78
    }


def test_build_put_credit_spread_accepts_a_realistic_25_delta_spread():
    cand = build_put_credit_spread(
        FakeChainClient(spy_chain()), "SPY", 766.0, S, R, today=TODAY,
        oi_lookup=lambda s: 1000,
    )
    assert cand is not None
    assert cand.short_strike == 749.0 and cand.long_strike == 744.0
    assert cand.credit_mid == 0.78


def test_open_interest_below_floor_rejected():
    cand = build_put_credit_spread(
        FakeChainClient(spy_chain()), "SPY", 766.0, S, R, today=TODAY,
        oi_lookup=lambda s: 100,
    )
    assert cand is None


def test_missing_open_interest_rejected():
    """Unknown OI is a rejection, never a pass-by-default."""
    cand = build_put_credit_spread(
        FakeChainClient(spy_chain()), "SPY", 766.0, S, R, today=TODAY,
        oi_lookup=lambda s: None,
    )
    assert cand is None


def test_build_rejects_the_2026_08_26_smoke_test_spread():
    """SPY 700/695 with spot 766: even with bogus in-band greeks and clean
    quotes, the three-cent credit dies at the floor. The selector could never
    have produced the incident's spread."""
    chain = {
        "SPY260911P00700000": snap(-0.24, 0.35, 0.39),   # mid 0.37
        "SPY260911P00695000": snap(-0.20, 0.31, 0.37),   # mid 0.34 -> credit 0.03
    }
    cand = build_put_credit_spread(
        FakeChainClient(chain), "SPY", 766.0, S, R, today=TODAY,
        oi_lookup=lambda s: 1000,
    )
    assert cand is None


def test_build_rejects_crossed_short_quote():
    chain = spy_chain()
    chain["SPY260911P00749000"] = snap(-0.25, 1.36, 0.03)   # crossed
    cand = build_put_credit_spread(
        FakeChainClient(chain), "SPY", 766.0, S, R, today=TODAY,
        oi_lookup=lambda s: 1000,
    )
    assert cand is None


def test_delta_band_excludes_at_the_money():
    assert S.min_short_delta <= 0.25 <= S.max_short_delta
    assert 0.42 > S.max_short_delta          # near-ATM strikes are out of band
    assert 0.10 < S.min_short_delta          # far-OTM strikes are out of band


def test_credit_quality_floors_are_set():
    assert S.min_credit_usd > 0
    assert 0 < S.min_credit_to_width < 1


def test_overextension_ceiling_and_calm_first():
    """The two strongest signals of 2026-08-26 were the day's two worst
    positions — for premium selling, strength measures overextension."""
    from datetime import datetime
    from agent.signals.ml30 import Signal

    def sig(sym, strength):
        # strength = (c/slow-1)+(c/fast-1); build via close/sma choices
        return Signal(symbol=sym, direction="LONG", close=100 * (1 + strength / 2),
                      sma_slow=100, sma_fast=100, bar_time=datetime(2026, 8, 26))

    s_calm, s_mid, s_hot = sig("A", 0.001), sig("B", 0.006), sig("C", 0.030)
    ceiling = StrategyConfig().max_signal_strength
    kept = sorted([x for x in [s_hot, s_mid, s_calm] if x.strength <= ceiling],
                  key=lambda x: x.strength)
    assert [x.symbol for x in kept] == ["A", "B"]      # hot one dropped, calm first


def test_sector_map_covers_universe():
    from agent.signals.ml30 import load_sectors, load_universe

    sectors = load_sectors()
    missing = [s for s in load_universe() if s not in sectors]
    assert not missing, f"symbols without sector: {missing}"
    assert StrategyConfig().max_new_per_sector_per_scan >= 1
