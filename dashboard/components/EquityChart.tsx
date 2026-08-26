"use client";

import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

const RANGES = ["1H", "1D", "1W", "1M", "ALL"] as const;
type Range = (typeof RANGES)[number];

export default function EquityChart() {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const [themeTick, setThemeTick] = useState(0);
  const [range, setRange] = useState<Range>("1D");
  const [data, setData] = useState<[number, number][]>([]);
  const [label, setLabel] = useState("today");
  const [fellBack, setFellBack] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      fetch(`/api/equity?range=${range}`)
        .then((r) => r.json())
        .then((j) => {
          if (cancelled) return;
          setData(j.points ?? []);
          setLabel(j.label ?? "");
          setFellBack(Boolean(j.fellBack));
        })
        .catch(() => {});
    load();
    const t = setInterval(load, 30_000);
    return () => { cancelled = true; clearInterval(t); };
  }, [range]);

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

  const hasData = data.length > 1;

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
    if (!chart.current || data.length === 0) return;
    const series1 = token("--series-1");
    const ink2 = token("--ink-secondary");
    const muted = token("--ink-muted");
    const grid = token("--grid");
    const surface = token("--surface-1");

    chart.current.setOption({
      backgroundColor: "transparent",
      grid: { left: 64, right: 16, top: 16, bottom: 28 },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross", lineStyle: { color: muted, width: 1 } },
        backgroundColor: surface,
        borderColor: grid,
        textStyle: { color: ink2, fontSize: 12 },
        valueFormatter: (v: number) =>
          v.toLocaleString("en-US", { style: "currency", currency: "USD" }),
      },
      xAxis: {
        type: "time",
        axisLine: { lineStyle: { color: grid } },
        axisLabel: {
          color: muted,
          fontSize: 11,
          formatter: (v: number) =>
            new Date(v).toLocaleString("en-US",
              range === "1H" || range === "1D"
                ? { hour: "numeric", minute: "2-digit" }
                : { month: "short", day: "numeric" }),
        },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLabel: {
          color: muted,
          fontSize: 11,
          formatter: (v: number) => "$" + v.toLocaleString("en-US"),
        },
        splitLine: { lineStyle: { color: grid, width: 1 } },
      },
      series: [
        {
          type: "line",
          data,
          showSymbol: false,
          lineStyle: { color: series1, width: 2, cap: "round", join: "round" },
          areaStyle: { color: series1, opacity: 0.1 },
        },
      ],
    });
  }, [data, themeTick, range, hasData]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="eyebrow">
          {label}
          {fellBack && " · shortest range with data"}
        </span>
        <div className="flex gap-1" role="group" aria-label="Equity time range">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              aria-pressed={r === range}
              className="font-mono2 rounded px-2 py-1 text-xs transition-opacity hover:opacity-80"
              style={
                r === range
                  ? { background: "var(--surface-2)", color: "var(--ink-primary)" }
                  : { color: "var(--ink-muted)" }
              }
            >
              {r}
            </button>
          ))}
        </div>
      </div>
      {hasData ? (
        <div ref={ref} className="h-64 w-full" />
      ) : (
        <div className="flex h-64 items-center justify-center text-sm"
          style={{ color: "var(--ink-muted)" }}>
          Not enough history yet — the curve starts once the account has traded.
        </div>
      )}
    </div>
  );
}
