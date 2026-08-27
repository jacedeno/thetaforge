"use client";

import { useCallback, useEffect, useState } from "react";
import EquityChart from "./EquityChart";
import PayoffDiagram from "./PayoffDiagram";
import PositionDetail from "./PositionDetail";
import BrainFeed from "./BrainFeed";
import StatusStrip from "./StatusStrip";
import ThemeToggle from "./ThemeToggle";
import TradeHistory from "./TradeHistory";
import DailyPnl from "./DailyPnl";

interface Spread {
  underlying: string;
  shortSymbol: string;
  longSymbol: string;
  shortStrike: number;
  longStrike: number;
  expiration: string;
  qty: number;
  entryCredit: number;
  openTs: string | null;
  signalTs: string | null;
  signalPrice: number | null;
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
  const [openPos, setOpenPos] = useState<string | null>(null);

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
            {spreads.map((s) => {
              const key = s.underlying + s.expiration;
              const expanded = openPos === key;
              return (
                <div key={key}
                  className="rounded-lg border p-4"
                  style={{
                    borderColor: "var(--grid)",
                    gridColumn: expanded ? "1 / -1" : undefined,
                  }}>
                  <button onClick={() => setOpenPos(expanded ? null : key)}
                    className="flex w-full items-center justify-between gap-3 text-left hover:opacity-90"
                    aria-expanded={expanded}>
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
                    <div className="flex items-center gap-2">
                      {!expanded && (
                        <PayoffDiagram shortStrike={s.shortStrike} longStrike={s.longStrike}
                          credit={s.entryCredit} spot={spots[s.underlying]} />
                      )}
                      <span className="shrink-0" style={{ color: "var(--ink-muted)" }}>
                        {expanded ? "▾" : "▸"}
                      </span>
                    </div>
                  </button>
                  {expanded && <PositionDetail spread={s} spot={spots[s.underlying]} />}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* ---- Agent brain ---- */}
      <section className="card mb-6 p-5">
        <h2 className="mb-1 text-sm font-medium" style={{ color: "var(--ink-secondary)" }}>
          Agent brain — live decision feed
        </h2>
        <p className="mb-3 text-xs" style={{ color: "var(--ink-muted)" }}>
          Deterministic rules, narrated live — every scan, signal, veto and order, exactly as the agent decides them.
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
            SMA55/21 crossover system scans the 80 most liquid S&P 500 names on 5-minute bars.
            Overextended breakouts are skipped — calm crosses trade first, one sector per scan.
          </div>
          <div>
            <div className="mb-1 font-mono text-xs" style={{ color: "var(--series-2)" }}>02 · STRUCTURE</div>
            <b style={{ color: "var(--ink-primary)" }}>Defined-risk spreads.</b> Bullish signal →
            sell a ~25Δ put credit spread, 7–21 DTE. Max loss is capped by construction; time decay
            works for the position every day.
          </div>
          <div>
            <div className="mb-1 font-mono text-xs" style={{ color: "var(--good)" }}>03 · MANAGE</div>
            <b style={{ color: "var(--ink-primary)" }}>Risk gates &amp; exits.</b> ≤1.5% equity risk per
            position, liquidity screens on every chain. Close at 50% profit, stop at 2× credit,
            never carry past 2 DTE.
          </div>
        </div>
      </section>

      {/* ---- Footer ---- */}
      <footer className="text-xs" style={{ color: "var(--ink-muted)" }}>
        <div className="flex flex-wrap items-center justify-between gap-3">
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
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-center justify-between gap-4 border-t pt-4"
          style={{ borderColor: "var(--grid)" }}>
          <div>
            <a href="https://geekendzone.com" target="_blank" rel="noopener noreferrer"
              className="font-display text-sm font-semibold underline-offset-2 hover:underline"
              style={{ color: "var(--accent)" }}>
              GeekendZone
            </a>
            <p className="mt-0.5">Crafted by Jose Cedeno. Built on bare metal.</p>
          </div>
          <nav className="flex flex-wrap items-center gap-4" aria-label="Elsewhere">
            {[
              {
                href: "https://linkedin.com/in/joseangelcedeno", label: "LinkedIn",
                d: "M4.98 3.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5zM3 9h4v12H3zM9 9h3.8v1.7h.05c.53-1 1.83-2.05 3.77-2.05 4.03 0 4.78 2.65 4.78 6.1V21h-4v-5.4c0-1.29-.02-2.95-1.8-2.95-1.8 0-2.08 1.4-2.08 2.85V21H9z",
              },
              {
                href: "https://github.com/jacedeno", label: "GitHub",
                d: "M12 .5C5.73.5.5 5.73.5 12a11.5 11.5 0 0 0 7.86 10.92c.58.1.79-.25.79-.56v-2c-3.2.7-3.88-1.54-3.88-1.54-.53-1.34-1.29-1.7-1.29-1.7-1.05-.72.08-.7.08-.7 1.16.08 1.77 1.2 1.77 1.2 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.56-.29-5.25-1.28-5.25-5.7 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.18 1.18a11 11 0 0 1 5.8 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.76.12 3.05.74.81 1.18 1.84 1.18 3.1 0 4.43-2.69 5.4-5.26 5.69.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.5 11.5 0 0 0 23.5 12C23.5 5.73 18.27.5 12 .5z",
              },
              {
                href: "mailto:jacedeno@geekendzone.com", label: "Email",
                d: "M20 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 4.24-8 4.62-8-4.62V6l8 4.62L20 6z",
              },
            ].map((l) => (
              <a key={l.label} href={l.href}
                {...(l.href.startsWith("http")
                  ? { target: "_blank", rel: "noopener noreferrer" } : {})}
                className="flex items-center gap-1.5 transition-colors"
                style={{ color: "var(--ink-secondary)" }}
                onMouseEnter={(e) => (e.currentTarget.style.color = "var(--accent)")}
                onMouseLeave={(e) => (e.currentTarget.style.color = "var(--ink-secondary)")}>
                <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"
                  className="h-3.5 w-3.5">
                  <path d={l.d} />
                </svg>
                {l.label}
              </a>
            ))}
            <a href="https://geekendzone.com" target="_blank" rel="noopener noreferrer"
              className="font-mono2 underline-offset-2 hover:underline"
              style={{ color: "var(--ink-secondary)" }}>
              geekendzone.com
            </a>
          </nav>
        </div>
      </footer>
    </main>
    </>
  );
}
