#!/usr/bin/env python3
"""Read-only funnel report: signals -> vetoes -> orders for one day.

Answers "why didn't more positions get taken?" with counts instead of
scrolling the log — capacity vetoes (position cap, risk budget, buying
power) are broken out so the 13 x 1.5% sizing experiment can be measured.

Usage:
    uv run python scripts/veto_summary.py              # today
    uv run python scripts/veto_summary.py 2026-08-26   # a specific day
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import journal

CAPACITY = ("max open positions", "risk budget", "buying power")


def main() -> None:
    day = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    events = [e for e in journal._load_events() if e.get("ts", "").startswith(day)]
    if not events:
        print(f"no events on {day}")
        return

    signals = [e for e in events if e["type"] == "signal"]
    vetoes = Counter(
        e.get("reason", "?") for e in events if e["type"] == "veto"
    )
    opens = [e for e in events if e["type"] == "order_open"]
    closes = [e for e in events if e["type"] == "order_close"]

    print(f"{day}: {len(signals)} signals -> {len(opens)} orders opened, "
          f"{len(closes)} closes")
    capacity_total = 0
    print("\nvetoes by reason:")
    for reason, n in vetoes.most_common():
        cap = any(k in reason for k in CAPACITY)
        capacity_total += n if cap else 0
        print(f"  {n:4d}  {reason}{'   << CAPACITY' if cap else ''}")
    print(f"\ncapacity vetoes (position cap / risk budget / buying power): "
          f"{capacity_total}")
    if capacity_total:
        syms = Counter(
            e.get("symbol", "?") for e in events
            if e["type"] == "veto" and any(k in e.get("reason", "") for k in CAPACITY)
        )
        print("  by symbol:", ", ".join(f"{s}x{n}" for s, n in syms.most_common(15)))


if __name__ == "__main__":
    main()
