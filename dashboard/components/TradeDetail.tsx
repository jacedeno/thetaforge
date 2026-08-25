"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart, CandlestickSeries, type IChartApi, type CandlestickData, type Time,
} from "lightweight-charts";
import type { Trade } from "./TradeHistory";

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export default function TradeDetail({ trade }: { trade: Trade }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [themeTick, setThemeTick] = useState(0);

  useEffect(() => {
    const mo = new MutationObserver(() => setThemeTick((t) => t + 1));
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => mo.disconnect();
  }, []);

  useEffect(() => {
    if (!ref.current) return;
    const el = ref.current;

    const openMs = new Date(trade.open_ts).getTime();
    const closeMs = trade.close_ts ? new Date(trade.close_ts).getTime() : Date.now();
    const from = new Date(openMs - 2 * 86_400_000).toISOString();
    const to = new Date(Math.min(closeMs + 1 * 86_400_000, Date.now() - 16 * 60_000)).toISOString();

    let disposed = false;

    fetch(`/api/bars?symbol=${trade.underlying}&from=${from}&to=${to}`)
      .then((r) => r.json())
      .then(({ bars }: { bars: CandlestickData<Time>[] }) => {
        if (disposed || !bars?.length) return;

        const up = token("--good"), down = token("--critical");
        const chart = createChart(el, {
          height: 300,
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

        // The options twist: strikes as price lines — the profit frontier is visible.
        series.createPriceLine({
          price: trade.short_strike, color: token("--series-2"), lineWidth: 2,
          lineStyle: 0, title: `short ${trade.short_strike} — profit above`,
        });
        series.createPriceLine({
          price: trade.long_strike, color: token("--ink-muted"), lineWidth: 1,
          lineStyle: 2, title: `long ${trade.long_strike} — max loss below`,
        });
        series.createPriceLine({
          price: trade.short_strike - trade.entry_credit, color: token("--series-1"),
          lineWidth: 1, lineStyle: 3, title: "breakeven",
        });

        const nearest = (ms: number) => {
          let best = bars[0].time as number;
          for (const b of bars) {
            if (Math.abs((b.time as number) * 1000 - ms) < Math.abs(best * 1000 - ms))
              best = b.time as number;
          }
          return best as Time;
        };
        interface Marker {
          time: Time; position: "belowBar" | "aboveBar";
          color: string; shape: "arrowUp" | "arrowDown"; text: string;
        }
        const markers: Marker[] = [{
          time: nearest(openMs), position: "belowBar",
          color: token("--series-2"), shape: "arrowUp",
          text: `SELL ${trade.entry_credit.toFixed(2)}cr ×${trade.qty}`,
        }];
        if (trade.close_ts) {
          markers.push({
            time: nearest(closeMs), position: "aboveBar",
            color: token("--series-1"), shape: "arrowDown",
            text: `CLOSE ${trade.exit_debit?.toFixed(2) ?? ""}db`,
          });
        }
        import("lightweight-charts").then(({ createSeriesMarkers }) => {
          if (!disposed) createSeriesMarkers(series, markers);
        });

        chart.timeScale().fitContent();
        const onResize = () => chart.applyOptions({ width: el.clientWidth });
        onResize();
        window.addEventListener("resize", onResize);
      });

    return () => {
      disposed = true;
      chartRef.current?.remove();
      chartRef.current = null;
    };
  }, [trade, themeTick]);

  const holding = trade.close_ts
    ? `${Math.round((new Date(trade.close_ts).getTime() - new Date(trade.open_ts).getTime()) / 3_600_000)}h`
    : "open";

  return (
    <div className="border-t px-4 pb-4 pt-3" style={{ borderColor: "var(--grid)" }}>
      <div ref={ref} className="w-full" />
      <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 text-[13px] sm:grid-cols-4"
        style={{ color: "var(--ink-secondary)" }}>
        <div><span className="eyebrow">structure</span><br />
          {trade.short_strike}/{trade.long_strike} put credit ×{trade.qty}</div>
        <div><span className="eyebrow">entry → exit</span><br />
          {trade.entry_credit.toFixed(2)}cr → {trade.exit_debit != null ? `${trade.exit_debit.toFixed(2)}db` : "—"}</div>
        <div><span className="eyebrow">holding</span><br />{holding} · exp {trade.expiration}</div>
        <div><span className="eyebrow">why</span><br />
          {trade.signal_strength != null ? `signal ${trade.signal_strength}` : "—"}
          {trade.exit_reason ? ` → ${trade.exit_reason}` : ""}</div>
      </div>
    </div>
  );
}
