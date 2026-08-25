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

export default function EquityChart({ data }: { data: [number, number][] }) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const [themeTick, setThemeTick] = useState(0);

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

  useEffect(() => {
    if (!ref.current) return;
    chart.current = echarts.init(ref.current);
    const onResize = () => chart.current?.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.current?.dispose();
    };
  }, []);

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
        axisLabel: { color: muted, fontSize: 11 },
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
  }, [data, themeTick]);

  return <div ref={ref} className="h-64 w-full" />;
}
