"""ML30 momentum signal engine.

Triple-confirmation long trigger evaluated on 5-minute REGULAR-HOURS bars —
the timeframe and session filter of V1-5m, the sweep-winning and
live-validated variant of the system (its 15-minute sibling was retired for
lack of live edge). All four conditions on a single candle close:

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
BAR_SPAN_S = 5 * 60         # bar labels are window STARTS; close = label + span

_UNIVERSE_PATH = Path(__file__).resolve().parent.parent / "universe.json"


@dataclass(frozen=True)
class Signal:
    symbol: str
    direction: str          # "LONG" (the deployed system is long-only)
    close: float
    sma_slow: float
    sma_fast: float
    bar_time: datetime

    @property
    def strength(self) -> float:
        """Breakout distance over both SMAs, in fractional terms.

        For the options overlay this is an OVEREXTENSION measure, not a merit
        score: a violent breakout mean-reverts within hours (observed live
        2026-08-26 — the two strongest signals were the day's two worst
        positions), while a calm cross tends to drift. Signals above the
        ceiling are skipped, and the calmest valid crosses trade first.
        """
        return (self.close / self.sma_slow - 1) + (self.close / self.sma_fast - 1)


def load_universe() -> list[str]:
    return json.loads(_UNIVERSE_PATH.read_text())["symbols"]


def load_sectors() -> dict[str, str]:
    return json.loads(_UNIVERSE_PATH.read_text()).get("sectors", {})


def _rth(df: pd.DataFrame) -> pd.DataFrame:
    """Regular-trading-hours bars only (09:30–16:00 ET, labels = window starts).

    The 3,600-backtest sweep that validated V1-5m ran on RTH-only bars
    (ml30-sp500-strategy data/alpaca_client.py — 'production / canonical');
    the live signal must see the same tape. Pre/after-market bars are thin
    and fed a live pre-market entry on 2026-08-27 that the validated system
    could never have produced.
    """
    ny = df.index.tz_convert("America/New_York")
    minutes = ny.hour * 60 + ny.minute
    return df[(minutes >= 9 * 60 + 30) & (minutes < 16 * 60)]


def fetch_bars(
    client: StockHistoricalDataClient, symbols: list[str], days: int = 4
) -> dict[str, pd.DataFrame]:
    """Fetch recent 5-minute regular-hours bars, keyed by symbol."""
    req = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame(5, TimeFrameUnit.Minute),
        start=datetime.now(timezone.utc) - timedelta(days=days),
    )
    bars = client.get_stock_bars(req)
    out: dict[str, pd.DataFrame] = {}
    df = bars.df
    if df.empty:
        return out
    for symbol in df.index.get_level_values("symbol").unique():
        out[symbol] = _rth(df.xs(symbol, level="symbol"))
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


def bar_age_s(bar_time: datetime, now: datetime | None = None) -> float:
    """Seconds since the signal bar CLOSED (labels are window starts)."""
    now = now or datetime.now(timezone.utc)
    return (now - (bar_time + timedelta(seconds=BAR_SPAN_S))).total_seconds()


def split_stale(
    signals: list[Signal], max_age_s: float, now: datetime | None = None
) -> tuple[list[Signal], list[tuple[Signal, float]]]:
    """Split signals into fresh and stale by bar age; stale carries its age.

    A stale bar is treated exactly like a down feed — the API answering with
    old data is the more expensive failure, because nothing errors.
    """
    now = now or datetime.now(timezone.utc)
    fresh: list[Signal] = []
    stale: list[tuple[Signal, float]] = []
    for s in signals:
        age = bar_age_s(s.bar_time, now)
        if age <= max_age_s:
            fresh.append(s)
        else:
            stale.append((s, age))
    return fresh, stale


def scan(
    client: StockHistoricalDataClient,
    symbols: list[str] | None = None,
    max_strength: float | None = None,
) -> list[Signal]:
    """Scan the universe; calm crosses first, overextended ones dropped."""
    symbols = symbols or load_universe()
    bars = fetch_bars(client, symbols)
    signals = [s for sym, df in bars.items() if (s := evaluate(sym, df))]
    if max_strength is not None:
        signals = [s for s in signals if s.strength <= max_strength]
    return sorted(signals, key=lambda s: s.strength)
