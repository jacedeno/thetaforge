"""Agent entry point.

One pass = scan signals -> build spreads -> risk gates -> execute.
Run with --dry-run to see decisions without sending orders.
"""

from __future__ import annotations

import argparse
import logging
import os

from dotenv import load_dotenv

log = logging.getLogger("thetaforge")


def run_once(dry_run: bool = True) -> None:
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
    if not signals:
        return

    equity = broker.equity()
    obp = broker.options_buying_power()
    positions = broker.option_positions()
    held = {p.symbol[:-15] for p in positions}  # strip OCC suffix -> underlying root

    for sig in signals:
        log.info("signal %s LONG @ %.2f (bar %s)", sig.symbol, sig.close, sig.bar_time)
        spread = build_put_credit_spread(
            option_data, sig.symbol, sig.close, cfg.strategy, cfg.risk
        )
        if spread is None:
            log.info("  no spread passes chain/liquidity gates — skip")
            continue
        qty = position_qty(spread, equity, cfg.risk)
        gate = check_all(spread, qty, equity, obp, len(positions), held, cfg.risk)
        if not gate.passed:
            log.info("  vetoed: %s", gate.reason)
            continue
        log.info(
            "  %s: sell %s / buy %s x%d, credit ~%.2f, max risk $%.0f",
            "DRY-RUN" if dry_run else "OPEN",
            spread.short_symbol, spread.long_symbol, qty,
            spread.credit_mid, spread.max_risk_per_spread * qty,
        )
        if not dry_run:
            order = broker.open_credit_spread(spread, qty, spread.credit_mid)
            log.info("  order %s status=%s", order["id"], order["status"])
            held.add(spread.underlying)


def main() -> None:
    parser = argparse.ArgumentParser(description="ThetaForge agent")
    parser.add_argument("--dry-run", action="store_true", help="decide but do not send orders")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv()
    run_once(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
