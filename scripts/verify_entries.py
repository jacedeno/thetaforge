#!/usr/bin/env python3
"""Read-only entry audit — re-run the V1-5m trigger for every open position.

For each open trade in the journal: find its `signal` event, rebuild the
5-minute SMA55/21 state as of that scan, re-evaluate ml30's four conditions
(c1 close>SMA55, c2 fresh cross, c3 close>SMA21, c4 bullish candle) on the
signal bar, and report per-condition verdicts plus the signal->fill delay.

Sends no orders; opens the DB read-only. Bars are refetched today, so tiny
price revisions are possible — the signal bar is located by matching the
event's logged close, falling back to the scan-time bar.

Usage:  uv run python scripts/verify_entries.py
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")   # the operator's clock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from alpaca.data.historical import StockHistoricalDataClient

from agent import journal
from agent.signals import ml30


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def floor5(dt: datetime) -> datetime:
    dt = dt.replace(second=0, microsecond=0)
    return dt - timedelta(minutes=dt.minute % 5)


def main() -> None:
    con = sqlite3.connect(f"file:{journal.DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT * FROM trades WHERE status='open' ORDER BY open_ts"
    ).fetchall()
    con.close()
    events = journal._load_events()
    signals = [e for e in events if e.get("type") == "signal"]
    order_opens = [e for e in events if e.get("type") == "order_open"]
    client = StockHistoricalDataClient(
        os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"]
    )

    ok = data_drift = problems = 0
    for r in rows:
        open_ts = parse_ts(r["open_ts"])
        # Anchor on the order_open for THESE legs — a stale order can fill via
        # reprice long after later scans re-signaled the same symbol, so the
        # latest signal before the FILL is often the wrong one.
        oo = max(
            (e for e in order_opens
             if e.get("short") == r["short_symbol"] and parse_ts(e["ts"]) <= open_ts),
            key=lambda e: e["ts"], default=None,
        )
        anchor_ts = parse_ts(oo["ts"]) if oo else open_ts
        sig_ev = max(
            (e for e in signals
             if e.get("symbol") == r["underlying"] and parse_ts(e["ts"]) <= anchor_ts),
            key=lambda e: e["ts"], default=None,
        )
        print(f"\n== {r['underlying']} {r['short_strike']:g}/{r['long_strike']:g} "
              f"x{r['qty']}  filled {open_ts.astimezone(CT):%H:%M:%S} CT")
        if sig_ev is None:
            print("   VERDICT: NO_SIGNAL_EVENT — nothing in the log before this order")
            problems += 1
            continue
        sig_ts = parse_ts(sig_ev["ts"])
        ev_price = float(sig_ev.get("price") or 0)
        ev_strength = sig_ev.get("strength")
        days = max(4, (datetime.now(timezone.utc) - sig_ts).days + 2)
        df = ml30.fetch_bars(client, [r["underlying"]], days=days).get(r["underlying"])
        if df is None or df.empty:
            print("   VERDICT: NO_DATA — could not refetch bars")
            problems += 1
            continue

        # Locate the bar the agent evaluated. Newer signal events carry
        # bar_time outright; otherwise try the scan-time bar and up to two
        # older ones (data lag), fingerprinting each against the logged
        # close and strength.
        candidates = []
        if sig_ev.get("bar_time"):
            candidates = [parse_ts(sig_ev["bar_time"])]
        else:
            scan_bar = floor5(sig_ts - timedelta(minutes=5))
            candidates = [scan_bar - timedelta(minutes=5 * lag) for lag in (0, 1, 2)]

        best = None
        for cand in candidates:
            if cand not in df.index:
                continue
            hist = df[df.index <= cand]
            if len(hist) < ml30.BARS_NEEDED:
                continue
            close = hist["close"]
            s55 = close.rolling(ml30.SMA_SLOW).mean()
            s21 = close.rolling(ml30.SMA_FAST).mean()
            strength = (close.iloc[-1] / s55.iloc[-1] - 1) + (close.iloc[-1] / s21.iloc[-1] - 1)
            score = abs(float(close.iloc[-1]) - ev_price) + (
                abs(strength - ev_strength) * 100 if ev_strength is not None else 0
            )
            if best is None or score < best[0]:
                best = (score, cand, hist, close, s55, s21, strength)
        if best is None:
            print("   VERDICT: NO_WARMUP — not enough bars refetched")
            problems += 1
            continue

        _, bar_label, hist, close, s55, s21, strength = best
        price_diff = abs(float(close.iloc[-1]) - ev_price)
        strength_diff = (abs(strength - ev_strength)
                         if ev_strength is not None else None)
        fingerprint = price_diff <= 0.02 and (strength_diff is None or strength_diff <= 0.002)

        c1 = bool(close.iloc[-1] > s55.iloc[-1])
        c2 = bool(close.iloc[-2] <= s55.iloc[-2])
        c3 = bool(close.iloc[-1] > s21.iloc[-1])
        c4 = bool(close.iloc[-1] > hist["open"].iloc[-1])
        delay = open_ts - sig_ts

        print(f"   signal bar  {bar_label.astimezone(CT):%H:%M} CT   "
              f"refetch vs logged: close diff {price_diff:.3f}, strength diff "
              f"{'-' if strength_diff is None else f'{strength_diff:.4f}'}")
        print(f"   close={close.iloc[-1]:.2f}  SMA55={s55.iloc[-1]:.2f}  "
              f"SMA21={s21.iloc[-1]:.2f}  prev_close={close.iloc[-2]:.2f}  "
              f"prev_SMA55={s55.iloc[-2]:.2f}  open={hist['open'].iloc[-1]:.2f}")
        print(f"   c1 close>SMA55: {'PASS' if c1 else 'FAIL'}   "
              f"c2 fresh cross: {'PASS' if c2 else 'FAIL'}   "
              f"c3 close>SMA21: {'PASS' if c3 else 'FAIL'}   "
              f"c4 bullish bar: {'PASS' if c4 else 'FAIL'}")
        late = delay.total_seconds() > 600
        print(f"   event: price={sig_ev.get('price')} strength={ev_strength}"
              f"   signal->fill delay: {int(delay.total_seconds() // 60)}m"
              f"{int(delay.total_seconds() % 60)}s"
              f"{'   ** LATE_FILL — stale signal repriced, see OPERATIONS.md **' if late else ''}")
        if c1 and c2 and c3 and c4:
            print("   VERDICT: SIGNAL_CONFIRMED")
            ok += 1
        elif not fingerprint:
            print("   VERDICT: DATA_DRIFT — today's bars no longer match what the "
                  "agent logged at scan time (live IEX bars settle late); the "
                  "logged price/strength are the agent's own numbers")
            data_drift += 1
        else:
            print("   VERDICT: CONDITIONS_NOT_REPRODUCED on matching data — investigate")
            problems += 1

    print(f"\n{ok} confirmed, {data_drift} data-drift (inconclusive post-hoc), "
          f"{problems} needing a look, of {len(rows)} open positions")


if __name__ == "__main__":
    main()
