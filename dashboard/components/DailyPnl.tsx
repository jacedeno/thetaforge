"use client";

import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export default function DailyPnl() {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const [themeTick, setThemeTick] = useState(0);
  const [days, setDays] = useState<{ date: string; pl: number; live: boolean }[]>([]);

  useEffect(() => {
    const load = () =>
      fetch("/api/daily-pnl").then((r) => r.json())
        .then((j) => setDays(j.days ?? []))
        .catch(() => {});
    load();
    const t = setInterval(load, 20_000);
    return () => clearInterval(t);
  }, []);

  // Re-read CSS tokens when the theme changes (OS setting or data-theme toggle).
  useEffect(() => {
    const bump = () => setThemeTick((t) => t + 1);
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", bump);
    const mo = new MutationObserver(bump);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => {
      mq.removeEventListener("change", bump);
      mo.disconnect();
    };
  }, []);

  const hasData = days.length > 0;

  // Keyed on hasData: on first render there is no data, the container is not
  // mounted and ref.current is null — an []-keyed init would never run again
  // and the chart would stay blank forever.
  useEffect(() => {
    if (!ref.current || !hasData) return;
    chart.current = echarts.init(ref.current);
    const onResize = () => chart.current?.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.current?.dispose();
      chart.current = null;
    };
  }, [hasData]);

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
        data: days.map((d) =>
          d.live ? "today · live"
                 : new Date(d.date + "T12:00:00Z").toLocaleDateString("en-US", { weekday: "short" })),
        axisLine: { lineStyle: { color: token("--baseline") } },
        axisLabel: { color: token("--ink-muted"), fontSize: 11 },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: token("--grid") } },
        axisLabel: { color: token("--ink-muted"), fontSize: 11, formatter: (v: number) => "$" + v },
      },
      series: [{
        type: "bar", data: days.map((d) => ({
          value: Math.round(d.pl * 100) / 100,
          itemStyle: {
            color: d.pl >= 0 ? token("--good") : token("--critical"),
            borderRadius: d.pl >= 0 ? [4, 4, 0, 0] : [0, 0, 4, 4],
            opacity: d.live ? 0.65 : 1,   // floating, still moving
          },
        })),
        barMaxWidth: 24,
      }],
    });
  }, [days, themeTick, hasData]);

  return (
    <section className="card mb-6 p-5">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="font-display text-base font-semibold">Daily P&L</h2>
        <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
          today updates live — the lighter bar is still in motion
        </span>
      </div>
      {hasData ? (
        <div ref={ref} className="h-48 w-full" />
      ) : (
        <div className="flex h-48 items-center justify-center text-sm"
          style={{ color: "var(--ink-muted)" }}>
          No closed sessions yet — bars appear after the first full trading day.
        </div>
      )}
    </section>
  );
}
