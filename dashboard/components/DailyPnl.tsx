"use client";

import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { Trade } from "./TradeHistory";

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export default function DailyPnl() {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const [days, setDays] = useState<[string, number][]>([]);

  useEffect(() => {
    const load = () =>
      fetch("/api/trades").then((r) => r.json()).then((j) => {
        const byDay = new Map<string, number>();
        for (const t of (j.trades ?? []) as Trade[]) {
          if (t.status !== "closed" || !t.close_ts) continue;
          const d = t.close_ts.slice(0, 10);
          byDay.set(d, (byDay.get(d) ?? 0) + (t.realized_pl ?? 0));
        }
        setDays([...byDay.entries()].sort((a, b) => a[0].localeCompare(b[0])).slice(-10));
      }).catch(() => {});
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (!ref.current) return;
    chart.current = echarts.init(ref.current);
    const onResize = () => chart.current?.resize();
    window.addEventListener("resize", onResize);
    return () => { window.removeEventListener("resize", onResize); chart.current?.dispose(); };
  }, []);

  useEffect(() => {
    if (!chart.current || days.length === 0) return;
    chart.current.setOption({
      backgroundColor: "transparent",
      grid: { left: 56, right: 8, top: 12, bottom: 24 },
      tooltip: {
        trigger: "axis",
        backgroundColor: token("--surface-1"), borderColor: token("--grid"),
        textStyle: { color: token("--ink-secondary"), fontSize: 12 },
        valueFormatter: (v: number) => v.toLocaleString("en-US", { style: "currency", currency: "USD" }),
      },
      xAxis: {
        type: "category",
        data: days.map(([d]) => new Date(d + "T12:00:00Z").toLocaleDateString("en-US", { weekday: "short" })),
        axisLine: { lineStyle: { color: token("--baseline") } },
        axisLabel: { color: token("--ink-muted"), fontSize: 11 },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: token("--grid") } },
        axisLabel: { color: token("--ink-muted"), fontSize: 11, formatter: (v: number) => "$" + v },
      },
      series: [{
        type: "bar", data: days.map(([, v]) => ({
          value: Math.round(v * 100) / 100,
          itemStyle: {
            color: v >= 0 ? token("--good") : token("--critical"),
            borderRadius: v >= 0 ? [4, 4, 0, 0] : [0, 0, 4, 4],
          },
        })),
        barMaxWidth: 24,
      }],
    });
  }, [days]);

  if (days.length === 0) return null;
  return (
    <section className="card mb-6 p-5">
      <h2 className="font-display mb-3 text-base font-semibold">Daily P&L</h2>
      <div ref={ref} className="h-48 w-full" />
    </section>
  );
}
