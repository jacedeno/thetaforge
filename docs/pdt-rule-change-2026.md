# The End of PDT — FINRA's Intraday Margin Rule (June 2026)

> Verified against Alpaca's own documentation on 2026-08-25. This changed after
> most training data and most online guides were written — treat any source that
> still says "$25,000 minimum" or "3 day trades per 5 days" as outdated.

## What changed

FINRA overhauled Rule 4210 as part of its "FINRA Forward" initiative. The legacy
Pattern Day Trader framework was **replaced**, not amended:

| | Legacy PDT rule | New intraday margin rule |
|---|---|---|
| Minimum equity to day trade | $25,000 | **Eliminated** — standard $2,000 Reg T minimum applies |
| Trade limits | 3 day trades per 5 business days under $25k | **Unlimited day trades** |
| Buying power | Fixed, from previous day's close | Dynamic, recalculated in real time |
| Intraday P&L | Ignored for buying power | **Counted immediately** |
| Deposits | 2-day hold | No hold |
| Trading into a margin call | Prohibited for PDTs | Permitted |
| 0DTE options | No specific intraday requirement | Margined as IML-reducing activity |

### Timeline

- **2026-04-14** — SEC approves the elimination
- **2026-06-04** — effective date
- **2027-10-20** — end of the phase-in window; firms may run either regime until then
- **Alpaca is already on the new regime** (its docs state "Unlimited day trades")

## How risk is measured now

Trade counting is gone; the framework measures real exposure through three terms:

- **IML (Intraday Margin Level)** — running balance of maintenance margin excess
  or deficit, updated continuously as transactions occur.
- **IML-reducing transaction** — anything that lowers IML: buying securities,
  selling options short, expiration of long options, withdrawing cash.
- **IMD (Intraday Margin Deficit)** — the largest negative IML recorded during the
  day *following an IML-reducing transaction*. Critically, mark-to-market losses
  alone do not create an IMD — only customer-initiated activity does.

### Deficits

An IMD triggers a margin call payable within **two business days**. Unmet by the
close of the fifth business day, the account faces a **90-day freeze** on new
debit balances and new short positions (closing existing shorts stays allowed).

**De minimis exception:** no call is triggered when the deficit is below **$1,000
or 5% of account equity**, whichever is lower.

## Why it matters for this project

**Defined-risk spreads sit far inside the de minimis threshold.** A $2–5 wide
credit spread carries $150–450 of defined risk, fully collateralized at entry —
it cannot generate a meaningful IMD.

**The 50%-profit rule now executes when the market offers it.** Under the old
regime, closing a spread the same session it was opened consumed one of three
weekly day trades, which pushed traders to hold overnight purely to preserve a
quota — accepting unwanted overnight risk for a regulatory reason rather than a
trading one. That constraint is gone: a spread that reaches its profit target
hours after entry gets closed immediately.

This matters most for a strategy whose edge comes from **taking profits early and
exiting risk**, which is exactly the exit discipline the agent enforces
(50% of credit captured, 2× credit stop, 2 DTE time stop).

**Intraday gains free up collateral the same day.** Closing a spread at midday
releases its buying power immediately for a new position, instead of waiting for
the settlement cycle.

**Small accounts are no longer sidelined.** A $6,000 account can now recycle
capital as often as risk allows — the manual playbook assumes this.

## Sources

- [Alpaca — The Intraday Margin Rule](https://docs.alpaca.markets/us/docs/the-intraday-margin-rule)
- [Alpaca — Understanding FINRA's New Intraday Margin Rule and the End of PDT](https://docs.alpaca.markets/us/docs/understanding-finras-new-intraday-margin-rule-and-the-end-of-pdt)
- [FINRA Regulatory Notice 26-10](https://www.finra.org/rules-guidance/notices/26-10)
- [SEC — File No. SR-FINRA-2025-017](https://www.sec.gov/files/rules/sro/finra/2026/34-105226.pdf)
