"""Structured event log — the agent's decision trail.

Every scan, signal, veto, order and exit lands in logs/events.jsonl as one
JSON object per line. The public web app renders this as the live
"agent brain" feed; it is also the audit trail for the write-up.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

_PATH = Path(__file__).resolve().parent.parent / "logs" / "events.jsonl"
_lock = Lock()


def emit(event_type: str, **payload) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "type": event_type,
        **payload,
    }
    with _lock:
        _PATH.parent.mkdir(exist_ok=True)
        with _PATH.open("a") as f:
            f.write(json.dumps(record) + "\n")


def tail(limit: int = 100) -> list[dict]:
    if not _PATH.exists():
        return []
    lines = _PATH.read_text().strip().splitlines()[-limit:]
    return [json.loads(line) for line in lines]
