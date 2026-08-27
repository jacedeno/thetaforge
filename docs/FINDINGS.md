# Findings backlog — burn-in 2026-08-27

> The working list. Each item gets checked off as it ships; the full stories
> live in [`OPERATIONS.md`](OPERATIONS.md). Rule 3 governs WHEN each class of
> change may land (trading logic through preflight, dashboard/docs any time).

## Trading logic (through preflight, after close / P&L-threatening window)

- [x] **Reprice age cap** — SHIPPED 2026-08-27 post-close
  (`reprice_max_age_s: 600`): a stale order older than 10 min is cancelled
  without reprice; its signal died with it.
- [x] **OCC root normalization** — SHIPPED 2026-08-27 post-close:
  `occ_root()` in parse_strike, the duplicate gate, journal enrichment and
  the dashboard signal matcher, with regression tests. **BRK.B stays out of
  the universe for the competition** (Jose's call to re-add — its option
  chain is thin and would likely veto anyway; dashboard spot lookup for
  dotted roots is untested).
- [ ] **Data feed decision** — the agent's bars are free-plan SIP: complete,
  but minus the last 15 minutes, so every "5-minute" signal fires 15–20 min
  after its bar. Decide: pay for real-time SIP · switch the signal to
  real-time IEX (thin bars — AAPL premarket had 1-trade candles) · accept
  the delay as part of the system.
- [x] **Pre-market bars in the signal** — SHIPPED 2026-08-27 night. The
  finding turned out deeper than a preference: the 3,600-backtest sweep
  that validated V1-5m runs on RTH-only bars (`ml30-sp500-strategy
  data/alpaca_client.py`, "production / canonical"), while the live agent
  fed extended-hours bars into the SMAs and even triggered on a pre-market
  bar (AAPL). `fetch_bars` now filters to 09:30–16:00 ET — the live signal
  is the validated signal again — and the dashboard computes its SMAs on
  the same RTH-only tape (extended candles stay drawn, shaded, outside the
  indicator).
- [ ] **Sizing experiment 15 × 1.5%** — retuned 2026-08-27 midday from
  10 × 2% (first to 13, then 15 at Jose's call: 22.5% aggregate, upper half
  of the canonical band; the old cap had vetoed 14 signals that morning).
  Measure with
  `scripts/veto_summary.py`: veto counts by reason, especially "max open
  positions" and risk-budget rejections, and compare results before locking
  for competition week.
- [ ] **`min_open_interest` 500 — is it the right floor?** Enforced for the
  first time 2026-08-26 night (was documented but unimplemented). On
  2026-08-27 it was the sole killer of CSCO (5 signals; only candidate's
  legs at OI 319/277) and CAT (best credits of the day, 2.40–2.76 at
  c/w 0.24–0.28, every leg at OI 49–116) while their QUOTES passed the
  width gates. OI is a liquidity proxy; on $800 underlyings low OI with
  tight quotes is normal. Review with data: lower the floor (~150–250)?
  Or treat OI as secondary when the quote gates already pass? (DE stays
  correctly vetoed either way — its chain quotes $2–7 wide with no bids.)
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
- [x] **Spread-level inverted-cost guard** — SHIPPED 2026-08-27 post-close:
  `cost <= 0` in `evaluate_exit` is a garbage-tick signature → HOLD with a
  `quote_anomaly` event, never a profit target (BA's −1.15 open quote had
  parked an unfillable 0.02 close).
- [x] **Exit-order chase** — SHIPPED 2026-08-27 post-close
  (`exit_stale_after_s: 120`): an unfilled close resting past 2 min is
  cancelled and the same monitor pass re-decides at the fresh cost
  (`exit_stale` event). A position never sits unmanaged behind a resting
  limit again (COP's stop had rested 3 h).

## Cosmetic / observability (any time)

- [ ] `run_scan.py` emits `universe=80` hardcoded — emit `len(symbols)`
  (the universe is 79 since BRK.B left).
- [x] `ml30.fetch_bars` docstring said "15-minute bars" — fixed with the RTH
  filter change.

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
