# ThetaForge — Post-Mortem

Retired 16 September 2026. This document records what the agent actually did with
money, and what the record says went wrong. It is written to be useful to whoever
builds the next version, including the author.

## Outcome

The agent ran unattended on a paper account for eight sessions after the hackathon
window closed. It opened and closed 9 round trips on its own, and was holding 4
open spreads when it was shut down.

| | |
|---|---|
| Sessions traded | 8 (4 Sep – 16 Sep 2026) |
| Round trips closed by the agent | 9 |
| Wins / losses | 5 / 4 (56% win rate) |
| Average win | +$48.80 |
| Average loss | −$228.00 |
| Payoff ratio | **0.21** (loss is 4.7x the win) |
| Realized P&L | **−$668** |
| Open P&L at shutdown | −$607 |
| Account | ~$2,800 → $1,808.52 (**−35%**) |

## The trade record

Every position was a defined-risk vertical credit spread sized in contracts.

| Underlying | Qty | Opened | Closed | Credit | Debit | P&L | Exit |
|---|---:|---|---|---:|---:|---:|---|
| AVGO | 1 | 04 Sep | 08 Sep | 0.88 | 0.39 | **+49** | profit target |
| MCD | 2 | 04 Sep | 08 Sep | 0.23 | 0.78 | **−110** | stop loss |
| TSLA | 1 | 04 Sep | 08 Sep | 1.15 | 0.63 | **+52** | profit target |
| BA | 2 | 04 Sep | 08 Sep | 0.57 | 0.37 | **+40** | profit target |
| META | 1 | 04 Sep | 09 Sep | 1.10 | 0.51 | **+59** | profit target |
| NKE | 6 | 08 Sep | 10 Sep | 0.17 | 0.52 | **−210** | stop loss |
| GOOGL | 1 | 08 Sep | 11 Sep | 0.90 | 0.46 | **+44** | profit target |
| NVDA | 2 | 09 Sep | 14 Sep | 0.56 | 2.05 | **−298** | stop loss |
| CMG | 6 | 08 Sep | 15 Sep | 0.16 | 0.65 | **−294** | stop loss |

Open at shutdown, closed manually at market: AMZN 250/247.5, XOM 160/157.5,
TSLA 350/345, BAC 59/58.

## What went wrong

### 1. The exit arithmetic was upside-down

This is the whole story. The agent won 56% of its trades — a real edge, and more
than enough to build on. It still lost a third of the account, because the profit
target sat near **50% of the credit received** while the stop tolerated roughly
**2x that credit**. Risking two units to make one, at a 56% hit rate, is a
negative-expectancy machine no matter how good the signal is.

Break-even win rate at the realized payoff ratio:

```
avg win  = $48.80
avg loss = $228.00
required = 228 / (228 + 48.80) = 82.3%
```

The strategy needed to be right **82% of the time** to break even. It was never
going to be, and nothing in the signal layer could have closed that gap.

### 2. Low-credit entries did almost all the damage

Three trades were opened for a very small credit relative to the width of the
spread:

| Trade | Credit | Width | Credit as % of width | Max loss risked per $1 collected | P&L |
|---|---:|---:|---:|---:|---:|
| CMG | 0.16 | 1.00 | 16% | $5.25 | −294 |
| NKE | 0.17 | 1.00 | 17% | $4.88 | −210 |
| MCD | 0.23 | 1.00 | 23% | $3.35 | −110 |

Those three account for **−$614 of the −$668** realized. All three were also the
largest positions by contract count (6, 6 and 2), so the sizing rule actively
amplified the worst-priced trades: a small credit meant a small notional per
contract, which the sizer read as room for more contracts.

A 16% credit-to-width ratio is the market pricing a spread as very unlikely to
pay — collecting $0.16 to risk $0.84. There was no gate against it.

### 3. The sample was too small to be trusted either way

Nine round trips is not a verdict on the signal. It is, however, enough to
observe that the exit configuration cannot work arithmetically, which is a
structural finding and does not need a large sample to be valid.

## What the next version needs

1. **A minimum credit as a percentage of spread width.** Refuse any spread paying
   less than roughly a third of its width. This alone would have blocked all
   three of the trades that caused the loss.
2. **Stop and target derived from the same number.** If the target is 50% of the
   credit, the stop cannot be 200% of it. Set both from the spread's max loss so
   the payoff ratio is a deliberate choice rather than an emergent accident.
3. **Sizing that reads risk, not premium.** Contract count should scale with the
   max loss of the position, not inversely with the credit collected.
4. **Backtest before funding.** Every conclusion above came from nine live trades
   and $990 of real drawdown. All of it was observable in historical data first.

## What worked

Worth keeping, because none of it is why the project failed:

- The agent ran unattended for eight sessions without an intervention, including
  a host migration mid-flight, and placed and managed every order itself.
- Defined-risk construction held. No position ever exceeded its designed max
  loss, and there was never an assignment or a margin event.
- The journal, the equity sampler and the decision log captured enough to write
  this document from the record rather than from memory — which is the only
  reason the diagnosis above is specific.
