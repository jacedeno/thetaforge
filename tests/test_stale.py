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


def test_entry_detection_with_sdk_enums():
    """The SDK sends enums whose str() is 'PositionIntent.SELL_TO_OPEN'."""
    from alpaca.trading.enums import PositionIntent

    o = order([PositionIntent.SELL_TO_OPEN, PositionIntent.BUY_TO_OPEN])
    assert is_entry(o)
    c = order([PositionIntent.BUY_TO_CLOSE, PositionIntent.SELL_TO_CLOSE])
    assert not is_entry(c)
    assert len(select_stale([o], 180, NOW)) == 1
    assert select_stale([c], 180, NOW) == []


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


def test_mleg_submit_args_shape():
    from agent.execution.broker import mleg_submit_args
    import json as _json

    legs = [{"symbol": "S", "ratio_qty": "1", "side": "sell", "position_intent": "sell_to_open"}]
    args = mleg_submit_args(legs, 5, -0.63, "tf-open-x")
    assert args[:2] == ["order", "submit"]
    assert "--order-class" in args and args[args.index("--order-class") + 1] == "mleg"
    assert args[args.index("--limit-price") + 1] == "-0.63"
    assert _json.loads(args[args.index("--legs") + 1]) == legs
