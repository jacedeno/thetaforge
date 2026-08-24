"use client";

import { useCallback, useEffect, useState } from "react";
import EquityChart from "./EquityChart";

interface Spread {
  underlying: string;
  shortStrike: number;
  longStrike: number;
  expiration: string;
  qty: number;
  entryCredit: number;
  currentCost: number;
  unrealizedPl: number;
  dte: number;
}

interface OrderLeg { symbol: string; side: string; intent: string }
interface Order {
  id: string;
  submittedAt: string;
  status: string;
  qty: string;
  limitPrice: string | null;
  filledAvgPrice: string | null;
  legs: OrderLeg[];
}

interface Snapshot {
  asOf: string;
  market: { isOpen: boolean; nextOpen: string };
  account: { number: string; equity: number; lastEquity: number; optionsBuyingPower: number };
  spreads: Spread[];
  equitySeries: [number, number][];
  orders: Order[];
  error?: string;
}

const usd = (v: number) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const usd2 = (v: number) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD" });

function StatTile({
  label, value, delta, deltaLabel,
}: { label: string; value: string; delta?: number; deltaLabel?: string }) {
  return (
    <div className="card px-5 py-4">
      <div className="text-sm" style={{ color: "var(--ink-secondary)" }}>{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
      {delta !== undefined && (
        <div
          className="mt-1 text-sm font-medium"
          style={{ color: delta >= 0 ? "var(--delta-up)" : "var(--delta-down)" }}
        >
          {delta >= 0 ? "+" : ""}{usd2(delta)}{deltaLabel ? ` ${deltaLabel}` : ""}
        </div>
      )}
    </div>
  );
}

export default function Dashboard() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch("/api/snapshot");
      const j = (await r.json()) as Snapshot;
      if (j.error) throw new Error(j.error);
      setSnap(j);
      setErr(null);
    } catch (e) {
      setErr(String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 15_000);
    return () => clearInterval(t);
  }, [refresh]);

  if (err) return <main className="p-8 text-sm" style={{ color: "var(--critical)" }}>{err}</main>;
  if (!snap) return <main className="p-8 text-sm" style={{ color: "var(--ink-muted)" }}>Loading…</main>;

  const { account, market, spreads, orders } = snap;
  const dayPl = account.equity - account.lastEquity;
  const openRisk = spreads.reduce(
    (a, s) => a + (s.shortStrike - s.longStrike - s.entryCredit) * 100 * s.qty, 0,
  );

  return (
    <main className="mx-auto max-w-6xl px-6 py-6">
      <header className="mb-6 flex items-center justify-between">
        <div className="flex items-baseline gap-3">
          <h1 className="text-xl font-semibold tracking-tight">ThetaForge</h1>
          <span className="text-sm" style={{ color: "var(--ink-muted)" }}>
            paper · {account.number}
          </span>
        </div>
        <div className="flex items-center gap-2 text-sm" style={{ color: "var(--ink-secondary)" }}>
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: market.isOpen ? "var(--good)" : "var(--ink-muted)" }}
          />
          {market.isOpen ? "Market open" : "Market closed"}
        </div>
      </header>

      <section className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Equity" value={usd(account.equity)} delta={dayPl} deltaLabel="today" />
        <StatTile label="Open spreads" value={String(spreads.length)} />
        <StatTile label="Capital at risk" value={usd(openRisk)} />
        <StatTile label="Options buying power" value={usd(account.optionsBuyingPower)} />
      </section>

      <section className="card mb-6 p-5">
        <h2 className="mb-3 text-sm font-medium" style={{ color: "var(--ink-secondary)" }}>
          Equity — last week
        </h2>
        <EquityChart data={snap.equitySeries} />
      </section>

      <section className="card mb-6 overflow-x-auto p-5">
        <h2 className="mb-3 text-sm font-medium" style={{ color: "var(--ink-secondary)" }}>
          Open positions
        </h2>
        {spreads.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--ink-muted)" }}>No open spreads.</p>
        ) : (
          <table className="w-full text-sm" style={{ fontVariantNumeric: "tabular-nums" }}>
            <thead>
              <tr className="text-left" style={{ color: "var(--ink-muted)" }}>
                <th className="pb-2 font-normal">Underlying</th>
                <th className="pb-2 font-normal">Structure</th>
                <th className="pb-2 font-normal">Exp / DTE</th>
                <th className="pb-2 text-right font-normal">Qty</th>
                <th className="pb-2 text-right font-normal">Credit</th>
                <th className="pb-2 text-right font-normal">Cost now</th>
                <th className="pb-2 text-right font-normal">P&L</th>
              </tr>
            </thead>
            <tbody>
              {spreads.map((s) => (
                <tr key={s.underlying + s.expiration} className="border-t" style={{ borderColor: "var(--grid)" }}>
                  <td className="py-2 font-medium">{s.underlying}</td>
                  <td className="py-2">{s.shortStrike}/{s.longStrike} put credit</td>
                  <td className="py-2">{s.expiration} · {s.dte}d</td>
                  <td className="py-2 text-right">{s.qty}</td>
                  <td className="py-2 text-right">{usd2(s.entryCredit)}</td>
                  <td className="py-2 text-right">{usd2(s.currentCost)}</td>
                  <td
                    className="py-2 text-right font-medium"
                    style={{ color: s.unrealizedPl >= 0 ? "var(--delta-up)" : "var(--delta-down)" }}
                  >
                    {s.unrealizedPl >= 0 ? "+" : ""}{usd2(s.unrealizedPl)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card overflow-x-auto p-5">
        <h2 className="mb-3 text-sm font-medium" style={{ color: "var(--ink-secondary)" }}>
          Order log
        </h2>
        {orders.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--ink-muted)" }}>No option orders yet.</p>
        ) : (
          <table className="w-full text-sm" style={{ fontVariantNumeric: "tabular-nums" }}>
            <thead>
              <tr className="text-left" style={{ color: "var(--ink-muted)" }}>
                <th className="pb-2 font-normal">Submitted</th>
                <th className="pb-2 font-normal">Legs</th>
                <th className="pb-2 text-right font-normal">Qty</th>
                <th className="pb-2 text-right font-normal">Limit</th>
                <th className="pb-2 text-right font-normal">Fill</th>
                <th className="pb-2 text-right font-normal">Status</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id} className="border-t align-top" style={{ borderColor: "var(--grid)" }}>
                  <td className="py-2 whitespace-nowrap">
                    {new Date(o.submittedAt).toLocaleString("en-US", {
                      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
                    })}
                  </td>
                  <td className="py-2">
                    {o.legs.map((l) => (
                      <div key={l.symbol}>
                        <span style={{ color: "var(--ink-muted)" }}>{l.side}</span> {l.symbol}
                      </div>
                    ))}
                  </td>
                  <td className="py-2 text-right">{o.qty}</td>
                  <td className="py-2 text-right">{o.limitPrice ?? "—"}</td>
                  <td className="py-2 text-right">{o.filledAvgPrice ?? "—"}</td>
                  <td className="py-2 text-right">{o.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <footer className="mt-4 text-xs" style={{ color: "var(--ink-muted)" }}>
        Refreshes every 15s · as of {new Date(snap.asOf).toLocaleTimeString()}
      </footer>
    </main>
  );
}
