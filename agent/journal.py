"""Trade journal — SQLite persistence for round-trip trade history.

Alpaca is the source of truth for fills; only the agent knows *why* it
traded. The reconciler joins both: it reads filled multi-leg orders from
the broker, pairs opens with closes into round trips, and enriches them
with the agent's own decision trail (signal strength, exit reason).

Runs idempotently inside the monitor pass — safe to call every minute.
"""

from __future__ import annotations

import json
import re
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
    status          TEXT NOT NULL DEFAULT 'open',  -- open | closed
    source          TEXT NOT NULL DEFAULT 'agent'  -- agent | manual
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or DB_PATH
    p.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.execute(_SCHEMA)
    cols = {r[1] for r in con.execute("PRAGMA table_info(trades)")}
    if "source" not in cols:
        con.execute("ALTER TABLE trades ADD COLUMN source TEXT NOT NULL DEFAULT 'agent'")
    return con


# ---- order pairing -------------------------------------------------------

# Every client_order_id this codebase generates. Anything else on the tape —
# hand-typed smoke tests included — is a manual order and must never be
# counted as agent performance (learned 2026-08-26: tf-smoke-cli-001).
_AGENT_ORDER_ID = re.compile(r"^tf-(open|retry)-")


def order_source(order: dict) -> str:
    cid = order.get("client_order_id") or ""
    return "agent" if _AGENT_ORDER_ID.match(cid) else "manual"


def _leg_fills(order: dict) -> tuple[float, float] | None:
    """(sell fill, buy fill) when both legs carry filled_avg_price, else None."""
    legs = order.get("legs") or []
    sell = next((l for l in legs if l.get("side") == "sell"), None)
    buy = next((l for l in legs if l.get("side") == "buy"), None)
    if sell and buy and sell.get("filled_avg_price") and buy.get("filled_avg_price"):
        return float(sell["filled_avg_price"]), float(buy["filled_avg_price"])
    return None


def net_credit(order: dict) -> float:
    """Net price of a filled mleg order, always positive.

    The single source of truth for entry/exit prices: prefer the per-leg
    fills (what actually happened), fall back to the parent's
    filled_avg_price, whose sign convention Alpaca leaves to the reader.
    """
    fills = _leg_fills(order)
    if fills is not None:
        return round(abs(fills[0] - fills[1]), 2)
    return abs(float(order.get("filled_avg_price") or 0))


def leg_parent_mismatch(order: dict) -> float | None:
    """Divergence between leg-derived and parent-reported net price, if > 1c."""
    fills = _leg_fills(order)
    if fills is None:
        return None
    diff = round(abs(abs(fills[0] - fills[1]) - abs(float(order.get("filled_avg_price") or 0))), 2)
    return diff if diff > 0.01 else None


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
                "entry_credit": net_credit(o),
                "source": order_source(o),
                "close_ts": None, "exit_debit": None,
                "realized_pl": None, "status": "open",
            })
        elif is_closing(o) and opens.get(key):
            opened = opens[key].pop(0)
            trip = next(t for t in trips if t["open_order_id"] == opened["id"])
            trip["close_ts"] = o["filled_at"]
            trip["exit_debit"] = net_credit(o)
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
        # events carry the ticker, `underlying` is the OCC root — normalize
        # dotted classes (BRK.B vs BRKB) or enrichment silently misses.
        if (e.get("symbol") or "").replace(".", "") != underlying:
            continue
        if e["type"] == "signal" and e["ts"] <= trip["open_ts"]:
            strength = e.get("strength")
        if e["type"] in ("order_close", "exit_signal") and trip.get("close_ts") and e["ts"] <= trip["close_ts"]:
            reason = e.get("reason")
    trip["signal_strength"] = strength
    trip["exit_reason"] = reason
    return trip


# ---- reconciler ----------------------------------------------------------

# One journal_price_mismatch event per order per process — reconcile reruns
# over the same tape every monitor pass.
_mismatch_flagged: set[str] = set()


def reconcile(raw_orders: list[dict], con: sqlite3.Connection | None = None) -> int:
    """Upsert round trips built from the broker's filled orders. Returns row count."""
    from agent.execution.monitor import parse_occ

    con = con or connect()
    events = _load_events()
    for o in raw_orders:
        diff = leg_parent_mismatch(o)
        oid = str(o.get("id"))
        if diff is not None and oid not in _mismatch_flagged:
            _mismatch_flagged.add(oid)
            from agent import events as _ev
            _ev.emit("journal_price_mismatch", order_id=oid,
                     client_order_id=o.get("client_order_id"), divergence=diff)
    trips = pair_round_trips(raw_orders)
    for t in trips:
        occ = parse_occ(t["short_symbol"])
        locc = parse_occ(t["long_symbol"])
        enrich(t, events, occ.root)
        con.execute(
            """INSERT INTO trades (open_order_id, underlying, short_symbol, long_symbol,
                   short_strike, long_strike, expiration, qty, open_ts, close_ts,
                   entry_credit, exit_debit, realized_pl, exit_reason, signal_strength,
                   status, source)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(open_order_id) DO UPDATE SET
                   close_ts=excluded.close_ts, exit_debit=excluded.exit_debit,
                   entry_credit=excluded.entry_credit,
                   realized_pl=excluded.realized_pl, exit_reason=excluded.exit_reason,
                   signal_strength=COALESCE(excluded.signal_strength, trades.signal_strength),
                   status=excluded.status, source=excluded.source""",
            (t["open_order_id"], occ.root, t["short_symbol"], t["long_symbol"],
             occ.strike, locc.strike, occ.expiration.isoformat(), t["qty"],
             t["open_ts"], t["close_ts"], t["entry_credit"], t["exit_debit"],
             t["realized_pl"], t["exit_reason"], t["signal_strength"], t["status"],
             t["source"]),
        )
    con.commit()
    return len(trips)
