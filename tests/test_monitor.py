from datetime import date
from types import SimpleNamespace

from agent.config import StrategyConfig
from agent.execution.monitor import (
    OpenSpread,
    evaluate_exit,
    parse_occ,
    reconstruct_spreads,
)

CFG = StrategyConfig()
TODAY = date(2026, 8, 24)


def make_spread(credit=1.00, exp=date(2026, 9, 11)):
    return OpenSpread(
        underlying="NVDA",
        short_symbol="NVDA260911P00197500",
        long_symbol="NVDA260911P00192500",
        qty=5,
        entry_credit=credit,
        expiration=exp,
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
