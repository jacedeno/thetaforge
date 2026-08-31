# ThetaForge — One-Page Write-Up

> Hackathon deliverable: AI logic, risk gates, and Alpaca infrastructure.

## AI logic — intelligence in the right layers

ThetaForge deliberately splits "AI" into three layers, putting each kind of
intelligence where it earns its place:

**1. The model layer (machine learning, offline).** The directional signal is
an SMA55/21 triple-confirmation momentum trigger — not hand-picked, but
selected by a 3,600-backtest sweep across 120 strategy configurations on
liquid S&P 500 names. The learning happened at design time: the sweep decided
*which* rule carries edge; the agent executes that rule.

**2. The execution layer (deterministic, online).** The running agent is
deterministic Python: scan the 80 most liquid S&P 500 names on each 5-minute
close, take fresh momentum crosses that haven't already overextended (calmest
first), express them through ~25-delta put credit spreads (7–21 DTE), and
manage exits mechanically. Same input, same decision, every time — no hallucination risk
with live orders, millisecond latency, and every trade auditable down to the
four boolean conditions that triggered it.

**3. The operator layer (LLM, supervisory).** An LLM operator, connected
through Alpaca's MCP server, supervises the running system: it watches it
trade, diagnoses failures from the structured event log, and ships fixes —
during the test week it caught and fixed live: a fill-rate collapse from
mid-anchored pricing, a stale-order detector defeated by SDK enum
stringification, a scheduler that skipped scans, and a duplicate-position race.

The thesis: **an LLM inside the order loop adds variance exactly where
reliability is non-negotiable.** AI supervises and adapts; determinism
executes. The public "agent brain" feed narrates the deterministic decisions
in plain language — the intelligence is in the rules, the narration is
courtesy for the viewer.

## Why premium selling

P&L = volatility risk premium (structural: implied systematically exceeds
realized — CBOE PUT index, decades of evidence) + the momentum signal as a
tilt. The signal's job is modest: not predicting rallies, but avoiding selling
puts into breakdowns. A bullish fresh-cross marks names least likely to crash
over the spread's life; if the signal added nothing, the system degrades to
plain systematic premium selling — a documented, survivable floor. Win-rate
asymmetry does the rest: spreads profit if the underlying rises, stays flat,
or falls short of ~3–4%.

## An honest note on the scoring window

This strategy's edge is structural, not fast. Put credit spreads earn the
volatility risk premium over their 7–21 day life, and the win-rate asymmetry
needs tens of trades to express itself. A four-day equity snapshot samples
that process mid-flight: most positions will still be open at the closing
bell, marked at current quotes rather than at their expected value, so
short-window P&L is dominated by noise the system was never designed to
chase. We compete inside the window as it is — but the honest claim is that
this architecture is built to win over months, and what four days *can*
fairly judge is the part that doesn't need luck: autonomy, risk discipline,
and a fully auditable decision trail.

## Risk gates — every order passes all, one veto kills it

| Gate | Rule |
|---|---|
| Position risk | max loss (width − credit) ≤ **1.5% of equity** |
| Portfolio | ≤ 15 concurrent positions · ≤ 50% buying power · 1 per underlying |
| In-flight claim | a pending order reserves its underlying — no stacking |
| Entry quality | short-leg delta 0.15–0.32 · credit ≥ 12% of width · ≥ $0.15 |
| Chain liquidity | per-leg bid-ask tight in relative (≤25%) *or* absolute (≤$0.10) terms |
| Cadence | ≤ 3 new positions per scan · ≤ 1 per sector per scan, calmest signals first |
| Exits | 50% of credit → take profit · 2× credit loss → stop · ≤ 2 DTE → close, never carry to expiration |
| Order hygiene | unfilled entries cancelled at 3 min; one reprice at the market's natural price, never chase further |

Sizing sits inside the canonical band for short-premium systems (1–2% per
position, fractional-Kelly territory; aggregate worst case 22.5%).

## Alpaca infrastructure

- **Alpaca CLI** — the agent's execution layer: every entry, reprice, exit and
  cancel runs through `alpaca order submit/cancel` with structured JSON and
  idempotent client order ids; raw REST is an automatic fallback.
- **Trading API / alpaca-py + Market Data API** — 5-minute equity bars for
  signals, option chains with greeks for structure selection, live option
  quotes for exit pricing and mark-vs-mid honesty.
- **MCP server** — the AI operator's supervision channel: account, orders,
  chains and docs inspected through MCP during build and live operation.
- **Paper trading environment** — all of it, end to end.

**Why the order loop runs on the official SDK + CLI rather than through
MCP** (per the FAQ's request to justify SDK use): MCP is a conversational
tool interface — ideal for the supervising LLM, wrong for the money path.
Deterministic risk gates need typed responses, explicit error handling and
idempotent client order ids with no model in between, which is exactly what
the official `alpaca-py` SDK and the Alpaca CLI provide. So the split
mirrors the architecture itself: supervision through MCP, execution through
the official SDK and CLI.

Every decision lands in a structured event log and a SQLite trade journal
(broker fills joined with the agent's *why*: signal strength in, exit reason
out) — rendered live at the public dashboard with per-trade candlesticks,
strike lines, payoff diagrams and a real-time decision feed.
