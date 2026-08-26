"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart, CandlestickSeries, type IChartApi, type CandlestickData, type Time,
} from "lightweight-charts";
import PayoffDiagram from "./PayoffDiagram";

const TIMEFRAMES = ["5Min", "15Min", "1Hour", "1Day"] as const;
const TF_LABEL: Record<string, string> = { "5Min": "5m", "15Min": "15m", "1Hour": "1h", "1Day": "1d" };

export interface OpenSpread {
  underlying: string;
  shortStrike: number;
  longStrike: number;
  expiration: string;
  qty: number;
  entryCredit: number;
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
  const [tf, setTf] = useState("15Min");

  useEffect(() => {
    const mo = new MutationObserver(() => setThemeTick((t) => t + 1));
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => mo.disconnect();
  }, []);

  useEffect(() => {
    if (!ref.current) return;
    const el = ref.current;
    const to = new Date(Date.now() - 16 * 60_000).toISOString();
    const from = new Date(Date.now() - 7 * 86_400_000).toISOString();

    let disposed = false;
    let onResizeRef: (() => void) | null = null;

    fetch(`/api/bars?symbol=${spread.underlying}&from=${from}&to=${to}&tf=${tf}`)
      .then((r) => r.json())
      .then(({ bars }: { bars: CandlestickData<Time>[] }) => {
        if (disposed || !bars?.length) return;
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
  }, [spread.underlying, spread.shortStrike, spread.longStrike, spread.entryCredit, themeTick, tf]);

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
        </div>
      </div>

      <div className="mb-2 mt-4 flex items-center justify-between">
        <div className="eyebrow">{spread.underlying} price · strikes drawn on the chart</div>
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
