"""Order execution against Alpaca's paper trading environment.

Execution routes through the **Alpaca CLI** (`alpaca order submit/cancel`
with structured JSON output) — the tool Alpaca built for long-running agent
sessions. The raw REST endpoint stays as an automatic fallback so a CLI
hiccup never blocks a trade, and alpaca-py's TradingClient handles account
and position reads. The documented mleg semantics (negative limit = net
credit, per-leg position intents) were validated live on 2026-08-24/26 —
see docs/alpaca-notes.md.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import uuid

import requests
from alpaca.trading.client import TradingClient

from agent.options.selector import SpreadCandidate

PAPER_BASE = "https://paper-api.alpaca.markets"

log = logging.getLogger("thetaforge")


def cli_path() -> str | None:
    return shutil.which("alpaca") or (
        os.path.expanduser("~/go/bin/alpaca")
        if os.path.exists(os.path.expanduser("~/go/bin/alpaca")) else None
    )


def mleg_submit_args(legs: list[dict], qty: int, limit_price: float, client_order_id: str) -> list[str]:
    """CLI argv for a multi-leg limit order (pure, for tests)."""
    return [
        "order", "submit",
        "--order-class", "mleg",
        "--qty", str(qty),
        "--type", "limit",
        "--limit-price", str(round(limit_price, 2)),
        "--time-in-force", "day",
        "--client-order-id", client_order_id,
        "--legs", json.dumps(legs),
    ]


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

    # -- Alpaca CLI (primary execution path) ------------------------------

    def _cli(self, args: list[str]) -> dict:
        """Run one Alpaca CLI command and parse its JSON output."""
        binary = cli_path()
        if binary is None:
            raise RuntimeError("alpaca CLI not installed")
        env = {**os.environ, "ALPACA_API_KEY": self._key, "ALPACA_SECRET_KEY": self._secret}
        r = subprocess.run([binary, *args], capture_output=True, text=True, timeout=30, env=env)
        if r.returncode != 0:
            raise RuntimeError(f"alpaca CLI failed [{r.returncode}]: {r.stderr.strip()[:300]}")
        out = r.stdout.strip()
        return json.loads(out) if out else {}

    def _submit_spread(self, legs: list[dict], qty: int, limit_price: float, client_order_id: str) -> dict:
        """CLI first; REST fallback so execution never depends on one path."""
        try:
            return self._cli(mleg_submit_args(legs, qty, limit_price, client_order_id))
        except Exception as e:
            log.warning("CLI submit failed (%s) — falling back to REST", e)
            return self._post_order({
                "order_class": "mleg", "qty": str(qty), "type": "limit",
                "limit_price": str(round(limit_price, 2)), "time_in_force": "day",
                "client_order_id": client_order_id, "legs": legs,
            })

    # -- spreads ----------------------------------------------------------

    def open_credit_spread(self, spread: SpreadCandidate, qty: int, limit_credit: float) -> dict:
        """Sell-to-open a credit spread at a net credit limit (positive input)."""
        return self.open_spread_symbols(
            spread.short_symbol, spread.long_symbol, qty, limit_credit,
            client_order_id=f"tf-open-{spread.underlying}-{uuid.uuid4().hex[:8]}",
        )

    def open_spread_symbols(
        self, short_symbol: str, long_symbol: str, qty: int,
        limit_credit: float, client_order_id: str | None = None,
    ) -> dict:
        legs = [
            {"symbol": short_symbol, "ratio_qty": "1",
             "side": "sell", "position_intent": "sell_to_open"},
            {"symbol": long_symbol, "ratio_qty": "1",
             "side": "buy", "position_intent": "buy_to_open"},
        ]
        return self._submit_spread(
            legs, qty, -abs(limit_credit),
            client_order_id or f"tf-open-{uuid.uuid4().hex[:8]}")

    def close_credit_spread(
        self, short_symbol: str, long_symbol: str, qty: int, limit_debit: float
    ) -> dict:
        """Buy-to-close a credit spread at a net debit limit (positive input)."""
        legs = [
            {"symbol": short_symbol, "ratio_qty": "1",
             "side": "buy", "position_intent": "buy_to_close"},
            {"symbol": long_symbol, "ratio_qty": "1",
             "side": "sell", "position_intent": "sell_to_close"},
        ]
        return self._submit_spread(
            legs, qty, abs(limit_debit), f"tf-close-{uuid.uuid4().hex[:8]}")

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

    def cancel_order(self, order_id: str) -> None:
        try:
            self._cli(["order", "cancel", "--order-id", order_id])
        except Exception as e:
            log.warning("CLI cancel failed (%s) — falling back to SDK", e)
            self.trading.cancel_order_by_id(order_id)
