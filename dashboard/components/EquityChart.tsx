"use client";

import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent, MarkLineComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([LineChart, GridComponent, TooltipComponent, MarkLineComponent, CanvasRenderer]);

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

const RANGES = ["1H", "1D", "1W", "1M", "ALL"] as const;
type Range = (typeof RANGES)[number];

interface Point { t: number; equity: number }
interface Session { date: string; start: number; count: number }

const TIME = { hour: "numeric", minute: "2-digit" } as const;
const DAY = { month: "short", day: "numeric" } as const;

export default function EquityChart() {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const [themeTick, setThemeTick] = useState(0);
  const [range, setRange] = useState<Range>("1D");
  const [points, setPoints] = useState<Point[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [label, setLabel] = useState("this session");
  const [source, setSource] = useState("journal");

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      fetch(`/api/equity?range=${range}`)
        .then((r) => r.json())
        .then((j) => {
          if (cancelled) return;
          setPoints(j.points ?? []);
          setSessions(j.sessions ?? []);
          setLabel(j.label ?? "");
          setSource(j.source ?? "journal");
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

  const hasData = points.length > 1;

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
    if (!chart.current || points.length === 0) return;
    const series1 = token("--series-1");
    const ink2 = token("--ink-secondary");
    const muted = token("--ink-muted");
    const grid = token("--grid");
    const surface = token("--surface-1");

    // The axis is ORDINAL, not time: one slot per sample. That is what keeps
    // the overnight and weekend gaps off the chart — on a time axis they are
    // real distance, and the curve crosses them as a long flat run that says
    // nothing. Here the last bar of a session sits next to the first bar of
    // the next, and a divider marks where the day changed.
    const multi = sessions.length > 1;
    const starts = new Set(sessions.slice(1).map((s) => s.start));

    chart.current.setOption({
      backgroundColor: "transparent",
      grid: { left: 64, right: 16, top: 16, bottom: 28 },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross", lineStyle: { color: muted, width: 1 } },
        backgroundColor: surface,
        borderColor: grid,
        textStyle: { color: ink2, fontSize: 12 },
        formatter: (params: { dataIndex: number; value: number }[]) => {
          const p = params[0];
          const when = new Date(points[p.dataIndex].t);
          const money = p.value.toLocaleString("en-US", { style: "currency", currency: "USD" });
          return `${when.toLocaleString("en-US", { ...DAY, ...TIME })}<br/><b>${money}</b>`;
        },
      },
      xAxis: {
        type: "category",
        data: points.map((p) => p.t),
        boundaryGap: false,
        axisLine: { lineStyle: { color: grid } },
        axisTick: { show: false },
        // Across sessions, label the boundaries and nothing else — a
        // time-of-day tick repeated per session reads as noise.
        axisLabel: {
          color: muted,
          fontSize: 11,
          interval: multi ? (i: number) => i === 0 || starts.has(i) : "auto",
          formatter: (v: string) =>
            new Date(Number(v)).toLocaleString("en-US", multi ? DAY : TIME),
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
          data: points.map((p) => p.equity),
          showSymbol: false,
          lineStyle: { color: series1, width: 2, cap: "round", join: "round" },
          areaStyle: { color: series1, opacity: 0.1 },
          markLine: multi
            ? {
                silent: true,
                symbol: "none",
                label: { show: false },
                lineStyle: { color: grid, width: 1, type: "dashed" },
                data: [...starts].map((i) => ({ xAxis: i })),
              }
            : undefined,
        },
      ],
    });
  }, [points, sessions, themeTick, range, hasData]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="eyebrow">
          {label}
          {source === "broker" && " · broker daily buckets"}
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
