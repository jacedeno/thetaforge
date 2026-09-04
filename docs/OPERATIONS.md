# Operations — How Changes Ship and How Failures Surface

> Written 2026-08-26 after a self-inflicted incident, so Friday can't inherit it.

## The incident that wrote these rules

While improving event readability mid-session, `parse_occ` was used in the
monitor without its import. The loop's blanket `except` swallowed the
NameError **109 times in a row**: no stale cancels, no exit evaluation, no
journal — for an hour, silently. Three zombie orders filled unmanaged. Every
individual bug that week had been caught by looking; this one showed that
looking doesn't scale.

## The second incident — the "bot trade" that wasn't (2026-08-26)

A SPY 700/695 spread appeared on the dashboard: entered at a 0.03 credit,
closed 16 seconds later for −$3.00. The review it triggered produced a full
bug hunt on another machine — and then the order tape ended the mystery in
one line: `client_order_id = tf-smoke-cli-001`. A hand-typed CLI smoke test,
submitted 46 seconds before the commit that routed execution through the
CLI. The −$295 close of the doubled HD position that morning was also manual
(limit 1.43 while the loop was logging HOLD at cost ~1.12, no exit_signal).
Neither order passed through a single agent gate — and both landed in the
journal, the stats and the public P&L as if the agent had decided them.

The generalized lesson, twice now: *every threshold expressed as a multiple
needs an absolute floor, and every number the system believes needs a sanity
check before it is believed* — including "this trade was ours".
`scripts/diagnose_trade.py` now adjudicates any trade against four sources
(journal, order tape, event log, live monitor) and prints verdict flags;
the journal records provenance per trade (`source = agent | manual`, from
the client_order_id namespace) and manual rows are excluded from the
dashboard's performance stats.

## Rule 1 — Preflight gates every start

`scripts/run_loop.sh` refuses to launch unless `scripts/preflight.sh` passes:

1. Full test suite (includes an AST name-resolution check on the
   monitor born from the incident above)
2. A **real dry monitor pass** against the live API — imports, broker reads,
   stale scan, quote fetch and exit evaluation, end to end

A change that would crash in production now crashes on the launchpad.
There is no way to start the agent around the gate.

## Rule 2 — The system announces its own sickness

The heartbeat carries `consecutive_failures`; the public status strip shows
three states: **AGENT LIVE** (green, pulsing) · **AGENT DEGRADED** (amber,
≥3 straight failed passes — beating but broken) · **AGENT DOWN** (red, no
heartbeat). Detection no longer depends on a human noticing odd behavior.

## Rule 3 — Freeze schedule for the competition

| When | What is allowed |
|---|---|
| Wed (today) after close | Last trading-logic changes, all through preflight |
| **Thu** | **Code freeze.** Full-session burn-in, zero edits. Parameters only if a burn-in finding demands it — via preflight, before open or after close, never midday |
| Fri 8:00 | Account swap only (`.env` + restart through preflight). No other change |
| Competition week | Dashboard/docs may change (they don't trade). Agent code: only for a P&L-threatening defect, with tests, through preflight |

## Account swap checklist (competition start — after the kickoff, per the
## Discord moderators: "start after kick off", confirmed 2026-08-27)

**FAQ update caught 2026-08-30 (re-read of the Google Doc):**
- **The judged number is total equity as of EOD Thursday, Sep 3** — stated
  twice ("we will be looking at the portfolio's total equity as of EOD
  Thursday Sep 3rd"), even though the window formally ends Friday 9:30 ET.
  Operator plan: have the book in its best shape by Thursday's close, and
  consider closing positions Thursday afternoon so the judged equity is
  cash, not end-of-day option marks (closing quotes mark pessimistically).
- **Pre-event work must be disclosed** in the README/submission — done,
  see README "Pre-event work disclosure".
- Also confirmed: no scoreboard · no risk-adjusted metrics (raw total
  equity) · backtests/simulated shocks welcome in the write-up as guardrail
  evidence · repo may stay private (ours is public by choice) · no strategy
  or model-provider restrictions · free-plan option QUOTES are real-time
  (the 15-min restriction is historical bars/trades only) · hosting not
  required.

**Official FAQ (Alpaca/lablab Google Doc, published 2026-08-28 afternoon):**
- **Official P&L window: Mon Aug 31 9:30 ET → Fri Sep 4 9:30 ET.** The
  agent "should begin trading from this account on Monday, August 31 at
  9:30 a.m. ET"; judges snapshot **total equity** (not cash) at the close.
- Consequence: the account swapped in on Friday noon traded pre-window
  (2 spreads) — Jose's call: let it run as a full-day live test, create
  the FINAL competition account after Friday's close, swap with the market
  closed, and let the clock guard deliver the first trade Monday 9:30 ET.
- **UI not required** (dashboard is scoring upside, not a requirement).
- **Free market data explicitly permitted** (indicative options feed);
  Algo Trader Plus/OPRA allowed but not provided.
- P&L "an important factor, but winners will not be selected on P&L
  alone" — creativity, autonomy, robustness of the workflow are judged.

**Official conditions (kickoff email, lablab.ai, 2026-08-28):**
- Final submission must run on a **brand-new paper account created for the
  hackathon** — an existing or reused account is not eligible for judging.
- Starting balance **set to $100,000**. Create it as soon as possible so the
  trading history is clean from minute one.
- The **paper account ID goes in the submission** — that is how judges read
  the P&L. One-page write-up required (AI logic, risk gates, Alpaca infra)
  — `docs/WRITEUP.md` covers exactly this.
- Requirements confirmed: autonomous agent on the Trading API, must use the
  MCP server or CLI (we use both), strategy must incorporate options. Main
  track: "Options Alpha Agents" — P&L over the competition window.
- Optional: social prize (2 × $500) for build-in-public posts on X/LinkedIn
  tagging @lablabai and @AlpacaHQ — up to 5 post links with the submission.

**EXECUTED TWICE 2026-08-28 — the second one is final.**
- ~12:00 CT: swapped to a fresh $100k account right after the kickoff.
  The official FAQ (published that afternoon) then fixed the scoring
  window to Monday 9:30 ET, so that account became a sanctioned full-day
  live test (8 spreads opened; archived as `archive/testday-account-*/`,
  positions abandoned, keys in its `env-*.bak`).
- ~15:15 CT, market closed: swapped to the OFFICIAL competition account —
  same procedure both times: account verified via the API first ($100k
  exact, options level 3, ACTIVE), keys into both envs, preflight PASS
  (61 tests + smoke), fresh journal/logs, single-tree restart, dashboard
  re-serving the new account. The loop now no-ops through the weekend on
  the clock guard and places its first order Monday 9:30 ET — inside the
  official window, untouched $100k, by construction rather than by timing
  discipline. Keys registered in the credentials store. Account IDs live
  in the submission and the credentials store only — never in this
  public repo.

1. Read the released conditions FIRST — account requirements, judged
   window, capital. Only then create/reset the competition paper account.
2. New keys into `.env` (agent) and `dashboard/.env.local` (dashboard).
   Keep `ALPACA_DATA_FEED=sip` in the dashboard env.
3. `bash scripts/preflight.sh` — must PASS against the new account.
4. Restart the loop (kill the tree with LITERAL pids — zsh does not split
   `$pids` — then `setsid nohup ./scripts/run_loop.sh &`) and the dashboard
   (`run_dashboard.sh`). Verify exactly ONE agent tree.
5. Verify: heartbeat healthy, dashboard shows the NEW account number,
   `data/thetaforge.db` starts empty for the new account (archive the
   burn-in db/logs to `archive/` like the dev account).
6. One full monitor cycle in the log before walking away (Rule 4).

## Rule 4 — Change discipline (standing)

Every agent change, however small: tests → preflight → restart → watch one
full monitor cycle in the log before walking away. "It's just a log line"
was exactly the change that took the system down.

## Operator reset, 2026-08-27 ~11:30 CT (sanctioned)

Jose's call: the six positions opened under the retired 15-minute regime
(COP, BA, CMG, JPM, NFLX, XOM) carried no informational value for the 5m
burn-in and were consuming 6 of the 10 position slots — `max open
positions` had already vetoed 14 signals that morning. All six were
liquidated at the natural price (`tf-reset-*` client ids, `order_close`
events carrying the reason, so journal, stats and the brain feed tell the
story truthfully), together with two stuck close orders that were blocking
BA and COP from monitor management (see the inverted-cost and exit-chase
findings in FINDINGS.md). Realized cost of the reset: −$3,126 across the
six. This is the sanctioned shape of an operator action: explicit ids,
logged reasons, documented here — the opposite of a silent smoke test.

## Rule 5 — No manual orders on the live account

The competition account's P&L is the judged artifact; one hand-typed order
contaminates it. Smoke tests and CLI experiments run against the dev account
(see `archive/dev-account-*/`), never the live paper account. If an
out-of-band order is ever unavoidable, keep its client_order_id outside the
`tf-open-*` / `tf-retry-*` namespace so the journal tags it `manual` and the
stats ignore it.

## Burn-in incident, 2026-08-27 09:00 CT — BRK.B crash loop

Minutes after the open, `parse_strike` crashed on BRK.B: its OCC option
symbols use the dotted-root stripped form (`BRKB...`), while the selector
slices `len("BRK.B")` characters off the symbol. The exception escaped
mid-scan, the scan slot never latched, and the loop re-ran the scan every
~65 s (DEGRADED, `consecutive_failures` climbing) — with every signal
stronger than BRK.B's blocked behind the crash. Contained at parameter
level within minutes (BRK.B removed from `universe.json` — it had entered
in the 2026-08-26 universe expansion and fired its first signal today),
restart through preflight, clean single scan on the next slot. Code fix
scheduled below.

## Kickoff-day incident, 2026-08-28 08:45 CT — SPGI adjusted-contract crash

Same class as BRK.B, new variant: SPGI's option chain carries
corporate-action-adjusted contracts under a **numeric-suffixed root**
(`SPGI1...`), so `parse_strike` — which slices `len(occ_root("SPGI"))`
characters — read the adjusted root's `1` as the first digit of the date
and died on `ValueError: month must be in 1..12, not 60`. Every scan where
SPGI signaled aborted the whole iteration (4 crashes 08:45–08:49, ~65 s
retry cadence, monitor pass skipped each time; one more at 09:01).
Contained at parameter level 09:04 CT during the morning audit: SPGI
removed from `universe.json` (78 symbols — hot-reloaded, `load_universe()`
runs per scan, no restart needed). Next scan 09:05:42 clean. Code fix for
after the close: the candidate loop must *skip* chain symbols that fail to
parse (adjusted roots are never tradable candidates for us) instead of
letting one bad symbol kill the scan — with a regression test; SPGI
returns to the universe only after that lands, and BRK.B's `occ_root` fix
alone was not sufficient because it never anticipated suffixed roots.

> The actionable checklist distilled from these findings lives in
> [`FINDINGS.md`](FINDINGS.md) — work through it there.

## Scheduled for after the close, 2026-08-27 (burn-in findings)

**OCC root normalization.** `parse_strike` (and every comparison between
signal symbols and OCC roots — `held` sets, duplicate gates) must map
dotted tickers to their OCC root (`BRK.B` → `BRKB`), with a regression
test. BRK.B returns to the universe only after that lands.

**The agent's bars are SIP, delayed 15 minutes.** Caught auditing the AAPL
entry (2026-08-27): the signal `bar_time` runs consistently 15–16 min
behind the scan, and the signal bar's close (310.59) exists only on the
SIP feed — the free plan serves full SIP history minus the most recent
15 minutes. Consequences to review after the close: (a) every "5-minute"
signal actually fires 15–20 min after its bar — decide between paying for
real-time SIP, switching the signal feed to real-time IEX (thin bars), or
accepting the delay as part of the system; (b) the first scans of the day
evaluate PRE-MARKET bars (AAPL's trigger bar was 8:25 CT) — decide whether
the trigger should be restricted to regular-hours bars. The dashboard now
charts the same SIP feed (`ALPACA_DATA_FEED=sip` in `dashboard/.env.local`)
so the drawn SMAs reproduce the agent's numbers exactly — auditing the
agent on IEX charts was comparing two different markets.

The stale-order reprice re-enters at the natural price **without
re-validating the signal's age** — it checks only the credit floor and
duplicate positions. Under a healthy monitor the stale→reprice chain lasts
3–6 minutes and is tolerable; on 2026-08-26 the morning's restarts kept the
monitor down, and its first healthy pass (12:52 CT) swept and repriced
every accumulated stale order at once — COP, JPM and BA filled with signals
up to **two hours old**, the day's worst entries. Fix, to ship after
today's close through preflight: *a stale order older than ~10 minutes is
cancelled without reprice* — its signal died with it. Until then the
pattern is watched: `scripts/verify_entries.py` flags any signal→fill
delay over 10 minutes as `LATE_FILL`.

Known limitation (documented, not fixed): `reconstruct_spreads` pairs legs
by (root, expiration, kind), so two same-expiry spreads on one underlying
collapse into a single pair, and the broker's `avg_entry_price` averages
across both fills — observed 2026-08-26 on the doubled HD position as a 4¢
credit drift. The monitor now prefers the journal's fill-derived credit,
which sidesteps the averaging; the entry gates prevent the doubling itself.

## Change record, 2026-08-30 (evening) — stale signal-bar guard shipped

The open item from Friday ("first ~20 min of the day trade yesterday's
close bar") went to production tonight, before the Monday open:

- `max_signal_bar_age_s = 1800` in `StrategyConfig`. A signal whose bar
  **closed** more than 30 minutes ago is dropped before the spread builder
  runs, with a narrated `veto` event ("stale data treated as down"). Age is
  measured from bar close, not the label — bar labels are window starts.
- Rationale: the API answering with old data is the more expensive failure
  than the API being down, because nothing errors. Friday's six
  stale-bar signals were stopped only by the option-liquidity gates —
  protection by luck. Monday's first judged scan must not depend on luck.
- Freeze-rule justification: P&L-threatening defect (an overnight-gap
  entry from yesterday's bar could be the first judged trade). Change is
  minimal: one pure helper + one filter + 5 regression tests
  (`tests/test_signal_age.py`, replaying the exact Friday scenario).
- Shipped through the standard gate: 66/66 tests, preflight PASS, loop
  restarted 19:01 CT with the market closed (clock guard no-op). Single
  process tree verified.

## Thursday close-out plan, decided 2026-08-31 (Jose)

The judged number is total account equity as of EOD Thursday, Sep 3. The
strategy holds spreads 7-21 days, so at any snapshot most of the book would
be marked at closing option quotes — pessimistic marks, not realized value.
Decision: **close all positions Thursday afternoon, before the 15:00 CT
bell**, so the judged equity is cash. This is a sanctioned operator action
(documented here per Rule 5's exception process), to be executed with Jose's
confirmation in the moment: review the book ~13:30 CT, close with
reasonable limits through the agent's exit path, verify a flat book, record
the final equity. Our expiries are all Sep 7 or later, so the FAQ's note
about Sep 3rd exercises/assignments does not touch us.

## Window close-out, 2026-09-03 (recorded 18:30 CT)

**Final judged equity: $98,085.40 (−1.91%)** as of EOD Thursday, Sep 3.
By session: Mon −1,309 · Tue −1,316 · Wed −1,025 · Thu **+1,736**.

The Aug 31 plan above (flatten before Thursday's bell) was superseded by
the 2026-09-01 hold decision: stop loss off inside the window, targets and
time stop on, losers ride. That call earned its keep on the last day — the
Thursday rebound recovered +1,736 against a book that a Wednesday flatten
would have crystallized near the lows. Entries were frozen for the final
session (2026-09-02, `max_new_positions_per_scan = 0`): with the book at
its 15-position cap, the only possible entry was refilling a slot freed by
a profit target, all delta and no theta at that horizon.

**ThetaForge is not the final hackathon submission** — a sibling system
finished the window better positioned and takes the slot. This repo stands
as what it is: four judged sessions of a premium-selling book run entirely
by the agent, including a same-day recovery from a host reboot (boot hook
added and tested that afternoon).

**Post-window status: caretaker mode.** The agent keeps running to manage
the open book — 15 spreads, expiries Sep 11 and Sep 18 — with entries still
at zero, profit targets and the time stop live, and the stop loss still
OFF. Both RESTORE notes in `agent/config.py` now gate the system's next
role, whatever that turns out to be: no new deployment starts without
entries back at 3 and the stop loss back on.

## Operator liquidation, 2026-09-04 08:45–08:53 CT (sanctioned — the relaunch)

The post-hackathon caretaker book was flattened for the relaunch on a
smaller account: 14 spreads closed through `scripts/close_book.py` (the
scripted form of the 2026-08-27 reset — natural-price limits capped at the
width, `order_close` events with reason `operator_relaunch`, loop stopped
first). Equity $97,557.32 marked → **$97,528.47 all cash**: the entire
liquidation cost ~$29 against the marks, and MU closed below its entry
credit — in profit.

Two operational notes, both now folded into the script:
- An unfilled close must be cancelled and re-priced at the fresh natural
  each pass, not waited on — HD's legs quoted $1.40 wide and its natural
  outran three resting limits before a padded cross (3.76 vs width 5.00)
  took it out.
- 11 of 14 filled on the first natural within seconds; wide-quoted
  deep-ITM spreads are the only ones that chase.

The account is **flat and frozen as the hackathon archive**. The loop is
STOPPED (nothing to manage, entries at zero). The reboot hook would harmlessly
restart it against the flat account until the relaunch swaps the keys.
