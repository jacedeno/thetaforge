# Risk Sizing — Where ThetaForge Sits vs the Literature

> Reference: classic position-sizing doctrine (Van Tharp school), Euan Sinclair
> (*Positional Option Trading*, Wiley 2020 — fractional-Kelly sizing), and the
> tastytrade/Spina mechanics (*The Unlucky Investor's Guide to Options Trading*,
> Wiley 2022). Written 2026-08-25 while fixing the agent's sizing parameters.

## The canonical numbers for short-premium systems

**Per position: 1–2% of equity at risk.** The classic rule and Sinclair's
fractional-Kelly derivation land in the same band: full Kelly for a 75%-win
trade looks permissive, but edge estimates are always uncertain, so
practitioners run ¼–½ Kelly. tastytrade's defined-risk guidance: 1–5%, comfort
zone 1–3%.

**Portfolio deployment: 25–50% of buying power.** The number experienced
premium sellers watch hardest. 25–35% in normal volatility, up to ~50% when IV
is elevated (richer premium for the same risk), never fully deployed. The
reserve is the crash defense — in a selloff every short spread loses at once,
and elevated IV is precisely when you want ammunition to sell.

**Aggregate worst case: 15–25% tolerable.** All positions hitting max loss
simultaneously is the correlated-crash scenario. The CBOE PUT index — the
academic benchmark for systematic put selling, fully collateralized — drew down
~35% in 2008 at the ultra-conservative end of implementations.

**The correlation warning (Sinclair):** ten put spreads on ten tickers are not
ten bets — they are one short-a-market-crash bet. The aggregate cap matters
more than the position count.

## ThetaForge configuration vs canon

| Parameter | Canon | ThetaForge |
|---|---|---|
| Risk per position | 1–2% | 2% (`max_risk_per_position_pct`) |
| Buying-power deployment | 25–50% | 50% cap; observed usage far lower |
| Aggregate worst case | 15–25% | 22.5% (15 positions × 1.5%, retuned 2026-08-27 from 10 × 2% — more and smaller positions, upper half of the band as a burn-in experiment) |
| Profit taking | early, mechanical | 50% of credit / 2× stop / 2 DTE |

Every parameter sits inside the experienced-practitioner band. The sizing is
not chosen to maximize return — it is chosen so the system survives its worst
week and keeps executing. The verified top-20 options sellers we studied carry
thousands of trades each; nobody accumulates that history on sizing that can
knock them out of the game.

## Note on small accounts

Contract granularity forces small accounts above the band: on $6,000, a single
$3-wide spread is ~4% of equity. Mitigation is structural — prefer narrower
spreads ($2-wide ≈ 2.7%), hold fewer simultaneous positions, and treat the
account as designated risk capital rather than total trading capital, so a
worst-case drawdown is bounded at the account level too.
