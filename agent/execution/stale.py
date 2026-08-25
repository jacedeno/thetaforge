"""Stale-order cleanup.

An entry order priced at the mid goes stale when the underlying moves before it
fills: the credit it asks for no longer exists in the market. Left alone it
either sits unfilled all session, tying up buying power, or fills much later
under conditions that no longer match the signal that justified it.

Entries are therefore cancelled after a short window. Exits are never cancelled
here — an open position must be allowed to close.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def is_entry(order) -> bool:
    """True when every leg opens a position."""
    legs = getattr(order, "legs", None) or []
    intents = {str(getattr(leg, "position_intent", "")) for leg in legs}
    return bool(intents) and all("to_open" in i for i in intents)


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
