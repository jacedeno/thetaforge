# ThetaForge — Post-Mortem

Retired 16 September 2026. This document records what the agent actually did with
money, and what the record says went wrong. It is written from the trade journal
rather than from memory, and it is meant to be useful to whoever builds the next
version — including the author.

## Outcome

The agent ran unattended on a paper account for eight sessions after the hackathon
window closed. It opened and closed 10 round trips on its own. Three further
spreads were still open when it was shut down and were closed manually at market.

| | |
|---|---|
| Sessions traded | 8 (4 Sep – 16 Sep 2026) |
| Round trips closed by the agent | 10 |
| Wins / losses | 5 / 5 (**50%**) |
| Average win | +$48.80 |
| Average loss | −$221.60 |
| Payoff ratio | **0.22** |
| Realized P&L | **−$864** |
| Account | ~$2,800 → $1,808.52 (**−35%**) |

## The trade record

Every position was a defined-risk vertical credit spread. `max win` is the credit
collected, `max loss` is what the structure could lose by construction.

| Underlying | Qty | Width | Credit | Credit/width | Max win | Max loss | Reward:risk | P&L | Exit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| AVGO | 1 | 5.00 | 0.88 | 18% | $88 | $412 | 1:4.7 | **+49** | profit target |
| MCD | 2 | 2.50 | 0.23 | 9% | $46 | $454 | 1:9.9 | **−110** | stop loss |
| TSLA | 1 | 5.00 | 1.15 | 23% | $115 | $385 | 1:3.3 | **+52** | profit target |
| BA | 2 | 2.50 | 0.57 | 23% | $114 | $386 | 1:3.4 | **+40** | profit target |
| META | 1 | 5.00 | 1.10 | 22% | $110 | $390 | 1:3.5 | **+59** | profit target |
| NKE | 6 | 1.00 | 0.17 | 17% | $102 | $498 | 1:4.9 | **−210** | stop loss |
| GOOGL | 1 | 5.00 | 0.90 | 18% | $90 | $410 | 1:4.6 | **+44** | profit target |
| NVDA | 2 | 2.50 | 0.56 | 22% | $112 | $388 | 1:3.5 | **−298** | stop loss |
| CMG | 6 | 1.00 | 0.16 | 16% | $96 | $504 | 1:5.2 | **−294** | stop loss |
| AMZN | 2 | 2.50 | 0.57 | 23% | $114 | $386 | 1:3.4 | **−196** | time stop (2 DTE) |

Closed manually at shutdown, not counted above: XOM 160/157.5, TSLA 350/345,
BAC 59/58.

## What went wrong

### The loss was priced into every entry, before any exit rule ran

This is the finding that matters, and it is not subtle once the entries are laid
out side by side.

The agent never once sold a spread for more than **23% of its width**. The range
across all ten trades was **9% to 23%**. Averaged over the book, each position
risked **$421 to collect $99** — a reward-to-risk of roughly **1:4.3**.

A structure with that shape has a break-even win rate baked in at the moment of
entry:

```
avg max win  = $99
avg max loss = $421
required win rate = 421 / (421 + 99) = 81%
```

**The strategy needed to be right about 81% of the time just to break even, and
that was true before a single stop or profit target was evaluated.** It was right
50% of the time. Nothing downstream — better exits, tighter stops, a smarter
signal — could have closed a gap that was fixed at entry.

Selling a $1.00-wide spread for $0.16 is not a strategy with a bad month. It is
the market pricing that spread as very unlikely to pay, and taking the other side
of that at size.

### The exit rules made it worse, but they are the second problem, not the first

The profit target sat near 50% of the credit received while the stop tolerated
roughly 2x that credit. That compresses an already-bad 1:4.3 into a realized
payoff of 0.22 (+$48.80 average win against −$221.60 average loss), which
independently requires an **82%** win rate. The two failures compound, but fixing
the exits alone would not have produced a profitable system.

### What was *not* the problem

Worth stating, because the obvious suspects are innocent and chasing them would
waste the next attempt:

- **Position sizing was sound.** Max loss per position ranged $385–$504 against a
  target near $400. The sizer was correctly holding risk constant, not scaling on
  premium. The two six-contract trades (NKE, CMG) look oversized and account for
  $504 of the $864 lost, but six contracts of a $1.00-wide spread *is* the same
  risk as one contract of a $5.00-wide one. The sizer did its job; it was handed
  badly priced structures.
- **The ML signal is unproven, not disproven.** Ten round trips says nothing
  about a directional model either way. The entry pricing failure is structural
  and provable from ten trades; the signal's edge is simply untested at this
  sample size.
- **Execution and risk plumbing held.** No position exceeded its designed max
  loss, there was never an assignment or a margin event, and the agent ran eight
  sessions unattended — including a host migration mid-flight — without an
  intervention.

## What the next version needs

1. **A minimum credit as a percentage of spread width, enforced at entry.** A
   floor near one third of width is the single change that would have prevented
   this outcome. Under it, **every one of these ten trades would have been
   rejected** — which is the correct result.
2. **Reward:risk as an explicit, logged input.** The 1:4.3 was emergent and
   nobody chose it. It should be a parameter with a hard bound, printed in the
   decision log at entry, so a trade that needs an 81% win rate cannot be opened
   without something refusing it.
3. **Exit rules derived from max loss, not from the credit.** If the target is a
   fraction of credit and the stop is a multiple of it, the payoff ratio drifts
   with every fill. Anchor both to the structure's max loss instead.
4. **Backtest before funding.** Every number in this document was observable in
   historical option chains. It cost $990 and eight sessions to learn it live.

## Corrections to this document

The first published version of this post-mortem reported 9 round trips and −$668
realized, and attributed the loss to three unusually cheap entries amplified by a
premium-based sizer. All three claims were wrong. AMZN closed on the agent's own
time stop moments before shutdown, making it 10 trades and −$864; the cheap-credit
problem was universal rather than confined to three trades; and the sizer was
holding risk constant, not scaling on premium. The corrected analysis above is
built from the full journal.
