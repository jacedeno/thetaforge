# Operations — How Changes Ship and How Failures Surface

> Written 2026-08-26 after a self-inflicted incident, so Friday can't inherit it.

## The incident that wrote these rules

While improving event readability mid-session, `parse_occ` was used in the
monitor without its import. The loop's blanket `except` swallowed the
NameError **109 times in a row**: no stale cancels, no exit evaluation, no
journal — for an hour, silently. Three zombie orders filled unmanaged. Every
individual bug that week had been caught by looking; this one showed that
looking doesn't scale.

## Rule 1 — Preflight gates every start

`scripts/run_loop.sh` refuses to launch unless `scripts/preflight.sh` passes:

1. Full test suite (33 tests, includes an AST name-resolution check on the
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
