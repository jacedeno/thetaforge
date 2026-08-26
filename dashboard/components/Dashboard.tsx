"use client";

import { useCallback, useEffect, useState } from "react";
import EquityChart from "./EquityChart";
import PayoffDiagram from "./PayoffDiagram";
import BrainFeed from "./BrainFeed";
import StatusStrip from "./StatusStrip";
import ThemeToggle from "./ThemeToggle";
import TradeHistory from "./TradeHistory";
import DailyPnl from "./DailyPnl";

interface Spread {
  underlying: string;
  shortStrike: number;
  longStrike: number;
  expiration: string;
  qty: number;
  entryCredit: number;
  currentCost: number;
  unrealizedPl: number;
  midCost: number | null;
  midPl: number | null;
  dte: number;
}

interface Snapshot {
  asOf: string;
  market: { isOpen: boolean; nextOpen: string };
  account: { number: string; equity: number; lastEquity: number; optionsBuyingPower: number };
  spreads: Spread[];
  spots: Record<string, number>;
  equitySeries: [number, number][];
  error?: string;
}

const usd = (v: number) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const usd2 = (v: number) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD" });

function nextScanCountdown(): string {
  const now = new Date();
  const m = now.getMinutes();
  const next = new Date(now);
  next.setMinutes(m - (m % 15) + 15, 30, 0); // scans fire ~30s after each 15m boundary
  const s = Math.max(0, Math.floor((next.getTime() - now.getTime()) / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function StatTile({ label, value, delta }: { label: string; value: string; delta?: number }) {
  return (
    <div className="card px-5 py-4">
      <div className="text-sm" style={{ color: "var(--ink-secondary)" }}>{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
      {delta !== undefined && (
        <div className="mt-1 text-sm font-medium"
          style={{ color: delta >= 0 ? "var(--delta-up)" : "var(--delta-down)" }}>
          {delta >= 0 ? "+" : ""}{usd2(delta)} today
        </div>
      )}
    </div>
  );
}

export default function Dashboard() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [countdown, setCountdown] = useState("--:--");

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
    const c = setInterval(() => setCountdown(nextScanCountdown()), 1000);
    return () => { clearInterval(t); clearInterval(c); };
  }, [refresh]);

  if (err) return <main className="p-8 text-sm" style={{ color: "var(--critical)" }}>{err}</main>;
  if (!snap) return <main className="p-8 text-sm" style={{ color: "var(--ink-muted)" }}>Loading…</main>;

  const { account, market, spreads, spots } = snap;
  const dayPl = account.equity - account.lastEquity;
  const openRisk = spreads.reduce(
    (a, s) => a + (s.shortStrike - s.longStrike - s.entryCredit) * 100 * s.qty, 0);

  return (
    <>
    <StatusStrip marketOpen={market.isOpen} countdown={countdown} />
    <main className="mx-auto max-w-6xl px-6 py-8">
      {/* ---- Hero ---- */}
      <header className="mb-8">
        <div className="flex items-center justify-between">
          <div className="flex items-baseline gap-3">
            <span className="font-mono2 text-lg" style={{ color: "var(--accent)" }}>θ·Δ</span>
            <h1 className="font-display text-2xl font-bold tracking-tight">
              Theta<span style={{ color: "var(--series-2)" }}>Forge</span>
            </h1>
            <span className="text-sm" style={{ color: "var(--ink-muted)" }}>
              autonomous options agent · Alpaca paper
            </span>
          </div>
          <ThemeToggle />
        </div>
        <p className="mt-3 max-w-3xl text-[15px] leading-relaxed" style={{ color: "var(--ink-secondary)" }}>
          A machine-learning momentum model — validated over 3,600 equity backtests — picks the
          direction. The agent expresses it through <b style={{ color: "var(--ink-primary)" }}>defined-risk
          options credit spreads</b>, harvesting the volatility risk premium with a hard max loss on
          every position. Fully autonomous: it scans, decides, executes and manages — you are watching
          it live.
        </p>
      </header>

      {/* ---- KPI row ---- */}
      <section className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Equity" value={usd(account.equity)} delta={dayPl} />
        <StatTile label="Open spreads" value={String(spreads.length)} />
        <StatTile label="Capital at risk" value={usd(openRisk)} />
        <StatTile label="Options buying power" value={usd(account.optionsBuyingPower)} />
      </section>

      {/* ---- Equity curve ---- */}
      <section className="card mb-6 p-5">
        <h2 className="mb-3 font-display text-base font-semibold">Equity</h2>
        <EquityChart />
      </section>

      <TradeHistory />
      <DailyPnl />

      {/* ---- Open positions with payoff ---- */}
      <section className="card mb-6 p-5">
        <h2 className="mb-3 text-sm font-medium" style={{ color: "var(--ink-secondary)" }}>
          Open positions
        </h2>
        {spreads.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--ink-muted)" }}>
            No open spreads — the agent is waiting for its next signal.
          </p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {spreads.map((s) => (
              <div key={s.underlying + s.expiration}
                className="flex items-center justify-between rounded-lg border p-4"
                style={{ borderColor: "var(--grid)" }}>
                <div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-lg font-semibold">{s.underlying}</span>
                    <span className="text-sm" style={{ color: "var(--ink-secondary)" }}>
                      {s.shortStrike}/{s.longStrike} put credit ×{s.qty}
                    </span>
                  </div>
                  <div className="mt-1 text-sm" style={{ color: "var(--ink-muted)" }}>
                    exp {s.expiration} · {s.dte}d · credit {usd2(s.entryCredit)}
                  </div>
                  <div className="mt-2 flex items-baseline gap-4">
                    <div>
                      <div className="eyebrow" title="Midpoint of the current bid/ask — a live quote, and where the spread would realistically trade">
                        at mid
                      </div>
                      <div className="text-lg font-semibold"
                        style={{ color: (s.midPl ?? 0) >= 0 ? "var(--delta-up)" : "var(--delta-down)" }}>
                        {s.midPl == null ? "—" : `${s.midPl >= 0 ? "+" : ""}${usd2(s.midPl)}`}
                      </div>
                    </div>
                    <div>
                      <div className="eyebrow" title="The broker's own position mark, which can lag the live quote in thin option chains">
                        broker mark
                      </div>
                      <div className="text-sm font-medium"
                        style={{ color: "var(--ink-muted)" }}>
                        {s.unrealizedPl >= 0 ? "+" : ""}{usd2(s.unrealizedPl)}
                      </div>
                    </div>
                  </div>
                </div>
                <PayoffDiagram shortStrike={s.shortStrike} longStrike={s.longStrike}
                  credit={s.entryCredit} spot={spots[s.underlying]} />
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ---- Agent brain ---- */}
      <section className="card mb-6 p-5">
        <h2 className="mb-1 text-sm font-medium" style={{ color: "var(--ink-secondary)" }}>
          Agent brain — live decision feed
        </h2>
        <p className="mb-3 text-xs" style={{ color: "var(--ink-muted)" }}>
          Every scan, signal, veto and order, exactly as the agent reasons through it.
        </p>
        <BrainFeed />
      </section>

      {/* ---- Strategy ---- */}
      <section className="card mb-6 p-5">
        <h2 className="mb-4 text-sm font-medium" style={{ color: "var(--ink-secondary)" }}>
          How it works
        </h2>
        <div className="grid gap-6 text-sm leading-relaxed md:grid-cols-3"
          style={{ color: "var(--ink-secondary)" }}>
          <div>
            <div className="mb-1 font-mono text-xs" style={{ color: "var(--series-1)" }}>01 · SIGNAL</div>
            <b style={{ color: "var(--ink-primary)" }}>ML momentum trigger.</b> A four-condition
            SMA55/21 crossover system scans the 80 most liquid S&P 500 names on 15-minute bars.
            Signals are ranked by breakout strength; only the strongest trade.
          </div>
          <div>
            <div className="mb-1 font-mono text-xs" style={{ color: "var(--series-2)" }}>02 · STRUCTURE</div>
            <b style={{ color: "var(--ink-primary)" }}>Defined-risk spreads.</b> Bullish signal →
            sell a ~25Δ put credit spread, 7–21 DTE. Max loss is capped by construction; time decay
            works for the position every day.
          </div>
          <div>
            <div className="mb-1 font-mono text-xs" style={{ color: "var(--good)" }}>03 · MANAGE</div>
            <b style={{ color: "var(--ink-primary)" }}>Risk gates &amp; exits.</b> ≤2% equity risk per
            position, liquidity screens on every chain. Close at 50% profit, stop at 2× credit,
            never carry past 2 DTE.
          </div>
        </div>
      </section>

      {/* ---- Footer ---- */}
      <footer className="flex flex-wrap items-center justify-between gap-3 text-xs"
        style={{ color: "var(--ink-muted)" }}>
        <div className="flex gap-2">
          {["Alpaca Trading API", "MCP Server", "Alpaca CLI", "Paper Trading"].map((t) => (
            <span key={t} className="rounded-full border px-3 py-1" style={{ borderColor: "var(--grid)" }}>
              {t}
            </span>
          ))}
        </div>
        <div className="text-right">
          Built for the Alpaca AI Trading Agents Hackathon · account {account.number} ·
          refreshes every 15s · not financial advice
          <br />
          Crafted at{" "}
          <a href="https://geekendzone.com" target="_blank" rel="noopener noreferrer"
            className="font-medium underline-offset-2 hover:underline" style={{ color: "var(--accent)" }}>
            GeekendZone
          </a>
        </div>
      </footer>
    </main>
    </>
  );
}
