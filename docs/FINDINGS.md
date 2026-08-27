# Findings backlog — burn-in 2026-08-27

> The working list. Each item gets checked off as it ships; the full stories
> live in [`OPERATIONS.md`](OPERATIONS.md). Rule 3 governs WHEN each class of
> change may land (trading logic through preflight, dashboard/docs any time).

## Trading logic (through preflight, after close / P&L-threatening window)

- [ ] **Reprice age cap** — a stale order older than ~10 min is cancelled
  WITHOUT reprice; its signal died with it. Root cause of the 2-hour
  COP/JPM/BA entries of 2026-08-26 (`LATE_FILL` in `verify_entries.py`).
- [ ] **OCC root normalization** — `parse_strike` and every signal-symbol vs
  OCC-root comparison must map dotted tickers (`BRK.B` → `BRKB`), with a
  regression test. BRK.B rejoins the universe only after this lands.
  (Crashed the scanner in a 65-second loop at the 2026-08-27 open.)
- [ ] **Data feed decision** — the agent's bars are free-plan SIP: complete,
  but minus the last 15 minutes, so every "5-minute" signal fires 15–20 min
  after its bar. Decide: pay for real-time SIP · switch the signal to
  real-time IEX (thin bars — AAPL premarket had 1-trade candles) · accept
  the delay as part of the system.
- [ ] **Pre-market trigger bars** — with the SIP delay, the day's first scans
  evaluate pre-market bars (AAPL's 2026-08-27 trigger bar was 8:25 CT).
  Decide whether the trigger requires regular-hours bars.
- [ ] **Sizing experiment 15 × 1.5%** — retuned 2026-08-27 midday from
  10 × 2% (first to 13, then 15 at Jose's call: 22.5% aggregate, upper half
  of the canonical band; the old cap had vetoed 14 signals that morning).
  Measure with
  `scripts/veto_summary.py`: veto counts by reason, especially "max open
  positions" and risk-budget rejections, and compare results before locking
  for competition week.
- [ ] **`max_signal_strength` 0.02** — raised from 0.012 for the 5m burn-in
  (on 5m the ceiling mostly vetoes opening-gap crosses). Review with the
  live signal data (`sma55`/`sma21`/`bar_time` now logged per signal) and
  lock the value for competition week.
- [ ] **Selector hardening, deferred half** — delta-vs-price plausibility
  check and short-leg minimum bid (deliberately not shipped 2026-08-26).
- [ ] **Same-expiry spread collapse** — `reconstruct_spreads` keys legs by
  (root, expiration, kind); two same-expiry spreads on one underlying merge
  and `avg_entry_price` averages their fills. Mitigated (journal credit is
  preferred; entry gates block the doubling); structural fix pending.
- [ ] **Spread-level inverted-cost guard** — at the 2026-08-27 open BA's
  legs quoted uncrossed individually but the SPREAD was inverted
  (long mid > short mid → cost −1.15); `evaluate_exit` read it as a profit
  target and parked an unfillable 0.02 close. Guard: `cost <= 0` means the
  quotes are garbage → HOLD, never a profit target.
- [ ] **Exit-order chase** — exits are exempt from stale cancels by design,
  so an unfilled close limit rests forever while its position sits
  unmanaged (COP's stop rested 3 h; the operator reset needed up to three
  re-prices per spread to fill). Mirror the entry logic: an unfilled exit
  older than ~2–3 min is cancelled and re-placed at the fresh natural —
  the position must never be left without a working exit.

## Cosmetic / observability (any time)

- [ ] `run_scan.py` emits `universe=80` hardcoded — emit `len(symbols)`
  (the universe is 79 since BRK.B left).
- [ ] `ml30.fetch_bars` docstring still says "15-minute bars" (code is 5-min).

## Post-competition

- [ ] **Dashboard-side strategy variables** — delta band, credit floors,
  exit thresholds tunable from the dashboard, gated behind preflight.
  (For the competition the dashboard is read-only visualization.)
- [ ] **Signal → long-call overlay experiment** — same ML30 trigger, long
  call instead of a put credit spread. Backtest it from the agent's own
  instrumented signal events (exact price and bar per signal) and compare
  the two structures in aggregate — win rate, expectancy, drawdown — not
  on cherry-picked days. Motivation (2026-08-27): on the day's three open
  positions a call would have been 1 clear win (AAPL +1.41%), 1 wash
  (GOOGL +0.23% ≈ theta + spread), 1 loss (BAC −0.14%), while the spreads
  were green or flat on all three — the structures pay off in different
  scenario mixes, so the comparison must be aggregate.

## Shipped during the burn-in (for context)

- [x] Exit-band absolute floors; unmanageable-credit HOLD; exit-limit
  floor/width cap; dry-run gating of cancels and reprices (2026-08-26)
- [x] One `entry_credit` definition (leg fills → journal → monitor and
  dashboard); trade provenance `agent|manual`, manual excluded from stats
- [x] Selector: crossed quotes rejected, open interest enforced, penny
  rescue closed, `entry_limit` logged
- [x] Signal instrumentation (`sma55`/`sma21`/`bar_time` per signal) +
  `scripts/verify_entries.py` + `scripts/diagnose_trade.py`
- [x] Dashboard audit view: SMAs (21 blue / 55 orange), SIGNAL/SELL/CLOSE
  markers, per-timeframe default ranges, local-time axes, SIP feed matched
  to the agent's data, 5m default on positions
