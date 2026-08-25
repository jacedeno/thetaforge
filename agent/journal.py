"""Trade journal — SQLite persistence for round-trip trade history.

Alpaca is the source of truth for fills; only the agent knows *why* it
traded. The reconciler joins both: it reads filled multi-leg orders from
the broker, pairs opens with closes into round trips, and enriches them
with the agent's own decision trail (signal strength, exit reason).

Runs idempotently inside the monitor pass — safe to call every minute.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "thetaforge.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    open_order_id   TEXT PRIMARY KEY,
    underlying      TEXT NOT NULL,
    short_symbol    TEXT NOT NULL,
    long_symbol     TEXT NOT NULL,
    short_strike    REAL,
    long_strike     REAL,
    expiration      TEXT,
    qty             INTEGER NOT NULL,
    open_ts         TEXT NOT NULL,
    close_ts        TEXT,
    entry_credit    REAL NOT NULL,
    exit_debit      REAL,
    realized_pl     REAL,
    exit_reason     TEXT,
    signal_strength REAL,
    status          TEXT NOT NULL DEFAULT 'open'   -- open | closed
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or DB_PATH
    p.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.execute(_SCHEMA)
    return con


# ---- order pairing -------------------------------------------------------


def _leg_intents(order: dict) -> set[str]:
    return {leg.get("position_intent", "") for leg in order.get("legs") or []}


def _leg_symbols(order: dict) -> tuple[str, ...]:
    return tuple(sorted(leg["symbol"] for leg in order.get("legs") or []))


def is_opening(order: dict) -> bool:
    return any(i.endswith("_to_open") for i in _leg_intents(order))


def is_closing(order: dict) -> bool:
    return any(i.endswith("_to_close") for i in _leg_intents(order))


def pair_round_trips(filled_orders: list[dict]) -> list[dict]:
    """Pair filled mleg orders into round trips, FIFO per leg-symbol set.

    Returns trade dicts keyed by the opening order id. A trade with no
    matching close yet is returned with status='open'.
    """
    opens: dict[tuple, list[dict]] = {}
    trips: list[dict] = []
    for o in sorted(filled_orders, key=lambda x: x.get("filled_at") or ""):
        if not o.get("filled_at") or not o.get("legs"):
            continue
        key = _leg_symbols(o)
        if is_opening(o):
            opens.setdefault(key, []).append(o)
            short = next(l for l in o["legs"] if l["side"] == "sell")
            long_ = next(l for l in o["legs"] if l["side"] == "buy")
            trips.append({
                "open_order_id": o["id"],
                "short_symbol": short["symbol"],
                "long_symbol": long_["symbol"],
                "qty": int(float(o["qty"])),
                "open_ts": o["filled_at"],
                "entry_credit": abs(float(o["filled_avg_price"] or 0)),
                "close_ts": None, "exit_debit": None,
                "realized_pl": None, "status": "open",
            })
        elif is_closing(o) and opens.get(key):
            opened = opens[key].pop(0)
            trip = next(t for t in trips if t["open_order_id"] == opened["id"])
            trip["close_ts"] = o["filled_at"]
            trip["exit_debit"] = abs(float(o["filled_avg_price"] or 0))
            trip["realized_pl"] = round(
                (trip["entry_credit"] - trip["exit_debit"]) * 100 * trip["qty"], 2
            )
            trip["status"] = "closed"
    return trips


# ---- agent-metadata enrichment ------------------------------------------


def _load_events() -> list[dict]:
    path = Path(__file__).resolve().parent.parent / "logs" / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().strip().splitlines() if l]


def enrich(trip: dict, events: list[dict], underlying: str) -> dict:
    """Attach signal strength (nearest before open) and exit reason (nearest close event)."""
    strength, reason = None, None
    for e in events:
        if e.get("symbol") != underlying:
            continue
        if e["type"] == "signal" and e["ts"] <= trip["open_ts"]:
            strength = e.get("strength")
        if e["type"] in ("order_close", "exit_signal") and trip.get("close_ts") and e["ts"] <= trip["close_ts"]:
            reason = e.get("reason")
    trip["signal_strength"] = strength
    trip["exit_reason"] = reason
    return trip


# ---- reconciler ----------------------------------------------------------


def reconcile(raw_orders: list[dict], con: sqlite3.Connection | None = None) -> int:
    """Upsert round trips built from the broker's filled orders. Returns row count."""
    from agent.execution.monitor import parse_occ

    con = con or connect()
    events = _load_events()
    trips = pair_round_trips(raw_orders)
    for t in trips:
        occ = parse_occ(t["short_symbol"])
        locc = parse_occ(t["long_symbol"])
        enrich(t, events, occ.root)
        con.execute(
            """INSERT INTO trades (open_order_id, underlying, short_symbol, long_symbol,
                   short_strike, long_strike, expiration, qty, open_ts, close_ts,
                   entry_credit, exit_debit, realized_pl, exit_reason, signal_strength, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(open_order_id) DO UPDATE SET
                   close_ts=excluded.close_ts, exit_debit=excluded.exit_debit,
                   realized_pl=excluded.realized_pl, exit_reason=excluded.exit_reason,
                   signal_strength=COALESCE(excluded.signal_strength, trades.signal_strength),
                   status=excluded.status""",
            (t["open_order_id"], occ.root, t["short_symbol"], t["long_symbol"],
             occ.strike, locc.strike, occ.expiration.isoformat(), t["qty"],
             t["open_ts"], t["close_ts"], t["entry_credit"], t["exit_debit"],
             t["realized_pl"], t["exit_reason"], t["signal_strength"], t["status"]),
        )
    con.commit()
    return len(trips)
