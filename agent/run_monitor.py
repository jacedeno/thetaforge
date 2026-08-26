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
    from agent import events
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

    # A stale entry gets one second chance at the NATURAL price before dying.
    # The paper simulator has no market makers: a limit fills only when it
    # crosses the NBBO, so mid-anchored orders mostly sit. Real fills beat
    # perfect prices in a P&L-judged environment.
    open_orders = broker.open_option_orders()
    from agent.execution.stale import is_retry, select_stale, spread_legs

    for o in select_stale(open_orders, cfg.strategy.order_stale_after_s):
        try:
            broker.cancel_order(str(o.id))
            log.info("cancelled stale entry order %s", o.id)
            events.emit("order_stale", order_id=str(o.id),
                        age_s=int(cfg.strategy.order_stale_after_s))
        except Exception:
            log.exception("could not cancel stale order %s", o.id)
            continue
        if is_retry(o):
            continue  # one reprice per spread — never chase further
        legs = spread_legs(o)
        if legs is None:
            continue
        try:
            from alpaca.data.requests import OptionLatestQuoteRequest

            quotes = option_data.get_option_latest_quote(
                OptionLatestQuoteRequest(symbol_or_symbols=list(legs)))
            sq, lq = quotes.get(legs[0]), quotes.get(legs[1])
            if not sq or not lq or not sq.bid_price or not lq.ask_price:
                continue
            natural = round(sq.bid_price - lq.ask_price, 2)
            if natural < cfg.strategy.min_credit_usd:
                events.emit("order_reprice_skipped", short=legs[0],
                            reason=f"natural credit {natural} below floor")
                continue
            import uuid as _uuid

            order = broker.open_spread_symbols(
                legs[0], legs[1], int(float(o.qty)), natural,
                client_order_id=f"tf-retry-{_uuid.uuid4().hex[:8]}")
            log.info("repriced stale entry at natural %.2f -> order %s", natural, order["id"])
            events.emit("order_reprice", short=legs[0], long=legs[1],
                        qty=int(float(o.qty)), natural=natural, status=order["status"])
        except Exception:
            log.exception("reprice failed for %s", o.id)
    open_orders = [o for o in open_orders if o not in select_stale(open_orders, cfg.strategy.order_stale_after_s)]

    # Symbols with an open (pending) order are skipped to avoid duplicates.
    pending = set()
    for o in open_orders:
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
