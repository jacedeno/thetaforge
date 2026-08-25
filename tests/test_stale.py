from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from agent.execution.stale import age_seconds, is_entry, select_stale

NOW = datetime(2026, 8, 25, 14, 0, 0, tzinfo=timezone.utc)


def order(intents, filled="0", minutes_old=10, oid="x"):
    return SimpleNamespace(
        id=oid,
        filled_qty=filled,
        submitted_at=NOW - timedelta(minutes=minutes_old),
        legs=[SimpleNamespace(position_intent=i, symbol=f"S{n}") for n, i in enumerate(intents)],
    )


def test_entry_vs_exit_detection():
    assert is_entry(order(["sell_to_open", "buy_to_open"]))
    assert not is_entry(order(["buy_to_close", "sell_to_close"]))


def test_age_seconds():
    assert age_seconds(order(["sell_to_open", "buy_to_open"], minutes_old=5), NOW) == 300


def test_stale_entry_selected():
    stale = select_stale([order(["sell_to_open", "buy_to_open"], minutes_old=10)], 180, NOW)
    assert len(stale) == 1


def test_fresh_entry_kept():
    assert select_stale([order(["sell_to_open", "buy_to_open"], minutes_old=1)], 180, NOW) == []


def test_exit_order_never_cancelled():
    """An exit must be allowed to work — a position needs to be able to close."""
    old_exit = order(["buy_to_close", "sell_to_close"], minutes_old=120)
    assert select_stale([old_exit], 180, NOW) == []


def test_partially_filled_entry_kept():
    partial = order(["sell_to_open", "buy_to_open"], filled="1", minutes_old=30)
    assert select_stale([partial], 180, NOW) == []
