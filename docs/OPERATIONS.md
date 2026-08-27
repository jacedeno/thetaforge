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

## Rule 4 — Change discipline (standing)

Every agent change, however small: tests → preflight → restart → watch one
full monitor cycle in the log before walking away. "It's just a log line"
was exactly the change that took the system down.

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
