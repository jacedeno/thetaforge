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

from agent.run_scan import run_scan
from agent.run_monitor import run_monitor

log = logging.getLogger("thetaforge")

MONITOR_INTERVAL_S = 60


def market_is_open(broker) -> bool:
    clock = broker.trading.get_clock()
    return bool(clock.is_open)


def run_loop(dry_run: bool) -> None:
    from agent.execution.broker import Broker

    broker = Broker()
    last_scan_slot: str | None = None
    log.info("loop started (dry_run=%s)", dry_run)
    while True:
        try:
            if market_is_open(broker):
                now = datetime.now(timezone.utc)
                slot = f"{now.hour}:{now.minute // 15}"   # changes at each 15m boundary
                # Scan ~30s after the boundary so the just-closed bar is available.
                if slot != last_scan_slot and now.minute % 15 == 0:
                    time.sleep(30)
                    run_scan(dry_run=dry_run)
                    last_scan_slot = slot
                run_monitor(dry_run=dry_run)
            else:
                log.info("market closed — sleeping 5m")
                time.sleep(240)
        except Exception:
            log.exception("loop iteration failed — continuing")
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
