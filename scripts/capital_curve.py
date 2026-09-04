"""Capital curve: what does each funding level buy, with the account as risk capital.

Frames the relaunch question of 2026-09-04: capital C split into N equal slots
of C/N; an opportunity fits if closing collateral for ONE contract — 
(width - credit) x 100 — fits the slot. Width follows the live selector's own
rule (1.2% of spot, floored at $1, capped at $10) snapped to the standard
strike grid, so the estimate matches what the agent actually traded.

Evidence: every `signal` event ever logged (current account + all archived
accounts), taken and vetoed alike — the full opportunity stream — plus the
real trades in each journal as the sanity check.

    uv run python scripts/capital_curve.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

WIDTH_GRID = [1.0, 2.5, 5.0, 10.0]
CREDIT_FRACTION = 0.18   # typical credit/width from the real fills (sanity-checked below)


def est_width(spot: float) -> float:
    target = min(max(0.012 * spot, 1.0), 10.0)
    return min(WIDTH_GRID, key=lambda w: abs(w - target))


def est_risk(spot: float) -> float:
    w = est_width(spot)
    return round(w * (1 - CREDIT_FRACTION) * 100)


def main() -> int:
    # -- opportunity stream: every signal, deduped per symbol x day ----------
    events_files = [ROOT / "logs" / "events.jsonl"]
    events_files += sorted(ROOT.glob("archive/*/events*.jsonl"))
    opps: dict[tuple[str, str], float] = {}   # (symbol, day) -> spot
    for f in events_files:
        for line in f.open():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("type") == "signal" and e.get("price"):
                opps[(e["symbol"], e["ts"][:10])] = float(e["price"])
    if not opps:
        print("no signal events found"); return 1

    risks = {k: est_risk(spot) for k, spot in opps.items()}
    by_symbol: dict[str, float] = {}
    for (sym, _), r in risks.items():
        by_symbol[sym] = max(by_symbol.get(sym, 0), r)

    print(f"opportunity stream: {len(risks)} symbol-days, {len(by_symbol)} symbols, "
          f"{len(events_files)} event files\n")

    # -- sanity check: real fills vs the estimate ---------------------------
    print("sanity check — real trades (journal) vs estimated collateral:")
    dbs = [ROOT / "data" / "thetaforge.db"] + sorted(ROOT.glob("archive/*/thetaforge.db"))
    diffs = []
    for db in dbs:
        con = sqlite3.connect(db); con.row_factory = sqlite3.Row
        for t in con.execute(
            "SELECT underlying, short_strike, long_strike, entry_credit FROM trades "
            "WHERE short_strike IS NOT NULL AND long_strike IS NOT NULL"
        ):
            width = abs(t["short_strike"] - t["long_strike"])
            real = round((width - t["entry_credit"]) * 100)
            day_spots = [s for (sym, _), s in opps.items() if sym == t["underlying"]]
            est = est_risk(day_spots[0]) if day_spots else None
            diffs.append((t["underlying"], real, est))
        con.close()
    for sym, real, est in sorted(set(diffs)):
        mark = "" if est is None or abs(est - real) <= 0.35 * real else "  <-- off"
        print(f"  {sym:6} real ${real:>4}  est {'$'+str(est) if est else '(no signal logged)':>6}{mark}")

    # -- the curve ----------------------------------------------------------
    capitals = [3000, 4000, 5000, 6000, 8000, 10000]
    slots_n = [4, 6, 8]
    total = len(risks)
    print("\ncapital curve — % of historical opportunities that fit one slot (C/N):")
    print(f"{'C':>7} | " + " | ".join(f"N={n} (slot)      " for n in slots_n))
    for c in capitals:
        row = []
        for n in slots_n:
            slot = c / n
            fit = sum(1 for r in risks.values() if r <= slot)
            row.append(f"{fit/total*100:5.1f}% (${slot:>5.0f})")
        print(f"{'$'+format(c,','):>7} | " + " | ".join(row))

    # -- who falls out ------------------------------------------------------
    print("\nsymbols excluded at each slot size (max collateral seen per symbol):")
    for slot in [500, 750, 1000]:
        out = sorted(s for s, r in by_symbol.items() if r > slot)
        print(f"  slot ${slot}: {len(out)} out — {', '.join(out) if out else 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
