"""Stale-order cleanup.

An entry order priced at the mid goes stale when the underlying moves before it
fills: the credit it asks for no longer exists in the market. Left alone it
either sits unfilled all session, tying up buying power, or fills much later
under conditions that no longer match the signal that justified it.

Entries are therefore cancelled after a short window. Exits are never
cancelled by the ENTRY rule — but an unfilled exit is chased: after its own
window it is cancelled so the monitor's next decision re-places it at the
fresh cost. A position must always have a WORKING path to close, which a
resting limit nobody crosses is not (2026-08-27: a stop rested three hours).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _intent(leg) -> str:
    """Intent as a plain lowercase string.

    The SDK returns an enum whose str() is "PositionIntent.SELL_TO_OPEN" —
    matching on the raw string silently fails, so normalize via .value first.
    """
    raw = getattr(leg, "position_intent", "")
    return str(getattr(raw, "value", raw)).lower()


def is_entry(order) -> bool:
    """True when every leg opens a position."""
    legs = getattr(order, "legs", None) or []
    intents = {_intent(leg) for leg in legs}
    return bool(intents) and all(i.endswith("to_open") for i in intents)


def age_seconds(order, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    submitted = getattr(order, "submitted_at", None) or getattr(order, "created_at", None)
    if submitted is None:
        return 0.0
    if submitted.tzinfo is None:
        submitted = submitted.replace(tzinfo=timezone.utc)
    return (now - submitted).total_seconds()


def select_stale(orders: list, max_age_s: int, now: datetime | None = None) -> list:
    """Unfilled entry orders older than the window."""
    return [
        o for o in orders
        if is_entry(o)
        and float(getattr(o, "filled_qty", 0) or 0) == 0
        and age_seconds(o, now) > max_age_s
    ]


def is_exit(order) -> bool:
    """True when every leg closes a position."""
    legs = getattr(order, "legs", None) or []
    intents = {_intent(leg) for leg in legs}
    return bool(intents) and all(i.endswith("to_close") for i in intents)


def select_stale_exits(orders: list, max_age_s: int, now: datetime | None = None) -> list:
    """Unfilled exit orders old enough to cancel and re-decide at fresh cost."""
    return [
        o for o in orders
        if is_exit(o)
        and float(getattr(o, "filled_qty", 0) or 0) == 0
        and age_seconds(o, now) > max_age_s
    ]


def spread_legs(order) -> tuple[str, str] | None:
    """(short_symbol, long_symbol) of a two-leg entry order, else None."""
    legs = getattr(order, "legs", None) or []
    if len(legs) != 2:
        return None
    short = next((l for l in legs if _intent(l) == "sell_to_open"), None)
    long_ = next((l for l in legs if _intent(l) == "buy_to_open"), None)
    if short is None or long_ is None:
        return None
    return short.symbol, long_.symbol


def is_retry(order) -> bool:
    cid = str(getattr(order, "client_order_id", "") or "")
    return cid.startswith("tf-retry")
