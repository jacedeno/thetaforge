# Strategy Specification — ThetaForge

> Working spec. Parameters live in `agent/config.py`; this document explains the reasoning.

## Thesis

Two edges, stacked:

1. **Volatility risk premium** — options are systematically priced richer than realized
   volatility. Selling premium with defined risk harvests this (documented across decades:
   CBOE PUT/BXM indices, tastytrade research).
2. **ML momentum overlay** — an SMA55/21 crossover system with years of validated equity
   backtests on the most liquid S&P 500 names provides the directional tilt, so we sell
   premium on the side the market is leaving.

## Signal → structure mapping

| Signal | Structure | Short leg |
|---|---|---|
| LONG | Put credit spread | ~25-delta put |
| SHORT | Call credit spread | ~25-delta call |
| NEUTRAL (high IV rank) | Iron condor | ~16-delta both sides |

## Entry rules

- Universe: liquid S&P 500 names with options chains passing liquidity gates
  (open interest ≥ 500/leg, bid-ask ≤ 10% of mid).
- Expiry: 7–21 DTE at entry.
- Spread width: $5 (adjust per underlying price).
- One position per underlying; max 10 open positions.

## Exit rules

- **Profit target:** buy back at 50% of collected credit.
- **Stop:** close when loss reaches 2× collected credit.
- **Time stop:** close or roll at 2 DTE — never carry into expiration/assignment.
- **Signal flip:** an opposing ML30 signal on the underlying closes the position.

## Position sizing

Max risk per position (width − credit) ≤ 2% of account equity.
Total buying-power usage ≤ 50%.

## Open questions (resolve during dev-account testing, Aug 24–27)

- [x] Multi-leg order mechanics validated 2026-08-24 — see `alpaca-notes.md` (rejection modes still pending)
- [ ] Signal timeframe: 15m canonical vs 5m with confirmation
- [ ] Iron condor leg: enable at launch, or ship directional-only MVP first
- [ ] IV rank data source for the neutral branch

## Runbook (competition week)

```
herdr --session thetaforge     # persistent session for the agent
./scripts/run_loop.sh          # scan each 15m bar close + monitor exits every minute

herdr --session tf-dash        # persistent session for the dashboard
./scripts/run_dashboard.sh     # http://localhost:3777
```

Logs land in `logs/agent-YYYY-MM-DD.log`; the agent's decision trail in `logs/events.jsonl`.

**Public showcase:** https://thetaforge.geekendzone.net — served through a
Cloudflare Tunnel (zero inbound ports). Read-only: API keys live server-side
only; the page exposes no controls.
