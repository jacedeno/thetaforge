"use client";

import { useEffect, useState } from "react";
import TradeDetail from "./TradeDetail";

export interface Trade {
  open_order_id: string;
  underlying: string;
  short_strike: number;
  long_strike: number;
  expiration: string;
  qty: number;
  open_ts: string;
  close_ts: string | null;
  entry_credit: number;
  exit_debit: number | null;
  realized_pl: number | null;
  exit_reason: string | null;
  signal_strength: number | null;
  status: string;
}

interface Stats {
  closed: number; open: number; totalPl: number;
  winRate: number | null; profitFactor: number | null;
  avgWin: number | null; avgLoss: number | null; creditCaptured: number;
}

const usd2 = (v: number) => v.toLocaleString("en-US", { style: "currency", currency: "USD" });
const pct = (v: number) => `${(v * 100).toFixed(0)}%`;

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <div className="eyebrow">{label}</div>
      <div className="mt-0.5 text-lg font-semibold" style={{ color: tone ?? "var(--ink-primary)" }}>
        {value}
      </div>
    </div>
  );
}

export default function TradeHistory() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    const load = () =>
      fetch("/api/trades").then((r) => r.json()).then((j) => {
        setTrades(j.trades ?? []);
        setStats(j.stats ?? null);
      }).catch(() => {});
    load();
    const t = setInterval(load, 30_000);
    return () => clearInterval(t);
  }, []);

  const closed = trades.filter((t) => t.status === "closed");

  return (
    <section className="card mb-6 p-5">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="font-display text-base font-semibold">Trade history</h2>
        <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
          every round trip, straight from the journal
        </span>
      </div>

      {stats && stats.closed > 0 && (
        <div className="mb-5 grid grid-cols-3 gap-4 border-b pb-4 sm:grid-cols-6"
          style={{ borderColor: "var(--grid)" }}>
          <Stat label="net P&L" value={usd2(stats.totalPl)}
            tone={stats.totalPl >= 0 ? "var(--delta-up)" : "var(--delta-down)"} />
          <Stat label="win rate" value={stats.winRate != null ? pct(stats.winRate) : "—"} />
          <Stat label="profit factor"
            value={stats.profitFactor != null ? stats.profitFactor.toFixed(2) : "∞"} />
          <Stat label="avg win" value={stats.avgWin != null ? usd2(stats.avgWin) : "—"} />
          <Stat label="avg loss" value={stats.avgLoss != null ? usd2(-stats.avgLoss) : "—"} />
          <Stat label="trades" value={`${stats.closed} closed · ${stats.open} open`} />
        </div>
      )}

      {closed.length === 0 ? (
        <p className="text-sm" style={{ color: "var(--ink-muted)" }}>
          No completed round trips yet — closed trades will appear here with their full story.
        </p>
      ) : (
        <div>
          {closed.map((t) => {
            const win = (t.realized_pl ?? 0) > 0;
            const capture = t.entry_credit > 0 && t.exit_debit != null
              ? (t.entry_credit - t.exit_debit) / t.entry_credit : null;
            const expanded = openId === t.open_order_id;
            return (
              <div key={t.open_order_id} className="rounded-lg"
                style={expanded ? { background: "var(--surface-2)" } : undefined}>
                <button onClick={() => setOpenId(expanded ? null : t.open_order_id)}
                  className="flex w-full items-center gap-4 rounded-lg px-4 py-3 text-left text-sm hover:opacity-90">
                  <span className="font-mono2 w-14 shrink-0 text-xs" style={{ color: "var(--ink-muted)" }}>
                    {new Date(t.close_ts ?? t.open_ts).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                  </span>
                  <span className="w-16 shrink-0 font-semibold">{t.underlying}</span>
                  <span className="hidden flex-1 sm:block" style={{ color: "var(--ink-secondary)" }}>
                    {t.short_strike}/{t.long_strike} put credit ×{t.qty}
                  </span>
                  <span className="w-14 shrink-0 rounded-full px-2 py-0.5 text-center text-xs font-medium"
                    style={{
                      background: win ? "color-mix(in srgb, var(--good) 15%, transparent)"
                        : "color-mix(in srgb, var(--critical) 15%, transparent)",
                      color: win ? "var(--delta-up)" : "var(--delta-down)",
                    }}>
                    {win ? "WIN" : "LOSS"}
                  </span>
                  <span className="w-24 shrink-0 text-right font-semibold"
                    style={{ color: win ? "var(--delta-up)" : "var(--delta-down)" }}>
                    {(t.realized_pl ?? 0) >= 0 ? "+" : ""}{usd2(t.realized_pl ?? 0)}
                  </span>
                  <span className="font-mono2 hidden w-24 shrink-0 text-right text-xs md:block"
                    style={{ color: "var(--ink-muted)" }}>
                    {capture != null ? `${pct(capture)} of credit` : ""}
                  </span>
                  <span className="w-4 shrink-0 text-center" style={{ color: "var(--ink-muted)" }}>
                    {expanded ? "▾" : "▸"}
                  </span>
                </button>
                {expanded && <TradeDetail trade={t} />}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
