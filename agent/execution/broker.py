"""Order execution against Alpaca's paper trading API.

Multi-leg orders go through the raw REST endpoint: the documented mleg
semantics (negative limit = net credit, per-leg position intents) were
validated by hand on 2026-08-24 — see docs/alpaca-notes.md.
Account and position reads use alpaca-py's TradingClient.
"""

from __future__ import annotations

import os
import uuid

import requests
from alpaca.trading.client import TradingClient

from agent.options.selector import SpreadCandidate

PAPER_BASE = "https://paper-api.alpaca.markets"


class Broker:
    def __init__(self) -> None:
        self._key = os.environ["ALPACA_API_KEY"]
        self._secret = os.environ["ALPACA_SECRET_KEY"]
        self.trading = TradingClient(self._key, self._secret, paper=True)

    # -- raw REST helpers -------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self._key,
            "APCA-API-SECRET-KEY": self._secret,
            "Content-Type": "application/json",
        }

    def _post_order(self, payload: dict) -> dict:
        r = requests.post(f"{PAPER_BASE}/v2/orders", json=payload, headers=self._headers(), timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"order rejected [{r.status_code}]: {r.text}")
        return r.json()

    # -- spreads ----------------------------------------------------------

    def open_credit_spread(self, spread: SpreadCandidate, qty: int, limit_credit: float) -> dict:
        """Sell-to-open a credit spread at a net credit limit (positive input)."""
        payload = {
            "order_class": "mleg",
            "qty": str(qty),
            "type": "limit",
            "limit_price": str(-abs(round(limit_credit, 2))),  # negative = credit
            "time_in_force": "day",
            "client_order_id": f"tf-open-{spread.underlying}-{uuid.uuid4().hex[:8]}",
            "legs": [
                {
                    "symbol": spread.short_symbol,
                    "ratio_qty": "1",
                    "side": "sell",
                    "position_intent": "sell_to_open",
                },
                {
                    "symbol": spread.long_symbol,
                    "ratio_qty": "1",
                    "side": "buy",
                    "position_intent": "buy_to_open",
                },
            ],
        }
        return self._post_order(payload)

    def close_credit_spread(
        self, short_symbol: str, long_symbol: str, qty: int, limit_debit: float
    ) -> dict:
        """Buy-to-close a credit spread at a net debit limit (positive input)."""
        payload = {
            "order_class": "mleg",
            "qty": str(qty),
            "type": "limit",
            "limit_price": str(abs(round(limit_debit, 2))),  # positive = debit
            "time_in_force": "day",
            "client_order_id": f"tf-close-{uuid.uuid4().hex[:8]}",
            "legs": [
                {
                    "symbol": short_symbol,
                    "ratio_qty": "1",
                    "side": "buy",
                    "position_intent": "buy_to_close",
                },
                {
                    "symbol": long_symbol,
                    "ratio_qty": "1",
                    "side": "sell",
                    "position_intent": "sell_to_close",
                },
            ],
        }
        return self._post_order(payload)

    # -- account state ----------------------------------------------------

    def equity(self) -> float:
        return float(self.trading.get_account().equity)

    def options_buying_power(self) -> float:
        return float(self.trading.get_account().options_buying_power)

    def option_positions(self) -> list:
        return [p for p in self.trading.get_all_positions() if p.asset_class == "us_option"]

    def open_option_orders(self) -> list:
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus

        return self.trading.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN))
