"""Monitor pass: price open spreads and execute exits."""

from __future__ import annotations

import logging
import os

log = logging.getLogger("thetaforge")


def run_monitor(dry_run: bool = True) -> None:
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import OptionLatestQuoteRequest

    from agent.config import Config
    from agent.execution.broker import Broker
    from agent.execution.monitor import evaluate_exit, reconstruct_spreads

    cfg = Config()
    broker = Broker()
    option_data = OptionHistoricalDataClient(
        os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"]
    )

    # Reconcile the trade journal against the broker's filled orders.
    try:
        import requests as _rq
        from agent import journal
        r = _rq.get(
            "https://paper-api.alpaca.markets/v2/orders",
            params={"status": "closed", "asset_class": "us_option", "limit": "500", "nested": "true"},
            headers=broker._headers(), timeout=30,
        )
        if r.ok:
            journal.reconcile(r.json())
    except Exception:
        log.exception("journal reconcile failed — continuing")

    positions = broker.option_positions()
    spreads = reconstruct_spreads(positions)
    log.info("monitor: %d option leg(s) -> %d spread(s)", len(positions), len(spreads))
    if not spreads:
        return

    # Symbols with an open (pending) order are skipped to avoid duplicates.
    pending = set()
    for o in broker.open_option_orders():
        for leg in getattr(o, "legs", None) or []:
            pending.add(leg.symbol)
        if getattr(o, "symbol", None):
            pending.add(o.symbol)

    symbols = [s for sp in spreads for s in (sp.short_symbol, sp.long_symbol)]
    quotes = option_data.get_option_latest_quote(
        OptionLatestQuoteRequest(symbol_or_symbols=symbols)
    )

    def mid(symbol: str) -> float | None:
        q = quotes.get(symbol)
        if q is None or not q.bid_price or not q.ask_price:
            return None
        return (q.bid_price + q.ask_price) / 2

    for sp in spreads:
        if sp.short_symbol in pending or sp.long_symbol in pending:
            log.info("%s: pending order in flight — skip", sp.underlying)
            continue
        short_mid, long_mid = mid(sp.short_symbol), mid(sp.long_symbol)
        if short_mid is None or long_mid is None:
            log.warning("%s: no live quotes — skip", sp.underlying)
            continue
        decision = evaluate_exit(sp, short_mid, long_mid, cfg.strategy)
        log.info("%s x%d: %s — %s", sp.underlying, sp.qty, decision.action, decision.reason)
        from agent import events
        if decision.action == "CLOSE":
            events.emit("exit_signal", symbol=sp.underlying, reason=decision.reason,
                        cost=decision.cost_to_close, credit=sp.entry_credit, qty=sp.qty)
        if decision.action == "CLOSE" and not dry_run:
            # Cross the spread a little to get filled on exits.
            limit = round(decision.cost_to_close * 1.02 + 0.01, 2)
            order = broker.close_credit_spread(
                sp.short_symbol, sp.long_symbol, sp.qty, limit
            )
            log.info("  close order %s status=%s limit=%.2f", order["id"], order["status"], limit)
            events.emit("order_close", symbol=sp.underlying, qty=sp.qty,
                        limit=limit, reason=decision.reason, status=order["status"])
