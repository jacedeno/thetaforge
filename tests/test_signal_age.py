"""Stale signal bars are treated exactly like a down feed.

Regression for 2026-08-28: with the 15-min SIP delay plus the RTH filter,
scans between 8:30 and ~8:50 CT saw the PRIOR session's 14:55 CT bar as the
latest completed bar, and six of its signals fired — stopped only by the
option-liquidity gates downstream. Protection by luck is not protection.
"""

from datetime import datetime, timedelta, timezone

from agent.config import StrategyConfig
from agent.signals.ml30 import BAR_SPAN_S, Signal, bar_age_s, split_stale

# Monday 2026-08-31 8:35 CT (9:35 ET) — inside the risky opening window.
NOW = datetime(2026, 8, 31, 13, 35, tzinfo=timezone.utc)


def _sig(bar_time: datetime) -> Signal:
    return Signal(symbol="TEST", direction="LONG", close=100.0,
                  sma_slow=99.0, sma_fast=99.5, bar_time=bar_time)


def test_age_is_measured_from_bar_close_not_label():
    # A 5-minute bar labeled 10 minutes ago closed 5 minutes ago.
    bar = NOW - timedelta(minutes=10)
    assert bar_age_s(bar, NOW) == 5 * 60


def test_yesterdays_close_bar_is_stale():
    # The exact 2026-08-28 scenario: prior session's last RTH bar
    # (14:55 CT = 19:55 UTC Friday) showing up as "latest" on Monday.
    bar = datetime(2026, 8, 28, 19, 55, tzinfo=timezone.utc)
    fresh, stale = split_stale([_sig(bar)], StrategyConfig().max_signal_bar_age_s, NOW)
    assert fresh == []
    assert len(stale) == 1
    assert stale[0][1] > StrategyConfig().max_signal_bar_age_s


def test_normal_sip_delay_passes():
    # Mid-session with the free-tier delay: latest completed bar closed
    # ~20 minutes ago. That is the normal tape, not a failure.
    bar = NOW - timedelta(minutes=25)
    fresh, stale = split_stale([_sig(bar)], StrategyConfig().max_signal_bar_age_s, NOW)
    assert len(fresh) == 1
    assert stale == []


def test_boundary_age_exactly_at_max_passes():
    cfg = StrategyConfig()
    bar = NOW - timedelta(seconds=cfg.max_signal_bar_age_s + BAR_SPAN_S)
    fresh, stale = split_stale([_sig(bar)], cfg.max_signal_bar_age_s, NOW)
    assert len(fresh) == 1
    assert stale == []


def test_mixed_batch_keeps_only_fresh():
    fresh_bar = NOW - timedelta(minutes=10)
    stale_bar = NOW - timedelta(hours=18)
    fresh, stale = split_stale(
        [_sig(stale_bar), _sig(fresh_bar)],
        StrategyConfig().max_signal_bar_age_s, NOW,
    )
    assert [s.bar_time for s in fresh] == [fresh_bar]
    assert [s.bar_time for s, _ in stale] == [stale_bar]
