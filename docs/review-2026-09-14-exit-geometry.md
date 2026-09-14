# Review 2026-09-14 — the first losses on the relaunch account

> Six sessions into the relaunch (2026-09-04 → 2026-09-14). Eight closed
> trades, five open. Decision: **nothing changes yet** — the sample is too
> small to move a parameter on, and every number below is recorded so the
> next review starts from counts instead of memory.

## What prompted it

The average winner is about $50 and one loser was $298 — six winners and
change, wiped by one trade. The question was whether that is bad luck or
design.

## The closed record

| | n | average | total |
|---|---|---|---|
| Winners (profit target, 50% of credit) | 5 | +$49 | +$244 |
| Losers (stop, 2× credit) | 3 | −$206 | −$618 |
| Net realized | 8 | | **−$374** |

Win rate 62.5%. At these averages the break-even win rate is **81%**.

That is not luck. Target = 0.5× credit and stop = 2× credit is a 1:4
win/loss ratio by construction, so the strategy needs four winners out of
five to stand still. The 2026-09-04 review kept the 2× stop because the
replay said it was P&L-neutral against holding, and that is still true —
the stop does not create the ratio, the target does, and the target is
where the slot turnover comes from. The ratio is the price of the turnover.

| Trade | qty | credit | width | credit/width | exit | P&L |
|---|---|---|---|---|---|---|
| TSLA 337.5/332.5 | 1 | 1.15 | 5 | 0.23 | target, Mon 09-08 | +52 |
| BA 207.5/205 | 2 | 0.57 | 2.5 | 0.23 | target, Mon 09-08 | +40 |
| MCD 252.5/250 | 2 | 0.23 | 2.5 | 0.09 | **stop, Mon 09-08 08:45 CT** | −110 |
| META 585/580 | 1 | 1.10 | 5 | 0.22 | target, Tue 09-09 | +59 |
| AVGO 345/340 | 1 | 0.88 | 5 | 0.18 | target, Mon 09-08 | +49 |
| NKE 37/36 | 6 | 0.17 | 1 | 0.17 | stop, Wed 09-10 | −210 |
| GOOGL 327.5/322.5 | 1 | 0.90 | 5 | 0.18 | target, Fri 09-11 | +44 |
| NVDA 217.5/215 | 2 | 0.56 | 2.5 | 0.22 | **stop, Mon 09-14 08:30 CT** | −298 |

(MCD's 0.09 is below the 0.12 floor, which has been in place since
2026-08-25. The floor is tested on the mid at selection; the fill landed
below it. The gate protects the quote, not the fill — worth remembering
when reading point (1) below.)

## Anatomy of the −$298

NVDA, 2 contracts, credit 0.56, stop at loss 1.12 (cost 1.68).

| | cost | loss per contract |
|---|---|---|
| Friday 09-11, last monitor pass (14:59 CT) | 1.02 | 0.46 — well inside the stop |
| Monday 09-14, first pass (08:30 CT) | 1.75 | 1.19 — stop fires |
| Three escalating exit attempts, 08:30–08:34 | fill 2.05 | 1.49 |

- Planned stop: $224.
- The weekend gap took it to $238 before the agent could act.
- The exit mechanics added $60: three retries two minutes apart, each one
  step closer to the natural price, run through the widest quotes of the
  session. On a stop that is already through its level, the ladder buys
  nothing — the third step pays what the first would have.

## The weekend, both ways

The obvious reaction is "no entries on Friday". It had already been
proposed and rejected on the grounds that a short-premium book is paid to
hold through the weekend. Both are true; the record decides which one
matters:

| Weekend | Held | Monday outcome |
|---|---|---|
| 09-04 → 09-08 | TSLA, BA, AVGO, MCD, META | 3 targets in the first hour, 1 stop (MCD), META target Tuesday |
| 09-11 → 09-14 | NVDA, CMG, AMZN, XOM, TSLA | 1 stop (NVDA); CMG and AMZN near target, XOM and TSLA under water |

Ten positions carried over a weekend: four targets on Monday, two stops on
Monday, four still open. The weekend produced more winners than losers.
What separates them is credit per dollar of width: the two Monday stops
were the thinnest credits of their lots. A 0.17 credit on a $1 width earns
cents of weekend theta and loses its whole stop to the gap; a 1.10 credit
on a $5 width is paid for the wait. **The Friday filter stays off.**

## The open book at the time of writing

Five positions, $2,214 at risk on $2,421 of equity.

| | qty | credit | cost | note |
|---|---|---|---|---|
| CMG 36/35 | 6 | 0.16 | 0.12 | near target |
| AMZN 250/247.5 | 2 | 0.57 | 0.45 | near target |
| XOM 160/157.5 | 2 | 0.32 | 0.50 | loss 0.18, stop at 0.64 |
| TSLA 350/345 | 1 | 1.10 | 1.21 | loss 0.11, stop at 2.20 |
| BAC 59/58 | 6 | 0.17 | 0.30 | opened 12:17 CT today; loss 0.13, stop at 0.34 |

## Decisions — deferred, one per point

Every one of these is a change the record could justify and none of them is
made today. Eight closed trades do not move a parameter. They are listed in
the order they would be taken.

1. **Credit floor per dollar of width.** NKE, CMG and BAC are six-contract
   lots collecting 0.16–0.17 on a $1 width: 17% collected, 83% at risk, and
   a 2% move in the underlying reaches the 2× stop. Raising
   `min_credit_to_width` 0.12 → 0.25 and `min_credit_usd` 0.15 → 0.30
   removes that class of entry while keeping the TSLA/META/AVGO class the
   weekend pays for. First change to make when the record supports it.
2. **A stop at the open crosses the spread in one order.** When the stop
   fires in the first fifteen minutes of a session, skip the three-step
   escalation and pay the natural price immediately. NVDA's $60 is the cost
   of not doing so.
3. **No Friday entries.** Rejected — see above. Recorded so it is not
   re-proposed on the next Monday loss without new evidence.
4. **Stop at 1× credit.** Moves the break-even to 67% but the 2026-09-04
   replay already showed tighter stops eat winners to noise. Not until the
   effect of (1) is visible.

## What the next review needs

- Closed trades split by credit/width band (< 0.20, 0.20–0.25, > 0.25):
  win rate and average P&L per band. Point (1) stands or falls on this.
- Every stop: loss at detection vs loss at fill, and the time of day.
  Point (2) stands or falls on this.
- Weekend-held positions with their Monday outcome, continued from the
  table above.

The dashboard's equity curve now carries SPY and QQQ buy-and-hold from the
first sample (2026-09-04, $3,000 each), so the account's drawdowns can be
read against the market's at the same time.
