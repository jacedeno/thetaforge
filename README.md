# ThetaForge

**An autonomous AI trading agent that redirects a battle-tested ML momentum model into defined-risk options structures.**

Built for the [Alpaca AI Trading Agents Hackathon](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon) (Aug 28 – Sep 4, 2026).

> **Status (Sep 2026):** the hackathon window is closed — four judged sessions,
> final equity −1.9%, every trade placed and managed by the agent. The system
> now runs in caretaker mode over its open book while its next role is decided.

## The idea

Most options bots pick a structure first and hope for direction. ThetaForge does the opposite: a machine-learning momentum model (SMA55/21 crossover system, validated over years of equity backtests on the most liquid S&P 500 names) decides **where** and **which way** — and the agent expresses that view through **premium-selling structures with defined risk**:

- Bullish signal → sell a **put credit spread** on the underlying
- Bearish signal → sell a **call credit spread**
- No directional edge → collect theta with a neutral **iron condor**

The volatility risk premium does the heavy lifting; the ML model tilts the odds on direction. Every position has a hard max loss by construction.

## Architecture

```
signals/     ML momentum signal engine (liquid S&P 500 universe)
options/     Chain analysis, strike/expiry selection, spread construction
risk/        Risk gates: position sizing, buying-power caps, stops, profit targets
execution/   Order routing through Alpaca (Trading API + MCP server / CLI)
dashboard/   Next.js dashboard: live positions, P&L, Greeks, trade log
```

## Stack

- **Trading:** Alpaca Trading API · Alpaca MCP server · Alpaca CLI · paper trading environment
- **Agent:** Python 3.13 · alpaca-py
- **Dashboard:** Next.js · shadcn/ui · ECharts · lightweight-charts

## Dashboard

The dashboard is the agent's public window — and its **audit instrument**. Every
element exists so the strategy can be inspected and adjusted between sessions:

- Candle charts drawn with the signal's own moving averages (SMA21 blue,
  SMA55 orange, the exact parameters the trigger uses), in the viewer's timezone.
- A **SIGNAL** marker on the bar where the trigger fired and a **SELL** marker
  where the position actually filled — the gap between them is the execution
  audit (signal→fill latency is a tracked metric).
- Expanded positions show the full payoff curve with breakeven, take-profit and
  stop levels, the live spot on the curve, and entry details from the journal.
- Trade history comes straight from the SQLite journal, with provenance: orders
  not placed by the agent are badged `manual` and excluded from performance stats.
- The "agent brain" feed narrates every scan, signal, veto and order in plain
  language, from the same event log the agent writes.

For the competition the dashboard is strictly **read-only visualization**: API
keys live server-side only and the page exposes no controls. The natural next
step is closing the loop — introducing strategy variables (delta band, credit
floors, exit thresholds) from the dashboard itself, gated behind the same
preflight discipline that already guards every agent start.

## Risk management

- Defined-risk structures only — no naked short options, ever
- Max risk per position capped as a fixed % of buying power
- Profit target at 50% of collected credit; stop at 2× credit
- Liquidity gates on every chain (open interest, bid-ask width) before entry

## Running

```bash
cp .env.example .env   # add your Alpaca paper API keys
uv sync
uv run python -m agent.main
```

## Pre-event work disclosure

Per the hackathon FAQ, pre-event work must be disclosed: this repository was
created and developed in the days before the August 28 kickoff — the git
history is public and tells the story commit by commit. Prototyping and a
burn-in week ran on separate testing paper accounts, as the rules permit.
Official competition trading happens exclusively in the dedicated $100,000
paper account, which placed its first order inside the official scoring
window (Monday, August 31, 9:30 a.m. ET onward). The underlying momentum
rule comes from the author's prior backtesting research; the agent, its
options workflow, risk gates, journal and dashboard are the work submitted.

## Disclaimer

This project trades exclusively in Alpaca's **paper trading environment** with simulated funds. Nothing here is financial advice.
