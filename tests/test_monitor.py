from datetime import date
from types import SimpleNamespace

from agent.config import StrategyConfig
from agent.execution.monitor import (
    OpenSpread,
    evaluate_exit,
    exit_limit,
    parse_occ,
    reconstruct_spreads,
)

CFG = StrategyConfig()
TODAY = date(2026, 8, 24)


def make_spread(credit=1.00, exp=date(2026, 9, 11), width=5.0):
    return OpenSpread(
        underlying="NVDA",
        short_symbol="NVDA260911P00197500",
        long_symbol="NVDA260911P00192500",
        qty=5,
        entry_credit=credit,
        expiration=exp,
        width=width,
    )


def test_parse_occ():
    c = parse_occ("NVDA260911P00197500")
    assert c.root == "NVDA"
    assert c.expiration == date(2026, 9, 11)
    assert c.kind == "P"
    assert c.strike == 197.5


def test_hold_when_nothing_triggers():
    d = evaluate_exit(make_spread(), short_mid=1.20, long_mid=0.50, strategy=CFG, today=TODAY)
    assert d.action == "HOLD"


def test_profit_target():
    # cost to close 0.45 <= 50% of 1.00 credit
    d = evaluate_exit(make_spread(), short_mid=0.70, long_mid=0.25, strategy=CFG, today=TODAY)
    assert d.action == "CLOSE"
    assert "profit target" in d.reason


def test_stop_loss():
    # cost 3.10, loss 2.10 >= 2x credit
    d = evaluate_exit(make_spread(), short_mid=3.60, long_mid=0.50, strategy=CFG, today=TODAY)
    assert d.action == "CLOSE"
    assert "stop loss" in d.reason


def test_time_stop_beats_profit_target():
    d = evaluate_exit(
        make_spread(exp=date(2026, 8, 25)), short_mid=0.30, long_mid=0.10,
        strategy=CFG, today=TODAY,
    )
    assert d.action == "CLOSE"
    assert "time stop" in d.reason


def test_reconstruct_pairs_legs():
    positions = [
        SimpleNamespace(symbol="NVDA260911P00197500", qty="-5", avg_entry_price="3.50"),
        SimpleNamespace(symbol="NVDA260911P00192500", qty="5", avg_entry_price="2.40"),
        SimpleNamespace(symbol="AAPL260911P00220000", qty="-2", avg_entry_price="1.80"),  # unpaired
    ]
    spreads = reconstruct_spreads(positions)
    assert len(spreads) == 1
    s = spreads[0]
    assert s.underlying == "NVDA"
    assert s.qty == 5
    assert s.entry_credit == 1.10
    assert s.width == 5.0
    assert s.credit_source == "avg_entry_price"


def test_reconstruct_prefers_journal_credit():
    positions = [
        SimpleNamespace(symbol="NVDA260911P00197500", qty="-5", avg_entry_price="3.50"),
        SimpleNamespace(symbol="NVDA260911P00192500", qty="5", avg_entry_price="2.40"),
    ]
    credits = {("NVDA260911P00197500", "NVDA260911P00192500"): 1.13}
    s = reconstruct_spreads(positions, credits)[0]
    assert s.entry_credit == 1.13
    assert s.credit_source == "journal"


# ---- exit-band floors (the sub-dollar credit regime) ---------------------


def test_penny_credit_does_not_trip_on_noise():
    """A 0.01 credit with two cents of quote flicker used to hit the 2x stop."""
    d = evaluate_exit(make_spread(credit=0.01), short_mid=0.37, long_mid=0.32,
                      strategy=CFG, today=TODAY)
    assert d.action == "HOLD"


def test_exit_band_floor_widens_stop():
    # credit 0.04: relative stop would fire at loss 0.08; the 0.10 floor holds it
    d = evaluate_exit(make_spread(credit=0.04), short_mid=0.42, long_mid=0.30,
                      strategy=CFG, today=TODAY)   # cost 0.12, loss 0.08
    assert d.action == "HOLD"
    d = evaluate_exit(make_spread(credit=0.04), short_mid=0.45, long_mid=0.30,
                      strategy=CFG, today=TODAY)   # cost 0.15, loss 0.11 >= 0.10
    assert d.action == "CLOSE"
    assert "stop loss" in d.reason


def test_exit_band_floor_widens_target():
    # credit 0.15: relative target would fire at cost 0.075; floored target is 0.05
    d = evaluate_exit(make_spread(credit=0.15), short_mid=0.27, long_mid=0.20,
                      strategy=CFG, today=TODAY)   # cost 0.07
    assert d.action == "HOLD"
    d = evaluate_exit(make_spread(credit=0.15), short_mid=0.25, long_mid=0.20,
                      strategy=CFG, today=TODAY)   # cost 0.05 <= 0.05
    assert d.action == "CLOSE"
    assert "profit target" in d.reason


def test_zero_credit_holds():
    """A zero/negative reconstructed credit used to fire the stop instantly."""
    d = evaluate_exit(make_spread(credit=0.0), short_mid=0.30, long_mid=0.30,
                      strategy=CFG, today=TODAY)
    assert d.action == "HOLD"
    assert d.flag == "non_positive_credit"


def test_unmanageable_credit_defers_to_time_stop():
    # Far from expiry: held, flagged — no floored profitable exit exists.
    d = evaluate_exit(make_spread(credit=0.03), short_mid=0.37, long_mid=0.34,
                      strategy=CFG, today=TODAY)
    assert d.action == "HOLD"
    assert d.flag == "unmanageable"
    # At the time stop it still closes — never carried into expiration.
    d = evaluate_exit(make_spread(credit=0.03, exp=date(2026, 8, 25)),
                      short_mid=0.37, long_mid=0.34, strategy=CFG, today=TODAY)
    assert d.action == "CLOSE"
    assert "time stop" in d.reason


def test_exit_limit_has_floor():
    assert exit_limit(0.05, 5.0, CFG) == 0.07     # pad floored at 0.02
    assert exit_limit(0.0, 5.0, CFG) == 0.02


def test_exit_limit_capped_at_width():
    assert exit_limit(6.00, 5.0, CFG) == 5.0


def test_exit_limit_never_negative():
    assert exit_limit(-0.30, 5.0, CFG) == 0.02


def test_run_monitor_names_resolve():
    """The monitor's module-level and function-level names must all import.

    A NameError inside run_monitor is swallowed by the loop's blanket
    try/except and silently disables exits and cancels — this happened live
    on 2026-08-26 when parse_occ was used without its import.
    """
    import ast, inspect
    import agent.run_monitor as m

    src = inspect.getsource(m)
    tree = ast.parse(src)
    # every Name used inside run_monitor must be importable/defined
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_monitor")
    imported = set()
    for node in ast.walk(fn):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                imported.add(a.asname or a.name.split(".")[0])
    used = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    module_names = set(dir(m)) | imported | set(dir(__builtins__)) | {
        "log", "dry_run", "cfg", "broker", "option_data", "events",
    }
    # locals assigned within the function (assignments, for-targets, comprehensions, with, except)
    assigned = set()
    for n in ast.walk(fn):
        if isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.For, ast.withitem)):
            for t in ast.walk(n):
                if isinstance(t, ast.Name):
                    assigned.add(t.id)
        if isinstance(n, ast.comprehension):
            for t in ast.walk(n.target):
                if isinstance(t, ast.Name):
                    assigned.add(t.id)
        if isinstance(n, ast.ExceptHandler) and n.name:
            assigned.add(n.name)
    missing = used - module_names - assigned - {"__builtins__"}
    leftovers = {x for x in missing if not hasattr(__import__("builtins"), x)}
    assert not leftovers, f"names used in run_monitor but never defined: {leftovers}"
