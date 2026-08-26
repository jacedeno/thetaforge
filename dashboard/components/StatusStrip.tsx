"use client";

import { useEffect, useState } from "react";

interface Health {
  agent: {
    alive: boolean; degraded?: boolean; consecutiveFailures?: number;
    lastBeat: string | null; lastScan: string | null;
    started: string | null; iteration: number | null; marketOpen: boolean | null;
  };
  eventsToday: number;
}

function ago(iso: string | null): string {
  if (!iso) return "—";
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 90) return `${s}s ago`;
  if (s < 5400) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

function uptime(iso: string | null): string {
  if (!iso) return "—";
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m`;
}

export default function StatusStrip({ marketOpen, countdown }: { marketOpen: boolean; countdown: string }) {
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    const load = () => fetch("/api/health").then((r) => r.json()).then(setHealth).catch(() => {});
    load();
    const t = setInterval(load, 15_000);
    return () => clearInterval(t);
  }, []);

  const alive = health?.agent.alive ?? false;
  const degraded = health?.agent.degraded ?? false;
  const stateColor = !alive ? "var(--critical)" : degraded ? "var(--series-2)" : "var(--good)";
  const stateLabel = !alive ? "AGENT DOWN"
    : degraded ? `AGENT DEGRADED (${health?.agent.consecutiveFailures} failed passes)` : "AGENT LIVE";

  const Item = ({ label, value, tone }: { label: string; value: React.ReactNode; tone?: string }) => (
    <span className="flex items-center gap-1.5 whitespace-nowrap">
      <span style={{ color: "var(--ink-muted)" }}>{label}</span>
      <span style={{ color: tone ?? "var(--ink-secondary)" }}>{value}</span>
    </span>
  );

  return (
    <div className="font-mono2 flex items-center gap-5 overflow-x-auto border-b px-6 py-2 text-[12px]"
      style={{ borderColor: "var(--grid)", background: "var(--surface-1)" }}>
      <span className="flex items-center gap-2 whitespace-nowrap font-medium"
        style={{ color: stateColor }}>
        <span className={`inline-block h-2 w-2 rounded-full ${alive && !degraded ? "live-dot" : ""}`}
          style={{ background: stateColor }} />
        {stateLabel}
      </span>
      <Item label="market" value={marketOpen ? "OPEN" : "CLOSED"}
        tone={marketOpen ? "var(--good)" : undefined} />
      {marketOpen && <Item label="next scan" value={countdown} />}
      <Item label="last scan" value={ago(health?.agent.lastScan ?? null)} />
      <Item label="heartbeat" value={ago(health?.agent.lastBeat ?? null)} />
      <Item label="uptime" value={uptime(health?.agent.started ?? null)} />
      <Item label="decisions today" value={health?.eventsToday ?? 0} />
    </div>
  );
}
