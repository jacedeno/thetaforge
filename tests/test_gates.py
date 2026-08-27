from agent.config import RiskConfig
from agent.options.selector import SpreadCandidate
from agent.risk.gates import check_all, position_qty
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


def test_position_qty_respects_risk_budget():
    # budget = equity x max_risk_per_position_pct; max risk/spread = $400
    # (tied to the config so a sizing retune can't silently rot this test)
    expected = int(100_000 * RISK.max_risk_per_position_pct // 400)
    assert position_qty(make_candidate(), 100_000, RISK) == expected
    assert expected >= 1


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
    r = check_all(make_candidate(), 5, 100_000, 50_000, RISK.max_open_positions, set(), RISK)
    assert not r.passed and "max open positions" in r.reason


def test_veto_insufficient_bp():
    r = check_all(make_candidate(), 5, 100_000, 1_000, 0, set(), RISK)
    assert not r.passed and "buying power" in r.reason


def test_veto_zero_qty():
    r = check_all(make_candidate(), 0, 100_000, 50_000, 0, set(), RISK)
    assert not r.passed
