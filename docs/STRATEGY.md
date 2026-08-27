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

- Universe: liquid S&P 500 names, 5-minute bars (the V1-5m live-validated variant) with options chains passing liquidity gates:
  - **open interest ≥ 500 per leg**, verified against the contracts endpoint at
    selection time — unknown OI rejects, never passes by default;
  - **bid-ask ≤ 25% of mid**, or ≤ $0.10 absolute for cheap-but-real contracts
    (the absolute branch requires a short-leg mid ≥ $0.20, so it can't rescue
    penny dust);
  - **crossed quotes (ask < bid) are rejected outright** — a bogus tick must
    never price a trade.
- Expiry: 7–21 DTE at entry.
- Spread width: $5 (adjust per underlying price).
- One position per underlying; max 13 open positions (retuned 2026-08-27
  from 10 × 2% to 13 × 1.5% — same aggregate envelope, more shots).

> Exits are unconstrained by day-trade limits: FINRA's PDT rule was eliminated
> 2026-06-04 and replaced by intraday margin, so a spread that hits its profit
> target the same session it was opened is closed immediately rather than held
> overnight to preserve a quota. See [`pdt-rule-change-2026.md`](pdt-rule-change-2026.md).

## Exit rules

- **Profit target:** buy back at 50% of collected credit.
- **Stop:** close when loss reaches 2× collected credit.
- **Absolute floor** (`min_exit_band_usd`, $0.10): both thresholds above must
  sit at least $0.10 away from the entry credit — on a penny credit the
  relative band is narrower than ordinary quote flicker. A credit so small
  that no floored profitable exit exists is **held to the time stop** and
  surfaced as `position_unmanageable`: closing it would mean paying roughly
  the position's whole value in spread crossing, while the risk is already
  defined and collateralized.
- **Time stop:** close or roll at 2 DTE — never carry into expiration/assignment.
- **Signal flip:** an opposing ML30 signal on the underlying closes the position.
- **No minimum holding time — deliberately.** Same-session closes are correct
  and intended (see the PDT note above); the floors are absolute price bands,
  not time locks. Do not "fix" exit churn with a hold timer — it would also
  delay legitimate stops.
- Closing limits carry a $0.02 minimum pad and are capped at the spread's
  width — no rational close pays more than the spread can ever be worth.

## Execution architecture (Alpaca stack)

- **Alpaca CLI** is the agent's execution layer: entries, reprices, exits and
  cancels run through `alpaca order submit/cancel` with structured JSON output
  and idempotent client order ids — the tool Alpaca built for long-running
  agent sessions. Raw REST is an automatic fallback so a CLI hiccup never
  blocks a trade.
- **alpaca-py SDK / Market Data API** feeds signals, chains and quotes.
- **Alpaca MCP server** is the supervision layer: the AI operator inspects
  accounts, orders and chains through it during development and live runs.
- Everything runs against the **paper trading environment**.

## Order handling

Entries are limit orders priced at the spread's mid. A limit that sits unfilled
goes stale: once the underlying moves, the credit it asks for no longer exists
in the market. Unfilled **entry** orders are therefore cancelled after 3 minutes
(`order_stale_after_s`) rather than left to tie up buying power or fill hours
later under conditions the original signal no longer describes. Exit orders are
never cancelled by this rule — an open position must always be able to close.

Observed live 2026-08-25: an order submitted the previous evening at a $0.75
credit was still unfilled at the open after SPY rose 0.4% overnight and the
spread's credit compressed to $0.56. Re-priced to $0.55, it filled in 200ms at
$0.63 (price improvement).

## Position sizing

Max risk per position (width − credit) ≤ 1.5% of account equity.
Total buying-power usage ≤ 50%.
These sit inside the canonical band for short-premium systems — the derivation
and literature comparison live in [`risk-sizing.md`](risk-sizing.md).

## Open questions (resolve during dev-account testing, Aug 24–27)

- [x] Multi-leg order mechanics validated 2026-08-24 — see `alpaca-notes.md` (rejection modes still pending)
- [x] Signal timeframe: resolved 2026-08-26 — 5m (V1-5m), scans every 5 minutes
- [ ] `max_signal_strength` raised 0.012 → 0.02 for the 5m burn-in
  (2026-08-27). Rationale: replay over the 80-name universe showed the 5m
  trigger's median strength is ~0.003 with p95 ≈ 0.012, and the ceiling's
  vetoes concentrate on opening-gap "crosses" (which 0.02 still blocks).
  **Review after the burn-in with the live signal data** — every signal now
  logs `sma55`/`sma21`/`bar_time`, and `scripts/verify_entries.py` audits
  entries against them — then lock the value for competition week.
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
