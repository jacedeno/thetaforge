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
- [x] **Data feed decision** — RESOLVED 2026-08-28 by the official FAQ:
  the free tier (delayed SIP bars, indicative options feed) is explicitly
  permitted for the competition; paid tiers allowed but not provided. We
  stay on the free plan — the 15-min delay is an accepted property of the
  system (documented in the write-up's honesty about entry timing).
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
- [ ] **Chain symbols that fail to parse must be skipped, not fatal** —
  2026-08-28 kickoff-day incident: SPGI's chain carries corporate-action
  adjusted contracts under the suffixed root `SPGI1`; `parse_strike` read
  the `1` as a date digit and the ValueError killed the whole scan
  iteration (monitor pass included) every time SPGI signaled. Contained by
  removing SPGI from the universe (78 names). Fix: `_trace_candidates`
  skips symbols that don't parse as `root+YYMMDD[C/P]strike` (adjusted
  roots are never candidates), regression test with an `SPGI1` symbol in
  the fixture chain; then SPGI (and the same argument for BRK.B) can
  return. Details: OPERATIONS.md.
- [x] **First ~20 min of the day trade yesterday's close bar** — with the
  RTH filter plus the 15-min SIP delay, scans from 8:30 to ~8:50 CT see
  yesterday's 14:55 CT bar as "latest" and fire its signals (6 on
  2026-08-28, all vetoed by open-hour option liquidity — protection by
  luck, not by design). RESOLVED 2026-08-30: `max_signal_bar_age_s=1800`
  — a signal bar that closed more than 30 min ago is treated exactly like
  a down feed (no order, narrated veto in the event feed). Age is measured
  from the bar's CLOSE (labels are window starts). Regression tests in
  `tests/test_signal_age.py` replay the exact Friday scenario. Prompted by
  a build-in-public exchange: "reachable and lying is the expensive case."
- [ ] **The credit floor lets in spreads that cannot be closed** — found
  2026-08-31, first day of the judged window. The entry gate accepts a credit
  of $0.15 on a $1-wide spread (15% of width, over the 12% floor). The 50%
  profit target on that credit is **$0.075**, which sits below the price at
  which a penny-quoted spread can actually be bought back. PFE was entered at
  0.15, reached its target, and the monitor tried to close it **47 times
  without a single fill** — correctly refusing to overpay, but retrying every
  pass instead of backing off. Four of the day's fifteen positions are in this
  class (PFE, CMCSA, NFLX, VZ, all $1-wide with credits of 0.15–0.19); the
  $5-wide spreads on expensive underlyings target $0.40–0.55 and close fine.
  **The asymmetry is the real defect: the stop (2x credit, ~$0.30) IS
  reachable while the profit target is not**, so a thin spread can take its
  loss early but not its win. Fix belongs at entry, not exit: require the 50%
  target to clear $0.15, i.e. a **minimum credit of $0.30**, which excludes all
  four of the day's thin trades and none of the good ones. Not shipped during
  the competition — the book is full at 15/15 so the gate barely fires again,
  and none of the four is losing money. Retrying 47 times a day is noise, not
  cost; a back-off after the first unfilled attempt is the cosmetic half.
- [ ] **Equity read after the close is not the equity at the close** —
  2026-08-31: the account showed **98,703 at the bell and 96,653 forty minutes
  later**, with no trade in between. Option market makers pull their quotes at
  the close and the marks widen against every position (CAT's short leg quoted
  6.38/9.53, three dollars wide). Two consequences. First, **read equity from
  the portfolio-history snapshot at 20:00 UTC, never from a live account call
  after the bell** — a post-close number overstates the loss by ~2% of the
  book. Second, mark-vs-mid: the same fifteen positions were **-3,340 at the
  broker's marks and -905 at the midpoint**, so $2,435 of the reported loss was
  the bid-ask of opening a full book in one session, not economics. This is the
  write-up's honesty section showing up as a measurement problem, and it argues
  for **holding the book through Thursday rather than closing it** — closing
  pays the exit spread on fifteen positions to convert marks that the bell
  snapshot already reports fairly.
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
