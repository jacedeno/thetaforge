# ThetaForge — Build Plan & Status

> Alpaca AI Trading Agents Hackathon · Aug 28 – Sep 4, 2026
> Live: https://thetaforge.geekendzone.net

## Status — end of day Aug 24 (T-4 to kickoff)

### Done

**Agent (Python)**
- [x] ML momentum signal engine — SMA55/21 triple-confirmation trigger, 15-minute bars, 80-name liquid S&P 500 universe, signals ranked by breakout strength
- [x] Options structure selection — ~25Δ put credit spreads, 7–21 DTE, per-leg liquidity gates (open interest, bid-ask width)
- [x] Risk gates — ≤2% equity risk per position, buying-power caps, position limits, per-scan entry cap
- [x] Multi-leg execution via Alpaca (validated live on paper: mleg orders, negative-limit credit convention, idempotency keys)
- [x] Position monitor — exits at 50% profit target / 2× credit stop / 2 DTE time stop, precedence-ordered
- [x] Continuous loop — scan on each 15m bar close, monitor every minute, heartbeat, survives market-closed periods
- [x] Trade journal — SQLite; reconciles broker fills into round trips, enriched with signal strength and exit reason
- [x] Structured event log (`events.jsonl`) — every scan, signal, veto, order, exit
- [x] Test suite: 17 tests (gates, monitor exits, journal pairing)

**Public showcase (Next.js)**
- [x] Live dashboard: equity curve, KPI tiles, open positions with per-spread payoff diagrams
- [x] Agent brain — live decision feed rendered from the event log
- [x] Trade history — per-trade stats header, WIN/LOSS rows, expandable options-aware candlestick (entry/exit markers, strike + breakeven price lines), daily P&L chart
- [x] Observability strip — agent heartbeat, market state, scan timing, uptime
- [x] Dark (default) and light themes; read-only by design
- [x] Published via Cloudflare Tunnel

### Remaining

- [ ] Tue Aug 25 — first full live day on the dev paper account; verify SPY test spread lifecycle; tune fills/limits
- [ ] Wed Aug 26 — video script; dashboard polish from live-data findings; one-page write-up draft
- [ ] Thu Aug 27 — demo video clips with real data; dry-run of full submission checklist
- [ ] Fri Aug 28 — create the competition paper account ($100k), point the agent at it, first trade on day one
- [ ] Aug 28 – Sep 3 — agent trades; build-in-public posts (X/LinkedIn, tagging @lablabai + @AlpacaHQ)
- [ ] Before Sep 4 10:00 CT — submit: repo, app URL, video, slides, write-up, account ID, social links

## Deliverables checklist (submission)

Public GitHub repo ✓ (this) · Application URL ✓ (live) · Video · Slides · Cover image ✓ ·
One-page write-up (AI logic, risk gates, Alpaca infra) · Alpaca paper account ID · up to 5 social posts
