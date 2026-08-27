"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart, CandlestickSeries, LineSeries,
  type IChartApi, type CandlestickData, type Time,
} from "lightweight-charts";
import PayoffDiagram from "./PayoffDiagram";
import {
  sma, smaLookbackMs, SMA_FAST, SMA_SLOW, SMA_FAST_COLOR, SMA_SLOW_COLOR,
} from "@/lib/sma";
import { toLocal, toLocalMs } from "@/lib/localtime";

const TIMEFRAMES = ["5Min", "15Min", "1Hour", "1Day"] as const;
const TF_LABEL: Record<string, string> = { "5Min": "5m", "15Min": "15m", "1Hour": "1h", "1Day": "1d" };

export interface OpenSpread {
  underlying: string;
  shortStrike: number;
  longStrike: number;
  expiration: string;
  qty: number;
  entryCredit: number;
  openTs?: string | null;
  midCost: number | null;
  midPl: number | null;
  unrealizedPl: number;
  dte: number;
}

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

const usd2 = (v: number) => v.toLocaleString("en-US", { style: "currency", currency: "USD" });

function Level({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <div className="eyebrow">{label}</div>
      <div className="mt-0.5 text-sm font-semibold" style={{ color: tone ?? "var(--ink-primary)" }}>
        {value}
      </div>
    </div>
  );
}

/** Webull-style expanded view of one open credit spread: the full payoff
 *  with labeled levels, the live spot on the curve, and a price chart with
 *  the strikes drawn — everything derived from snapshot data, no new API. */
export default function PositionDetail({ spread, spot }: { spread: OpenSpread; spot?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [themeTick, setThemeTick] = useState(0);
  // 5m by default — the signal's own timeframe, the one where the drawn
  // SMAs reproduce what the agent computed.
  const [tf, setTf] = useState("5Min");

  useEffect(() => {
    const mo = new MutationObserver(() => setThemeTick((t) => t + 1));
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => mo.disconnect();
  }, []);

  useEffect(() => {
    if (!ref.current) return;
    const el = ref.current;
    const to = new Date(Date.now() - 16 * 60_000).toISOString();
    const openMs = spread.openTs ? new Date(spread.openTs).getTime() : null;
    // 7 days of context — stretched back to the entry when it's older — plus
    // enough lookback for SMA55 to be warm on screen.
    const windowStart = Math.min(
      Date.now() - 7 * 86_400_000,
      openMs != null ? openMs - 86_400_000 : Infinity,
    );
    const from = new Date(windowStart - smaLookbackMs(tf)).toISOString();

    let disposed = false;
    let onResizeRef: (() => void) | null = null;

    fetch(`/api/bars?symbol=${spread.underlying}&from=${from}&to=${to}&tf=${tf}`)
      .then((r) => r.json())
      .then(({ bars: rawBars }: { bars: CandlestickData<Time>[] }) => {
        if (disposed || !rawBars?.length) return;
        // Shift bar times to the viewer's zone — the chart renders them as UTC.
        const bars = rawBars.map((b) => ({ ...b, time: toLocal(b.time as number) }));
        const up = token("--good"), down = token("--critical");
        const chart = createChart(el, {
          height: 240,
          localization: { locale: "en-US" },
          layout: {
            background: { color: "transparent" },
            textColor: token("--ink-muted"),
            fontFamily: "var(--font-mono2), monospace",
            attributionLogo: false,
          },
          grid: {
            vertLines: { color: token("--grid") },
            horzLines: { color: token("--grid") },
          },
          timeScale: { timeVisible: true, borderColor: token("--baseline") },
          rightPriceScale: { borderColor: token("--baseline") },
          crosshair: { mode: 0 },
        });
        chartRef.current = chart;
        const series = chart.addSeries(CandlestickSeries, {
          upColor: up, wickUpColor: up, borderUpColor: up,
          downColor: down, wickDownColor: down, borderDownColor: down,
        });
        series.setData(bars);
        // The signal's own averages — fast orange, slow red — so the entry
        // can be checked against the cross that fired it.
        for (const [period, color] of [
          [SMA_FAST, SMA_FAST_COLOR], [SMA_SLOW, SMA_SLOW_COLOR],
        ] as [number, string][]) {
          chart.addSeries(LineSeries, {
            color, lineWidth: 1, priceLineVisible: false,
            lastValueVisible: false, crosshairMarkerVisible: false,
          }).setData(sma(bars, period));
        }
        series.createPriceLine({
          price: spread.shortStrike, color: token("--series-2"), lineWidth: 2,
          lineStyle: 0, title: `short ${spread.shortStrike} — profit above`,
        });
        series.createPriceLine({
          price: spread.longStrike, color: token("--ink-muted"), lineWidth: 1,
          lineStyle: 2, title: `long ${spread.longStrike} — max loss below`,
        });
        series.createPriceLine({
          price: spread.shortStrike - spread.entryCredit, color: token("--series-1"),
          lineWidth: 1, lineStyle: 3, title: "breakeven",
        });

        // The entry marker — where the agent actually sold the spread.
        if (openMs != null) {
          const openLocal = toLocalMs(openMs);
          let nearest = bars[0].time as number;
          for (const b of bars) {
            if (Math.abs((b.time as number) * 1000 - openLocal) <
                Math.abs(nearest * 1000 - openLocal)) nearest = b.time as number;
          }
          import("lightweight-charts").then(({ createSeriesMarkers }) => {
            if (!disposed) createSeriesMarkers(series, [{
              time: nearest as Time, position: "belowBar",
              color: token("--series-2"), shape: "arrowUp",
              text: `SELL ${spread.entryCredit.toFixed(2)}cr ×${spread.qty}`,
            }]);
          });
        }
        chart.timeScale().fitContent();
        const onResize = () => chart.applyOptions({ width: el.clientWidth });
        onResize();
        window.addEventListener("resize", onResize);
        onResizeRef = onResize;
      });

    return () => {
      disposed = true;
      if (onResizeRef) window.removeEventListener("resize", onResizeRef);
      chartRef.current?.remove();
      chartRef.current = null;
    };
  }, [spread.underlying, spread.shortStrike, spread.longStrike, spread.entryCredit,
      spread.openTs, spread.qty, themeTick, tf]);

  const width = spread.shortStrike - spread.longStrike;
  const maxProfit = spread.entryCredit * 100 * spread.qty;
  const maxLoss = (width - spread.entryCredit) * 100 * spread.qty;
  const breakeven = spread.shortStrike - spread.entryCredit;
  const toBreakeven = spot !== undefined ? spot - breakeven : null;
  // Exit rules mirrored from agent/config.py (floored by min_exit_band_usd 0.10).
  const targetPerShare = Math.max(0.5 * spread.entryCredit, 0.10);
  const stopPerShare = Math.max(2 * spread.entryCredit, 0.10);

  return (
    <div className="mt-3 border-t pt-4" style={{ borderColor: "var(--grid)" }}>
      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <div className="eyebrow mb-2">payoff at expiration</div>
          <PayoffDiagram detailed w={520} h={210}
            shortStrike={spread.shortStrike} longStrike={spread.longStrike}
            credit={spread.entryCredit} spot={spot} />
        </div>
        <div className="grid grid-cols-2 content-start gap-x-6 gap-y-4 sm:grid-cols-3">
          <Level label="max profit" value={`+${usd2(maxProfit)}`} tone="var(--delta-up)" />
          <Level label="max loss" value={`−${usd2(maxLoss)}`} tone="var(--delta-down)" />
          <Level label="breakeven" value={breakeven.toFixed(2)} />
          <Level label="to breakeven"
            value={toBreakeven == null ? "—"
              : `${toBreakeven >= 0 ? "+" : ""}${toBreakeven.toFixed(2)} (${((toBreakeven / breakeven) * 100).toFixed(1)}%)`}
            tone={toBreakeven == null || toBreakeven >= 0 ? "var(--delta-up)" : "var(--delta-down)"} />
          <Level label="P&L at mid"
            value={spread.midPl == null ? "—" : `${spread.midPl >= 0 ? "+" : ""}${usd2(spread.midPl)}`}
            tone={(spread.midPl ?? 0) >= 0 ? "var(--delta-up)" : "var(--delta-down)"} />
          <Level label="cost to close"
            value={spread.midCost == null ? "—" : usd2(spread.midCost * 100 * spread.qty)} />
          <Level label="take profit"
            value={targetPerShare <= spread.entryCredit
              ? `+${usd2(targetPerShare * 100 * spread.qty)}`
              : "held to time stop"} />
          <Level label="stop loss" value={`−${usd2(stopPerShare * 100 * spread.qty)}`} />
          <Level label="expiry" value={`${spread.expiration} · ${spread.dte}d`} />
          <Level label="entered"
            value={spread.openTs
              ? new Date(spread.openTs).toLocaleString("en-US",
                  { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
              : "—"} />
        </div>
      </div>

      <div className="mb-2 mt-4 flex items-center justify-between">
        <div className="eyebrow">
          {spread.underlying} price · strikes drawn on the chart ·{" "}
          <span className="font-mono2 normal-case" style={{ color: SMA_FAST_COLOR }}>— SMA{SMA_FAST}</span>{" "}
          <span className="font-mono2 normal-case" style={{ color: SMA_SLOW_COLOR }}>— SMA{SMA_SLOW}</span>
        </div>
        <div className="flex gap-1" role="group" aria-label="Chart timeframe">
          {TIMEFRAMES.map((t) => (
            <button key={t} onClick={() => setTf(t)} aria-pressed={t === tf}
              className="font-mono2 rounded px-2 py-0.5 text-xs transition-opacity hover:opacity-80"
              style={t === tf
                ? { background: "var(--surface-1)", color: "var(--ink-primary)" }
                : { color: "var(--ink-muted)" }}>
              {TF_LABEL[t]}
            </button>
          ))}
        </div>
      </div>
      <div ref={ref} className="w-full" />
    </div>
  );
}
