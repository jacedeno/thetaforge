"""Scan pass: signals -> spreads -> risk gates -> entries."""

from __future__ import annotations

import logging
import os

log = logging.getLogger("thetaforge")


def run_scan(dry_run: bool = True) -> None:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.historical.option import OptionHistoricalDataClient

    from agent.config import Config
    from agent.execution.broker import Broker
    from agent.options.selector import build_put_credit_spread
    from agent.risk.gates import check_all, position_qty
    from agent.signals import ml30

    cfg = Config()
    key, secret = os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"]
    stock_data = StockHistoricalDataClient(key, secret)
    option_data = OptionHistoricalDataClient(key, secret)
    broker = Broker()

    signals = ml30.scan(stock_data)
    log.info("scan complete: %d signal(s)", len(signals))
    from agent import events
    events.emit("scan", signals=len(signals), universe=80)
    if not signals:
        return

    equity = broker.equity()
    obp = broker.options_buying_power()
    positions = broker.option_positions()
    from agent.execution.monitor import parse_occ

    held = {parse_occ(p.symbol).root for p in positions}
    # An order in flight is a claim on its underlying: without this, a signal
    # that repeats across scans stacks a second order on top of the first —
    # observed live 2026-08-26 as a doubled HD position at 2x the risk budget.
    for o in broker.open_option_orders():
        for leg in getattr(o, "legs", None) or []:
            try:
                held.add(parse_occ(leg.symbol).root)
            except ValueError:
                pass

    opened_this_scan = 0
    for sig in signals:
        if opened_this_scan >= cfg.strategy.max_new_positions_per_scan:
            log.info("per-scan entry cap reached — %d signal(s) deferred", len(signals) - signals.index(sig))
            break
        log.info("signal %s LONG @ %.2f strength=%.4f (bar %s)", sig.symbol, sig.close, sig.strength, sig.bar_time)
        events.emit("signal", symbol=sig.symbol, direction="LONG", price=sig.close,
                    strength=round(sig.strength, 4))
        spread = build_put_credit_spread(
            option_data, sig.symbol, sig.close, cfg.strategy, cfg.risk
        )
        if spread is None:
            log.info("  no spread passes chain/liquidity gates — skip")
            events.emit("veto", symbol=sig.symbol, reason="no spread passes chain/liquidity gates")
            continue
        qty = position_qty(spread, equity, cfg.risk)
        gate = check_all(spread, qty, equity, obp, len(held), held, cfg.risk)
        if not gate.passed:
            log.info("  vetoed: %s", gate.reason)
            events.emit("veto", symbol=sig.symbol, reason=gate.reason)
            continue
        log.info(
            "  %s: sell %s / buy %s x%d, credit ~%.2f, max risk $%.0f",
            "DRY-RUN" if dry_run else "OPEN",
            spread.short_symbol, spread.long_symbol, qty,
            spread.credit_mid, spread.max_risk_per_spread * qty,
        )
        opened_this_scan += 1
        # An order at the exact mid queues behind the market and mostly sits
        # unfilled; a small concession trades pennies for a filled position.
        concession = max(cfg.strategy.entry_concession_min,
                         round(spread.credit_mid * cfg.strategy.entry_concession_pct, 2))
        entry_limit = round(spread.credit_mid - concession, 2)
        if not dry_run:
            order = broker.open_credit_spread(spread, qty, entry_limit)
            log.info("  order %s status=%s", order["id"], order["status"])
            events.emit("order_open", symbol=spread.underlying,
                        short=spread.short_symbol, long=spread.long_symbol,
                        qty=qty, credit=spread.credit_mid,
                        max_risk=round(spread.max_risk_per_spread * qty, 2),
                        delta=spread.short_delta, status=order["status"])
            held.add(spread.underlying)
