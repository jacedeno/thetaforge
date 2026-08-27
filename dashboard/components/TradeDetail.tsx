"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart, CandlestickSeries, LineSeries,
  type IChartApi, type CandlestickData, type Time,
} from "lightweight-charts";
import type { Trade } from "./TradeHistory";
import {
  sma, smaLookbackMs, SMA_FAST, SMA_SLOW, SMA_FAST_COLOR, SMA_SLOW_COLOR,
} from "@/lib/sma";

const TIMEFRAMES = ["5Min", "15Min", "30Min", "1Hour", "1Day"] as const;
const TF_LABEL: Record<string, string> = {
  "5Min": "5m", "15Min": "15m", "30Min": "30m", "1Hour": "1h", "1Day": "1d",
};

interface Txn {
  at: string | null; symbol: string; side: string;
  qty: string; price: string | null; opening: boolean;
}

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function formatHolding(ms: number): string {
  if (ms < 90_000) return `${Math.round(ms / 1000)}s`;
  if (ms < 90 * 60_000) return `${Math.round(ms / 60_000)}m`;
  if (ms < 48 * 3_600_000) return `${(ms / 3_600_000).toFixed(1)}h`;
  return `${(ms / 86_400_000).toFixed(1)}d`;
}

export function defaultTf(holdingMs: number): string {
  if (holdingMs <= 2 * 3_600_000) return "5Min";
  if (holdingMs <= 2 * 86_400_000) return "15Min";
  return "1Hour";
}

export default function TradeDetail({ trade }: { trade: Trade }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [themeTick, setThemeTick] = useState(0);
  const holdingMs =
    (trade.close_ts ? new Date(trade.close_ts).getTime() : Date.now()) -
    new Date(trade.open_ts).getTime();
  const [tf, setTf] = useState(() => defaultTf(holdingMs));
  const [txns, setTxns] = useState<Txn[]>([]);

  useEffect(() => {
    fetch(`/api/trade-orders?short=${trade.short_symbol}&long=${trade.long_symbol}`)
      .then((r) => r.json())
      .then((j) => setTxns(j.transactions ?? []))
      .catch(() => {});
  }, [trade.short_symbol, trade.long_symbol]);

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
    // Size the window to the trade: a minutes-long trade gets a session-scale
    // view instead of the same fixed ±days a week-long trade needs.
    const span = Math.max(closeMs - openMs, 60_000);
    const pad = Math.max(span * 2, 3 * 3_600_000);
    // Extra lookback so the SMAs are warm well before the entry marker.
    const from = new Date(openMs - pad - smaLookbackMs(tf)).toISOString();
    const to = new Date(Math.min(closeMs + pad, Date.now() - 16 * 60_000)).toISOString();

    let disposed = false;
    let onResizeRef: (() => void) | null = null;

    fetch(`/api/bars?symbol=${trade.underlying}&from=${from}&to=${to}&tf=${tf}`)
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

        // The signal's own averages, so the entry can be checked against the
        // cross that fired it: fast orange, slow red.
        for (const [period, color] of [
          [SMA_FAST, SMA_FAST_COLOR], [SMA_SLOW, SMA_SLOW_COLOR],
        ] as [number, string][]) {
          chart.addSeries(LineSeries, {
            color, lineWidth: 1, priceLineVisible: false,
            lastValueVisible: false, crosshairMarkerVisible: false,
          }).setData(sma(bars, period));
        }

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

        // A logical (bar-index) range survives overnight/weekend session gaps
        // that a time range would stretch across. Short trades get a window
        // around their markers; long ones still fit everything.
        const idx = (ms: number) => {
          let best = 0;
          bars.forEach((b, i) => {
            if (Math.abs((b.time as number) * 1000 - ms) <
                Math.abs((bars[best].time as number) * 1000 - ms)) best = i;
          });
          return best;
        };
        const iOpen = idx(openMs), iClose = idx(closeMs);
        if (iClose - iOpen < bars.length / 3) {
          const padBars = Math.max(12, (iClose - iOpen) * 2);
          chart.timeScale().setVisibleLogicalRange({
            from: Math.max(0, iOpen - padBars),
            to: Math.min(bars.length - 1, iClose + padBars),
          });
        } else {
          chart.timeScale().fitContent();
        }
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
    // Scalar deps only: TradeHistory hands us a NEW trade object every 30s
    // poll — depending on the object identity rebuilt the chart twice a
    // minute and wiped any zoom the user had.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trade.open_order_id, trade.open_ts, trade.close_ts, trade.underlying,
      trade.short_strike, trade.long_strike, trade.entry_credit,
      trade.exit_debit, trade.qty, themeTick, tf]);

  const quickFlip = trade.close_ts != null && holdingMs < 15 * 60_000;
  const holding = trade.close_ts ? formatHolding(holdingMs) : "open";

  return (
    <div className="border-t px-4 pb-4 pt-3" style={{ borderColor: "var(--grid)" }}>
      <div className="mb-2 flex items-center justify-between">
        <span className="font-mono2 text-[11px]">
          <span style={{ color: SMA_FAST_COLOR }}>— SMA{SMA_FAST}</span>{"  "}
          <span style={{ color: SMA_SLOW_COLOR }}>— SMA{SMA_SLOW}</span>
        </span>
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
      {txns.length > 0 && (
        <div className="mt-4">
          <div className="eyebrow mb-2">transactions</div>
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]" style={{ fontVariantNumeric: "tabular-nums" }}>
              <tbody>
                {txns.map((t, i) => (
                  <tr key={i} className="border-b last:border-b-0" style={{ borderColor: "var(--grid)" }}>
                    <td className="py-1.5 pr-3 whitespace-nowrap" style={{ color: "var(--ink-muted)" }}>
                      {t.at ? new Date(t.at).toLocaleString("en-US",
                        { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—"}
                    </td>
                    <td className="py-1.5 pr-3 font-mono2 text-xs">{t.symbol}</td>
                    <td className="py-1.5 pr-3 font-medium"
                      style={{ color: t.side === "SELL" ? "var(--delta-up)" : "var(--delta-down)" }}>
                      {t.side}
                    </td>
                    <td className="py-1.5 pr-3" style={{ color: "var(--ink-muted)" }}>
                      {t.opening ? "open" : "close"}
                    </td>
                    <td className="py-1.5 pr-3 text-right">{t.qty}</td>
                    <td className="py-1.5 text-right">{t.price ? `$${t.price}` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-2 flex justify-between border-t pt-2 text-[13px]"
            style={{ borderColor: "var(--grid)" }}>
            <span style={{ color: "var(--ink-secondary)" }}>Net gain</span>
            <span className="font-semibold"
              style={{ color: (trade.realized_pl ?? 0) >= 0 ? "var(--delta-up)" : "var(--delta-down)" }}>
              {trade.realized_pl == null ? "open" :
                `${trade.realized_pl >= 0 ? "+" : ""}$${trade.realized_pl.toFixed(2)}`}
            </span>
          </div>
        </div>
      )}

      <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-[13px] sm:grid-cols-4"
        style={{ color: "var(--ink-secondary)" }}>
        <div><span className="eyebrow">structure</span><br />
          {trade.short_strike}/{trade.long_strike} put credit ×{trade.qty}</div>
        <div><span className="eyebrow">entry → exit</span><br />
          {trade.entry_credit.toFixed(2)}cr → {trade.exit_debit != null ? `${trade.exit_debit.toFixed(2)}db` : "—"}</div>
        <div><span className="eyebrow">holding</span><br />
          <span
            style={quickFlip ? { color: "var(--critical)", fontWeight: 600 } : undefined}
            title={quickFlip ? "closed within one monitor pass — worth a look at why" : undefined}>
            {holding}
          </span>{" "}· exp {trade.expiration}</div>
        <div><span className="eyebrow">why</span><br />
          {trade.signal_strength != null ? `signal ${trade.signal_strength}` : "—"}
          {trade.exit_reason ? ` → ${trade.exit_reason}` : ""}</div>
      </div>
    </div>
  );
}
