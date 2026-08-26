"use client";

import { useEffect, useState } from "react";

interface Ev {
  ts: string;
  type: string;
  [k: string]: unknown;
}

const COLORS: Record<string, string> = {
  scan: "var(--ink-muted)",
  signal: "var(--series-1)",
  veto: "var(--ink-secondary)",
  order_open: "var(--good)",
  exit_signal: "var(--series-2)",
  order_close: "var(--series-2)",
  order_stale: "var(--ink-muted)",
  order_reprice: "var(--series-1)",
  order_reprice_skipped: "var(--ink-muted)",
};

function line(e: Ev): string {
  switch (e.type) {
    case "scan": return `scan complete — ${e.signals} signal(s) across ${e.universe} symbols`;
    case "signal": return `signal ${e.symbol} ${e.direction} @ ${e.price} · strength ${e.strength}`;
    case "veto": return `veto ${e.symbol} — ${e.reason}`;
    case "order_open": return `OPEN ${e.symbol} credit spread x${e.qty} @ $${e.credit} credit · max risk $${e.max_risk} · Δ${e.delta}`;
    case "exit_signal": return `exit ${e.symbol} — ${e.reason}`;
    case "order_close": return `CLOSE ${e.symbol} x${e.qty} @ $${e.limit} — ${e.reason}`;
    case "order_stale": return `entry unfilled for ${e.age_s}s — cancelled`;
    case "order_reprice": return `REPRICE at natural $${e.natural} x${e.qty} — trading price for certainty`;
    case "order_reprice_skipped": return `reprice skipped — ${e.reason}`;
    default: return JSON.stringify(e);
  }
}

export default function BrainFeed() {
  const [events, setEvents] = useState<Ev[]>([]);

  useEffect(() => {
    const load = () =>
      fetch("/api/events").then((r) => r.json()).then((j) => setEvents(j.events ?? []));
    load();
    const t = setInterval(load, 10_000);
    return () => clearInterval(t);
  }, []);

  if (events.length === 0)
    return (
      <p className="text-sm" style={{ color: "var(--ink-muted)" }}>
        The agent is idle — decisions will stream here when the market opens.
      </p>
    );

  return (
    <div className="max-h-96 overflow-y-auto font-mono text-[13px] leading-6"
      style={{ fontFamily: "var(--font-mono, ui-monospace, monospace)" }}>
      {events.map((e, i) => (
        <div key={i} className="flex gap-3 border-t py-1 first:border-t-0"
          style={{ borderColor: "var(--grid)" }}>
          <span className="shrink-0" style={{ color: "var(--ink-muted)" }}>
            {new Date(e.ts).toLocaleTimeString("en-US", { hour12: false })}
          </span>
          <span style={{ color: COLORS[e.type] ?? "var(--ink-secondary)" }}>{line(e)}</span>
        </div>
      ))}
    </div>
  );
}
