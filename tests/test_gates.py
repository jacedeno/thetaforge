from agent.config import RiskConfig
from agent.options.selector import SpreadCandidate
from agent.risk.gates import check_all, max_positions, position_qty, position_slot
from datetime import date

RISK = RiskConfig()


def make_candidate(credit=1.00, width=5.0):
    return SpreadCandidate(
        underlying="NVDA",
        short_symbol="NVDA260911P00197500",
        long_symbol="NVDA260911P00192500",
        short_strike=197.5,
        long_strike=192.5,
        expiration=date(2026, 9, 11),
        short_delta=0.25,
        credit_mid=credit,
        width=width,
    )


def test_position_qty_fills_one_slot():
    # slot at $3,000 = $500 growth slot; max risk/spread = $400 -> 1 contract
    # (tied to the config so a sizing retune can't silently rot this test)
    assert position_qty(make_candidate(), 3_000, RISK) == int(
        position_slot(3_000, RISK) // 400
    )
    # mature phase: slot = 10% of equity -> $1,000 at $10k -> 2 contracts
    assert position_qty(make_candidate(), 10_000, RISK) == int(
        10_000 * RISK.slot_mature_pct // 400
    )


def test_ladder_growth_phase():
    # one new position per $500 of equity, slot fixed at $500
    assert max_positions(3_000, RISK) == 6
    assert max_positions(3_499, RISK) == 6
    assert max_positions(3_500, RISK) == 7
    assert max_positions(4_000, RISK) == 8
    assert position_slot(3_000, RISK) == RISK.slot_growth_usd
    assert position_slot(4_999, RISK) == RISK.slot_growth_usd


def test_ladder_meets_mature_phase_without_a_step():
    # at $5,000 the cap of 10 arrives exactly where 10% = $500
    assert max_positions(5_000, RISK) == RISK.slot_cap_positions
    assert position_slot(5_000, RISK) == RISK.slot_growth_usd == 5_000 * RISK.slot_mature_pct


def test_ladder_mature_phase_scales_with_equity():
    assert max_positions(6_000, RISK) == 10
    assert position_slot(6_000, RISK) == 600.0
    assert position_slot(7_000, RISK) == 700.0
    # the $10-wide giants (~$830 collateral) re-enter at ~$8,300
    assert position_slot(8_300, RISK) == 830.0


def test_ladder_steps_down_in_drawdown():
    assert max_positions(2_900, RISK) == 5
    assert max_positions(499, RISK) == 0


def test_all_gates_pass():
    r = check_all(make_candidate(), 5, 100_000, 50_000, 0, set(), RISK)
    assert r.passed


def test_dotted_ticker_duplicate_detected():
    """held carries OCC roots (BRKB); the candidate carries the ticker
    (BRK.B) — without normalization a dotted class double-enters."""
    from dataclasses import replace

    cand = replace(make_candidate(), underlying="BRK.B")
    r = check_all(cand, 5, 100_000, 50_000, 0, {"BRKB"}, RISK)
    assert not r.passed and "already holding" in r.reason


def test_veto_duplicate_underlying():
    r = check_all(make_candidate(), 5, 100_000, 50_000, 1, {"NVDA"}, RISK)
    assert not r.passed and "already holding" in r.reason


def test_veto_max_positions():
    # at $3,000 the ladder allows 6 — the seventh is vetoed
    r = check_all(make_candidate(), 1, 3_000, 3_000, 6, set(), RISK)
    assert not r.passed and "max open positions" in r.reason


def test_veto_insufficient_bp():
    r = check_all(make_candidate(), 5, 100_000, 1_000, 0, set(), RISK)
    assert not r.passed and "buying power" in r.reason


def test_veto_zero_qty():
    r = check_all(make_candidate(), 0, 100_000, 50_000, 0, set(), RISK)
    assert not r.passed
