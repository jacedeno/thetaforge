# ThetaForge

**An autonomous AI trading agent that redirects a battle-tested ML momentum model into defined-risk options structures.**

Built for the [Alpaca AI Trading Agents Hackathon](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon) (Aug 28 – Sep 4, 2026).

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

## Disclaimer

This project trades exclusively in Alpaca's **paper trading environment** with simulated funds. Nothing here is financial advice.
