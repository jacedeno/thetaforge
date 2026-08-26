"""Agent entry point.

Modes:
    --scan       one signal-scan pass (entries)
    --monitor    one monitor pass (exits)
    --loop       run continuously during market hours:
                 scan on each 15m bar close, monitor every minute
    --dry-run    decide but never send orders (combines with any mode)
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

import json
from pathlib import Path

from agent.run_scan import run_scan
from agent.run_monitor import run_monitor

HEARTBEAT = Path(__file__).resolve().parent.parent / "data" / "heartbeat.json"


def beat(**extra) -> None:
    HEARTBEAT.parent.mkdir(exist_ok=True)
    HEARTBEAT.write_text(json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **extra,
    }))

log = logging.getLogger("thetaforge")

MONITOR_INTERVAL_S = 60


def market_is_open(broker) -> bool:
    clock = broker.trading.get_clock()
    return bool(clock.is_open)


def run_loop(dry_run: bool) -> None:
    from agent.execution.broker import Broker

    broker = Broker()
    last_scan_slot: str | None = None
    last_scan_ts: str | None = None
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    iteration = 0
    consecutive_failures = 0
    log.info("loop started (dry_run=%s)", dry_run)
    while True:
        try:
            iteration += 1
            open_now = market_is_open(broker)
            beat(market_open=open_now, last_scan=last_scan_ts, started=started,
                 iteration=iteration, dry_run=dry_run,
                 consecutive_failures=consecutive_failures)
            if open_now:
                now = datetime.now(timezone.utc)
                slot = f"{now.hour}:{now.minute // 15}"   # changes at each 15m boundary
                # Fire once per quarter, whenever the first iteration of that
                # quarter lands — never require hitting the exact boundary
                # minute, which the loop's natural drift will eventually skip.
                if slot != last_scan_slot:
                    if now.minute % 15 == 0 and now.second < 30:
                        time.sleep(30 - now.second)  # let the bar close
                    run_scan(dry_run=dry_run)
                    last_scan_slot = slot
                    last_scan_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
                run_monitor(dry_run=dry_run)
            else:
                log.info("market closed — sleeping 5m")
                time.sleep(240)
            consecutive_failures = 0
        except Exception:
            consecutive_failures += 1
            log.exception("loop iteration failed (%d in a row) — continuing",
                          consecutive_failures)
        time.sleep(MONITOR_INTERVAL_S)


def main() -> None:
    parser = argparse.ArgumentParser(description="ThetaForge agent")
    parser.add_argument("--scan", action="store_true", help="one entry-scan pass")
    parser.add_argument("--monitor", action="store_true", help="one exit-monitor pass")
    parser.add_argument("--loop", action="store_true", help="run continuously")
    parser.add_argument("--dry-run", action="store_true", help="decide but do not send orders")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv()

    if args.loop:
        run_loop(dry_run=args.dry_run)
    elif args.monitor:
        run_monitor(dry_run=args.dry_run)
    else:
        run_scan(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
