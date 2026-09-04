"""Operator liquidation: close every open spread at the natural price.

The sanctioned shape of an operator action (docs/OPERATIONS.md, 2026-08-27
reset): explicit orders through the agent's own broker path, `order_close`
events carrying the reason, and a written record — the opposite of a silent
sweep. Used 2026-09-04 to flatten the post-hackathon caretaker book before
relaunching the system on a smaller account.

Run with the LOOP STOPPED. The monitor's stale-exit sweeper cancels any
unfilled exit after its window and then re-decides by its own three rules —
which will say HOLD, not CLOSE, for an operator liquidation. This script
does its own chasing instead: submit at natural, wait, re-quote, re-submit
what did not fill.

    uv run python scripts/close_book.py            # dry run (default)
    uv run python scripts/close_book.py --execute  # place orders
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("thetaforge.close_book")

REASON = "operator_relaunch"
PASSES = 4          # submit / check cycles before giving up on a leg pair
WAIT_S = 45         # fill wait per pass; natural-priced orders fill fast or not at all


def main() -> int:
    parser = argparse.ArgumentParser(description="Close every open spread at natural")
    parser.add_argument("--execute", action="store_true", help="place real orders")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv(".env")

    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import OptionLatestQuoteRequest

    from agent import events, journal
    from agent.execution.broker import Broker
    from agent.execution.monitor import reconstruct_spreads

    broker = Broker()
    option_data = OptionHistoricalDataClient(
        os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"]
    )

    if args.execute:
        clock = broker.trading.get_clock()
        if not clock.is_open:
            log.error("market is closed — natural prices mean nothing; refusing")
            return 1

    def entry_credits() -> dict[tuple[str, str], float]:
        """Fill-derived credits for open trades, exactly as the monitor reads them."""
        import requests

        r = requests.get(
            "https://paper-api.alpaca.markets/v2/orders",
            params={"status": "closed", "asset_class": "us_option",
                    "limit": "500", "nested": "true"},
            headers=broker._headers(), timeout=30,
        )
        if r.ok:
            journal.reconcile(r.json())
        credits: dict[tuple[str, str], float] = {}
        con = journal.connect()
        for row in con.execute(
            "SELECT short_symbol, long_symbol, entry_credit FROM trades WHERE status='open'"
        ):
            credits[(row["short_symbol"], row["long_symbol"])] = float(row["entry_credit"])
        con.close()
        return credits

    for attempt in range(1, PASSES + 1):
        positions = broker.option_positions()
        spreads = reconstruct_spreads(positions, entry_credits())
        if not spreads:
            log.info("book is flat — done")
            return 0

        symbols = [s for sp in spreads for s in (sp.short_symbol, sp.long_symbol)]
        quotes = option_data.get_option_latest_quote(
            OptionLatestQuoteRequest(symbol_or_symbols=symbols)
        )

        # A close that did not fill in one pass is not going to: on wide-quoted
        # legs (HD's quoted $1.40 per leg during the 2026-09-04 liquidation)
        # the natural moves before the order does. Cancel and re-price at the
        # fresh natural instead of waiting behind a stale limit.
        if attempt > 1 and args.execute:
            for o in broker.open_option_orders():
                try:
                    broker.cancel_order(str(o.id))
                    log.info("cancelled unfilled close %s — re-pricing", o.id)
                except Exception:
                    log.exception("could not cancel %s", o.id)
            time.sleep(3)

        log.info("pass %d/%d — %d spread(s) open", attempt, PASSES, len(spreads))
        submitted = 0
        for sp in spreads:
            sq, lq = quotes.get(sp.short_symbol), quotes.get(sp.long_symbol)
            if sq is None or lq is None or not sq.ask_price or not lq.bid_price:
                log.warning("%s: no usable quotes — skipped this pass", sp.underlying)
                continue
            # Pay what the book asks, never more than the spread can be worth.
            natural = round(sq.ask_price - lq.bid_price, 2)
            limit = round(min(max(natural, 0.01), sp.width), 2)
            log.info("%s x%d: close at natural %.2f (credit was %.2f)",
                     sp.underlying, sp.qty, limit, sp.entry_credit)
            if not args.execute:
                continue
            order = broker.close_credit_spread(
                sp.short_symbol, sp.long_symbol, sp.qty, limit
            )
            events.emit("order_close", symbol=sp.underlying, qty=sp.qty,
                        limit=limit, reason=REASON, status=order["status"],
                        attempt=attempt - 1, natural=natural)
            submitted += 1

        if not args.execute:
            log.info("dry run — no orders placed")
            return 0
        log.info("%d order(s) submitted — waiting %ds for fills", submitted, WAIT_S)
        time.sleep(WAIT_S)

    positions = broker.option_positions()
    if positions:
        log.error("NOT flat after %d passes — %d leg(s) remain; run again or inspect",
                  PASSES, len(positions))
        return 1
    log.info("book is flat — done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
