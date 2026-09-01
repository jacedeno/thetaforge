"""Monitor pass: price open spreads and execute exits."""

from __future__ import annotations

import logging
import os

log = logging.getLogger("thetaforge")

# One position_unmanageable event per symbol per process — the condition
# repeats every pass for as long as the spread is held.
_flagged_unmanageable: set[str] = set()

# How many times each spread's close has been placed and cancelled unfilled,
# keyed by leg pair. Drives the escalation from midpoint toward the natural
# price in exit_limit(); pruned below when the spread is no longer held, so a
# position that closes and is later re-opened starts again at the good price.
_exit_attempts: dict[tuple[str, str], int] = {}


def run_monitor(dry_run: bool = True) -> None:
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import OptionLatestQuoteRequest

    from agent import journal
    from agent.config import Config
    from agent.execution.broker import Broker
    from agent.execution.monitor import (
        evaluate_exit,
        exit_limit,
        parse_occ,
        reconstruct_spreads,
    )

    cfg = Config()
    broker = Broker()
    from agent import events
    option_data = OptionHistoricalDataClient(
        os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"]
    )

    # Reconcile the trade journal against the broker's filled orders.
    # This MUST run before reconstruct_spreads below: the exit decision
    # prefers the journal's fill-derived entry credit, so the journal has to
    # be fresh first. Keep this ordering.
    try:
        import requests as _rq
        r = _rq.get(
            "https://paper-api.alpaca.markets/v2/orders",
            params={"status": "closed", "asset_class": "us_option", "limit": "500", "nested": "true"},
            headers=broker._headers(), timeout=30,
        )
        if r.ok:
            journal.reconcile(r.json())
    except Exception:
        log.exception("journal reconcile failed — continuing")

    # Fill-derived entry credits for open trades, keyed by leg pair.
    credits: dict[tuple[str, str], float] = {}
    try:
        con = journal.connect()
        for row in con.execute(
            "SELECT short_symbol, long_symbol, entry_credit FROM trades WHERE status='open'"
        ):
            credits[(row["short_symbol"], row["long_symbol"])] = float(row["entry_credit"])
        con.close()
    except Exception:
        log.exception("journal read failed — falling back to avg entry prices")

    positions = broker.option_positions()
    spreads = reconstruct_spreads(positions, credits)
    log.info("monitor: %d option leg(s) -> %d spread(s)", len(positions), len(spreads))
    if not spreads:
        return

    # A stale entry gets one second chance at the NATURAL price before dying.
    # The paper simulator has no market makers: a limit fills only when it
    # crosses the NBBO, so mid-anchored orders mostly sit. Real fills beat
    # perfect prices in a P&L-judged environment.
    open_orders = broker.open_option_orders()
    from agent.execution.stale import (
        age_seconds,
        is_retry,
        select_stale,
        select_stale_exits,
        spread_legs,
    )

    # The stale pass cancels and REPRICES (= submits real orders). It must
    # honor dry_run: preflight runs a dry monitor pass on every restart and
    # must never touch the live order book.
    stale = select_stale(open_orders, cfg.strategy.order_stale_after_s)
    if dry_run and stale:
        log.info("dry-run: %d stale order(s) left untouched", len(stale))
    for o in stale if not dry_run else []:
        legs_for_name = spread_legs(o)
        stale_sym = parse_occ(legs_for_name[0]).root if legs_for_name else "?"
        try:
            broker.cancel_order(str(o.id))
            log.info("cancelled stale entry order %s (%s)", o.id, stale_sym)
            events.emit("order_stale", symbol=stale_sym, retry=is_retry(o),
                        age_s=int(cfg.strategy.order_stale_after_s))
        except Exception:
            log.exception("could not cancel stale order %s", o.id)
            continue
        if is_retry(o):
            continue  # one reprice per spread — never chase further
        # A signal this old is dead: a downed monitor must not sweep hour-old
        # orders into blind re-entries on restart (2026-08-26, COP/JPM/BA).
        if age_seconds(o) > cfg.strategy.reprice_max_age_s:
            events.emit("order_reprice_skipped", symbol=stale_sym,
                        reason=f"order {int(age_seconds(o) // 60)}m old — its signal is stale")
            continue
        legs = spread_legs(o)
        if legs is None:
            continue
        # If another fill already established this underlying, the signal is
        # satisfied — a reprice here would double the position.
        underlying = parse_occ(legs[0]).root
        if any(parse_occ(p.symbol).root == underlying for p in broker.option_positions()):
            events.emit("order_reprice_skipped", symbol=underlying, short=legs[0],
                        reason="position already exists in underlying")
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
            events.emit("order_reprice", symbol=underlying, short=legs[0], long=legs[1],
                        qty=int(float(o.qty)), natural=natural, status=order["status"])
        except Exception:
            log.exception("reprice failed for %s", o.id)
    # Exit chase: an unfilled close that sat past its window is cancelled so
    # the decision loop below re-places it at the FRESH cost this same pass —
    # a position must never sit unmanaged behind a resting limit.
    stale_exits = select_stale_exits(open_orders, cfg.strategy.exit_stale_after_s)
    for o in stale_exits if not dry_run else []:
        legs_for_name = [l.symbol for l in (getattr(o, "legs", None) or [])]
        exit_sym = parse_occ(legs_for_name[0]).root if legs_for_name else "?"
        try:
            broker.cancel_order(str(o.id))
            log.info("cancelled stale exit %s (%s) — re-deciding at fresh cost", o.id, exit_sym)
            events.emit("exit_stale", symbol=exit_sym,
                        age_s=int(age_seconds(o)), limit=float(o.limit_price or 0))
        except Exception:
            log.exception("could not cancel stale exit %s", o.id)

    if not dry_run:
        open_orders = [o for o in open_orders if o not in stale and o not in stale_exits]

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
        if q.ask_price < q.bid_price:   # crossed quote — stale or bogus tick
            return None
        return (q.bid_price + q.ask_price) / 2

    def natural_cost(sp) -> float | None:
        """What closing costs RIGHT NOW: lift the short's ask, hit the long's bid."""
        sq, lq = quotes.get(sp.short_symbol), quotes.get(sp.long_symbol)
        if sq is None or lq is None or not sq.ask_price or not lq.bid_price:
            return None
        return round(sq.ask_price - lq.bid_price, 2)

    # Forget spreads we no longer hold, so the counter tracks live positions only.
    held = {(sp.short_symbol, sp.long_symbol) for sp in spreads}
    for key in list(_exit_attempts):
        if key not in held:
            del _exit_attempts[key]

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
        if decision.flag and sp.underlying not in _flagged_unmanageable:
            _flagged_unmanageable.add(sp.underlying)
            event = ("quote_anomaly" if decision.flag == "bad_quotes"
                     else "position_unmanageable")
            events.emit(event, symbol=sp.underlying,
                        credit=sp.entry_credit, reason=decision.reason)
        if decision.action == "CLOSE":
            events.emit("exit_signal", symbol=sp.underlying, reason=decision.reason,
                        cost=decision.cost_to_close, credit=sp.entry_credit, qty=sp.qty)
        if decision.action == "CLOSE" and not dry_run:
            key = (sp.short_symbol, sp.long_symbol)
            attempt = _exit_attempts.get(key, 0)
            # Taking profit must stay profitable: never bid up to or past the
            # credit collected. A stop or a time close has no such luxury —
            # they are bounded only by the width.
            ceiling = (sp.entry_credit - 0.01) if decision.kind == "target" else None
            limit = exit_limit(
                decision.cost_to_close, sp.width, cfg.strategy,
                natural=natural_cost(sp), attempt=attempt, ceiling=ceiling,
            )
            order = broker.close_credit_spread(
                sp.short_symbol, sp.long_symbol, sp.qty, limit
            )
            _exit_attempts[key] = attempt + 1
            log.info("  close order %s status=%s limit=%.2f (attempt %d)",
                     order["id"], order["status"], limit, attempt)
            events.emit("order_close", symbol=sp.underlying, qty=sp.qty,
                        limit=limit, reason=decision.reason, status=order["status"],
                        attempt=attempt, natural=natural_cost(sp))
