#!/usr/bin/env python3
"""Read-only trade diagnostics — adjudicate what the journal, the broker's
order tape, the event log, and the live monitor each believe about a trade.

Born from the 2026-08-26 SPY 700/695 incident, where the decisive column
turned out to be the client_order_id: the "trade" was a hand-typed CLI smoke
test, not an agent decision. This prints every source side by side plus
explicit verdict flags, so adjudication never again means a human diffing
four sources by eye.

Usage:
    python scripts/diagnose_trade.py              # last 10 round trips
    python scripts/diagnose_trade.py SPY          # every round trip in SPY
    python scripts/diagnose_trade.py --chain SPY  # trace the live chain scan

Read-only guarantees: sends no orders, opens the DB in SQLite read-only
mode, writes nothing under data/ or logs/.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

FLAGS_LEGEND = {
    "MANUAL_ORDER": "client_order_id matches no agent generator — not an agent trade",
    "NOT_IN_EVENT_LOG": "no order_open event for these legs — the agent never logged opening it",
    "PARENT_NE_LEGS": "parent filled_avg_price disagrees with the leg fills (> 1c)",
    "FILL_BELOW_LIMIT": "opening fill collected less credit than the submitted limit",
    "DELTA_OOB": "the delta the agent logged at entry is outside the configured band",
    "RATIO_LT_FLOOR": "entry credit / width below min_credit_to_width",
    "MONITOR_JOURNAL_DIVERGE": "monitor-reconstructed credit differs from the journal's (> 1c)",
}


def db_rows(underlying: str | None, limit: int) -> list[sqlite3.Row]:
    from agent.journal import DB_PATH

    if not DB_PATH.exists():
        print(f"no journal db at {DB_PATH}")
        return []
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    if underlying:
        q = "SELECT * FROM trades WHERE underlying = ? ORDER BY open_ts DESC"
        rows = con.execute(q, (underlying,)).fetchall()
    else:
        rows = con.execute(
            "SELECT * FROM trades ORDER BY open_ts DESC LIMIT ?", (limit,)
        ).fetchall()
    con.close()
    return rows


def order_tape(broker) -> list[dict]:
    import requests

    r = requests.get(
        "https://paper-api.alpaca.markets/v2/orders",
        params={"status": "closed", "asset_class": "us_option",
                "limit": "500", "nested": "true"},
        headers=broker._headers(), timeout=30,
    )
    r.raise_for_status()
    return r.json()


def find_close_order(tape: list[dict], row: sqlite3.Row) -> dict | None:
    from agent.journal import is_closing

    legs = tuple(sorted((row["short_symbol"], row["long_symbol"])))
    for o in sorted(tape, key=lambda x: x.get("filled_at") or ""):
        if not is_closing(o) or not o.get("filled_at"):
            continue
        if tuple(sorted(l["symbol"] for l in o.get("legs") or [])) == legs:
            if not row["close_ts"] or o["filled_at"] >= row["open_ts"]:
                return o
    return None


def held_for(row: sqlite3.Row) -> str:
    if not row["close_ts"]:
        return "open"
    ms = (datetime.fromisoformat(row["close_ts"].replace("Z", "+00:00"))
          - datetime.fromisoformat(row["open_ts"].replace("Z", "+00:00"))).total_seconds()
    if ms < 90:
        return f"{ms:.0f}s"
    if ms < 5400:
        return f"{ms / 60:.0f}m"
    if ms < 172800:
        return f"{ms / 3600:.1f}h"
    return f"{ms / 86400:.1f}d"


def leg_line(order: dict | None) -> str:
    if not order:
        return "(not on tape)"
    parts = []
    for l in order.get("legs") or []:
        parts.append(f"{l.get('side')} {l.get('symbol')} @ {l.get('filled_avg_price')}")
    return "   ".join(parts) or "(no legs)"


def diagnose(underlying: str | None, limit: int) -> None:
    from agent import journal
    from agent.config import Config
    from agent.execution.broker import Broker
    from agent.execution.monitor import reconstruct_spreads

    cfg = Config()
    broker = Broker()
    tape = {o["id"]: o for o in order_tape(broker)}
    events = journal._load_events()
    open_events = [e for e in events if e.get("type") == "order_open"]

    # What the monitor would compute right now, keyed by leg pair.
    monitor_now = {}
    try:
        for sp in reconstruct_spreads(broker.option_positions()):
            monitor_now[(sp.short_symbol, sp.long_symbol)] = sp
    except Exception as e:
        print(f"(monitor reconstruction unavailable: {e})")

    rows = db_rows(underlying, limit)
    if not rows:
        print("no matching trades in the journal")
        return

    for row in rows:
        parent = tape.get(row["open_order_id"])
        close_order = find_close_order(list(tape.values()), row)
        ev = next((e for e in open_events
                   if e.get("short") == row["short_symbol"]), None)
        width = abs(row["short_strike"] - row["long_strike"])
        flags = []

        if parent:
            if journal.order_source(parent) == "manual":
                flags.append("MANUAL_ORDER")
            if journal.leg_parent_mismatch(parent) is not None:
                flags.append("PARENT_NE_LEGS")
            limit_price = parent.get("limit_price")
            if limit_price is not None:
                if journal.net_credit(parent) < abs(float(limit_price)) - 0.005:
                    flags.append("FILL_BELOW_LIMIT")
        if ev is None:
            flags.append("NOT_IN_EVENT_LOG")
        else:
            delta = ev.get("delta")
            if delta is not None and not (
                cfg.strategy.min_short_delta <= abs(delta) <= cfg.strategy.max_short_delta
            ):
                flags.append("DELTA_OOB")
        if width and row["entry_credit"] / width < cfg.strategy.min_credit_to_width:
            flags.append("RATIO_LT_FLOOR")
        sp = monitor_now.get((row["short_symbol"], row["long_symbol"]))
        if sp is not None and abs(sp.entry_credit - row["entry_credit"]) > 0.01:
            flags.append("MONITOR_JOURNAL_DIVERGE")

        print(f"\n== {row['underlying']} {row['short_strike']:g}/{row['long_strike']:g}P "
              f"exp {row['expiration']} x{row['qty']}  [{row['status']}]  "
              f"held {held_for(row)}")
        print(f"   db          entry_credit={row['entry_credit']}  "
              f"exit_debit={row['exit_debit']}  realized_pl={row['realized_pl']}  "
              f"source={row['source'] if 'source' in row.keys() else '?'}  "
              f"signal_strength={row['signal_strength']}  exit_reason={row['exit_reason']}")
        if parent:
            print(f"   open order  client_order_id={parent.get('client_order_id')}  "
                  f"limit={parent.get('limit_price')}  filled_avg={parent.get('filled_avg_price')}")
            print(f"               {leg_line(parent)}")
        else:
            print("   open order  (not on tape — beyond the 500-order window?)")
        if row["close_ts"]:
            if close_order:
                print(f"   close order client_order_id={close_order.get('client_order_id')}  "
                      f"limit={close_order.get('limit_price')}  "
                      f"filled_avg={close_order.get('filled_avg_price')}")
                print(f"               {leg_line(close_order)}")
            else:
                print("   close order (not found on tape)")
        print(f"   event       "
              + (f"order_open credit={ev.get('credit')} delta={ev.get('delta')} "
                 f"entry_limit={ev.get('entry_limit')} ts={ev.get('ts')}" if ev else "(none)"))
        if sp is not None:
            print(f"   monitor     entry_credit={sp.entry_credit} ({sp.credit_source}) "
                  f"width={sp.width}")
        elif row["status"] == "open":
            print("   monitor     (position not found at broker)")
        print(f"   VERDICTS    {', '.join(flags) if flags else '(clean)'}")

    print("\nlegend:")
    seen = {f for _ in rows for f in FLAGS_LEGEND}
    for f in sorted(seen):
        print(f"   {f:24s} {FLAGS_LEGEND[f]}")


def trace_chain(underlying: str) -> None:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import StockLatestTradeRequest

    import os

    from agent.config import Config
    from agent.options.selector import (
        _trace_candidates,
        chain_request,
        target_width,
    )

    cfg = Config()
    key, secret = os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"]
    spot = StockHistoricalDataClient(key, secret).get_stock_latest_trade(
        StockLatestTradeRequest(symbol_or_symbols=underlying)
    )[underlying].price
    chain = OptionHistoricalDataClient(key, secret).get_option_chain(
        chain_request(underlying, spot, cfg.strategy, date.today())
    )
    width = target_width(spot, cfg.strategy)
    strikes = sorted({round(float(s[-8:]) / 1000, 2) for s in chain})
    spacing = sorted({round(b - a, 2) for a, b in zip(strikes, strikes[1:])})
    print(f"{underlying} spot={spot}  target_width={width:.2f}  "
          f"contracts={len(chain)}  strikes={len(strikes)} "
          f"[{strikes[0]:g}..{strikes[-1]:g}]  spacing={spacing}")
    print(f"{'symbol':22s} {'exp':10s} {'strike':>7s} {'delta':>6s} {'bid':>6s} "
          f"{'ask':>6s} {'mid':>6s} {'credit':>6s} {'c/w':>5s}  outcome")
    for t in _trace_candidates(chain, underlying, width, cfg.strategy, cfg.risk):
        snap = chain[t["symbol"]]
        quote = getattr(snap, "latest_quote", None)
        bid = getattr(quote, "bid_price", None)
        ask = getattr(quote, "ask_price", None)
        crossed = " CROSSED" if bid and ask and ask < bid else ""
        ratio = (f"{t['credit'] / t['width']:.2f}"
                 if t["credit"] is not None and t["width"] else "-")
        outcome = t["reject"] or f"CANDIDATE credit={t['credit']}"
        print(f"{t['symbol']:22s} {t['expiration']} {t['strike']:7g} "
              f"{t['delta'] if t['delta'] is not None else '-':>6} "
              f"{bid if bid is not None else '-':>6} {ask if ask is not None else '-':>6} "
              f"{t['mid'] if t['mid'] is not None else '-':>6} "
              f"{t['credit'] if t['credit'] is not None else '-':>6} {ratio:>5s}  "
              f"{outcome}{crossed}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("underlying", nargs="?", help="filter round trips to one underlying")
    ap.add_argument("--limit", type=int, default=10, help="round trips when no underlying given")
    ap.add_argument("--chain", metavar="UNDERLYING", help="trace the live chain scan instead")
    args = ap.parse_args()
    if args.chain:
        trace_chain(args.chain.upper())
    else:
        diagnose(args.underlying.upper() if args.underlying else None, args.limit)


if __name__ == "__main__":
    main()
