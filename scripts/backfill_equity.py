#!/usr/bin/env python3
"""Seed the equity curve from the broker's own portfolio history.

The loop samples equity every five minutes, but only from the moment that
sampling shipped. This fills in what came before, so the chart opens with
the account's whole life at five-minute grain instead of starting blank.

The broker serves five-minute buckets for about a week and answers a 400
for a month at that resolution, so this reaches back one week and stops.
Backfilled rows never overwrite a sample the loop recorded: the loop's
number is the one the sizing ladder actually saw.

Usage:
    uv run python scripts/backfill_equity.py            # last week, 5Min
    uv run python scripts/backfill_equity.py --dry-run  # report, write nothing
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from agent import journal

PERIOD = "1W"
TIMEFRAME = "5Min"


def fetch() -> list[tuple[datetime, float]]:
    from agent.execution.broker import Broker

    broker = Broker()
    h = broker.portfolio_history(period=PERIOD, timeframe=TIMEFRAME)
    out: list[tuple[datetime, float]] = []
    for ts, eq in zip(h.get("timestamp") or [], h.get("equity") or []):
        if eq is None or eq <= 0:
            continue
        out.append((datetime.fromtimestamp(ts, timezone.utc), float(eq)))
    return out


def main() -> None:
    load_dotenv()
    dry = "--dry-run" in sys.argv
    samples = fetch()
    if not samples:
        print("broker returned no equity buckets — nothing to backfill")
        return

    con = journal.connect()
    before = con.execute("SELECT COUNT(*) FROM equity_samples").fetchone()[0]
    if not dry:
        for when, eq in samples:
            journal.record_equity(eq, when=when, source="backfill", con=con)
    after = con.execute("SELECT COUNT(*) FROM equity_samples").fetchone()[0]
    span = con.execute("SELECT MIN(ts), MAX(ts) FROM equity_samples").fetchone()
    con.close()

    first, last = samples[0][0], samples[-1][0]
    print(f"broker buckets with equity : {len(samples)} "
          f"({first:%Y-%m-%d %H:%M} .. {last:%Y-%m-%d %H:%M} UTC)")
    if dry:
        print(f"rows in journal            : {before} (dry run, nothing written)")
        return
    print(f"rows in journal            : {before} -> {after} (+{after - before})")
    print(f"curve now spans            : {span[0]} .. {span[1]}")


if __name__ == "__main__":
    main()
