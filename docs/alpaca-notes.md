# Alpaca Multi-Leg Order Mechanics — Field Notes

Validated 2026-08-24 on a paper account (options level 3), market closed — order accepted and queued for next open.

## What works

Put credit spread via `POST /v2/orders` (or MCP `place_option_order`):

- `order_class: "mleg"` — parent carries `qty` (strategy multiplier), `type: "limit"`, `time_in_force: "day"` (options are **day-only**).
- **`limit_price` sign convention:** negative = net credit, positive = net debit. `-0.75` = collect $0.75/spread.
- Each leg: `symbol` (OCC format), `ratio_qty` (string), `side`, `position_intent` (`sell_to_open` / `buy_to_open`).
- Parent needs no `symbol`/`side`; legs get their own order IDs; per-leg `limit_price` is null (the net limit governs).
- `client_order_id` works as idempotency key on the parent.
- Orders submitted while closed are `accepted` and queue for the open; day orders carry an `expires_at` of next session close (~16:15 ET).

## Test order placed

| | |
|---|---|
| Structure | SPY put credit spread, exp 2026-09-11 (18 DTE) |
| Short leg | SPY260911P00749000 (~25Δ) |
| Long leg | SPY260911P00744000 ($5 wide) |
| Net limit | $0.75 credit (mid was ~$0.78) |
| Max risk | $425 = (5.00 − 0.75) × 100 |

## OCC symbol format

`SPY260911P00749000` = root + YYMMDD + C/P + strike × 1000, zero-padded to 8 digits.

## Still to verify (market hours)

- [ ] Fill behavior at open; slippage vs mid on the net limit
- [ ] Closing flow: reversed legs with `*_to_close` intents, positive (debit) limit
- [ ] Rejection modes: insufficient options BP, bad ratio, >4 legs, non-day TIF
- [ ] How spread margin is reserved (options_buying_power delta after fill)
