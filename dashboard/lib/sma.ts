import type { CandlestickData, Time } from "lightweight-charts";

// The ML30 signal's own averages (agent/signals/ml30.py: SMA_FAST=21,
// SMA_SLOW=55) — drawn on the candle charts so an entry can be verified
// against the cross that fired it.
export const SMA_FAST = 21;
export const SMA_SLOW = 55;
export const SMA_FAST_COLOR = "#2196f3"; // fast — blue (Jose's convention)
export const SMA_SLOW_COLOR = "#ff9800"; // slow — orange
export const SIGNAL_COLOR = "#00e676";   // signal marker — traffic-light green: "go"

// Default visible span per timeframe — a fast read at a glance, with zoom
// and pan untouched. (Jose's spec: 5m→24h, 15m→72h, 1h→14d, 1d→12mo.)
export const DEFAULT_RANGE_S: Record<string, number> = {
  "5Min": 24 * 3600,
  "15Min": 72 * 3600,
  "30Min": 7 * 86400,
  "1Hour": 14 * 86400,
  "1Day": 365 * 86400,
};

export function sma(
  bars: CandlestickData<Time>[], period: number,
): { time: Time; value: number }[] {
  const out: { time: Time; value: number }[] = [];
  let sum = 0;
  for (let i = 0; i < bars.length; i++) {
    sum += bars[i].close;
    if (i >= period) sum -= bars[i - period].close;
    if (i >= period - 1) out.push({ time: bars[i].time, value: sum / period });
  }
  return out;
}

const BAR_SECONDS: Record<string, number> = {
  "5Min": 300, "15Min": 900, "30Min": 1800, "1Hour": 3600, "1Day": 86400,
};

/** Extra calendar time to fetch before the visible window so SMA55 is
 *  already warm at the first bars that matter: 60 bars of the timeframe,
 *  scaled from session time to calendar time (nights, weekends), never
 *  less than 4 days. */
export function smaLookbackMs(tf: string): number {
  const bar = BAR_SECONDS[tf] ?? 900;
  const factor = tf === "1Day" ? 1.6 : 5;
  return Math.max(60 * bar * 1000 * factor, 4 * 86_400_000);
}
