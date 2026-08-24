"""ML30 momentum signal engine.

Triple-confirmation long trigger evaluated on 15-minute bars, all four
conditions on a single candle close:

    c1: close > SMA55           (above primary moving average)
    c2: prev_close <= prev_SMA55  (fresh-cross filter: fires only on the
                                   bar that crosses up, not continuations)
    c3: close > SMA21           (short-term momentum confirmation)
    c4: close > open            (bullish candle)

The trigger comes from a momentum system validated over a 120-config,
3,600-backtest sweep on liquid S&P 500 names; here it selects the
underlyings and direction for the options overlay.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

SMA_SLOW = 55
SMA_FAST = 21
BARS_NEEDED = SMA_SLOW + 5  # warm-up plus a small margin

_UNIVERSE_PATH = Path(__file__).resolve().parent.parent / "universe.json"


@dataclass(frozen=True)
class Signal:
    symbol: str
    direction: str          # "LONG" (the deployed system is long-only)
    close: float
    sma_slow: float
    sma_fast: float
    bar_time: datetime


def load_universe() -> list[str]:
    return json.loads(_UNIVERSE_PATH.read_text())["symbols"]


def fetch_bars(
    client: StockHistoricalDataClient, symbols: list[str], days: int = 10
) -> dict[str, pd.DataFrame]:
    """Fetch recent 15-minute bars, keyed by symbol."""
    req = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame(15, TimeFrameUnit.Minute),
        start=datetime.now(timezone.utc) - timedelta(days=days),
    )
    bars = client.get_stock_bars(req)
    out: dict[str, pd.DataFrame] = {}
    df = bars.df
    if df.empty:
        return out
    for symbol in df.index.get_level_values("symbol").unique():
        out[symbol] = df.xs(symbol, level="symbol")
    return out


def evaluate(symbol: str, df: pd.DataFrame) -> Signal | None:
    """Evaluate the trigger on the latest completed bar of one symbol."""
    if len(df) < BARS_NEEDED:
        return None
    close = df["close"]
    sma_slow = close.rolling(SMA_SLOW).mean()
    sma_fast = close.rolling(SMA_FAST).mean()

    c, p = -1, -2  # current and previous bar
    c1 = close.iloc[c] > sma_slow.iloc[c]
    c2 = close.iloc[p] <= sma_slow.iloc[p]
    c3 = close.iloc[c] > sma_fast.iloc[c]
    c4 = close.iloc[c] > df["open"].iloc[c]

    if c1 and c2 and c3 and c4:
        return Signal(
            symbol=symbol,
            direction="LONG",
            close=float(close.iloc[c]),
            sma_slow=float(sma_slow.iloc[c]),
            sma_fast=float(sma_fast.iloc[c]),
            bar_time=df.index[c].to_pydatetime(),
        )
    return None


def scan(client: StockHistoricalDataClient, symbols: list[str] | None = None) -> list[Signal]:
    """Scan the universe and return all symbols triggering on the latest bar."""
    symbols = symbols or load_universe()
    bars = fetch_bars(client, symbols)
    signals = [s for sym, df in bars.items() if (s := evaluate(sym, df))]
    return signals
