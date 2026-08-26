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
  position_unmanageable: "var(--critical)",
  journal_price_mismatch: "var(--ink-secondary)",
};

function friendlyVeto(reason: string): string {
  if (reason.includes("chain/liquidity")) return "its options chain isn't liquid enough to trade well";
  if (reason.includes("budget")) return "one spread would exceed the per-position risk budget";
  if (reason.includes("already holding")) return "we already hold a position there";
  if (reason.includes("sector cap")) return "another name from the same sector is already entering this scan";
  if (reason.includes("max open")) return "the portfolio is at its position limit";
  if (reason.includes("buying power")) return "not enough option buying power right now";
  return reason;
}

function friendlyExit(reason: string): string {
  if (reason.includes("profit target")) return "profit target reached — locking in the win early";
  if (reason.includes("stop loss")) return "stop hit — cutting the loss before it grows";
  if (reason.includes("time stop")) return "too close to expiration — never carry into the last days";
  return reason;
}

function line(e: Ev): string {
  switch (e.type) {
    case "scan":
      return e.signals === 0
        ? `scanned ${e.universe} symbols on the 5-min close — no fresh momentum triggers`
        : `scanned ${e.universe} symbols — ${e.signals} momentum trigger${Number(e.signals) > 1 ? "s" : ""} found`;
    case "signal":
      return `${e.symbol} just crossed above its trend at $${e.price} — a candidate`;
    case "veto":
      return `passed on ${e.symbol}: ${friendlyVeto(String(e.reason ?? ""))}`;
    case "order_open":
      return `selling a ${e.symbol} put spread ×${e.qty} for $${e.credit} credit — max loss capped at $${e.max_risk}, ~${Math.round(Number(e.delta ?? 0) * 100)}% chance it's ever tested`;
    case "order_stale":
      return e.retry
        ? `${e.symbol ?? "order"}: even the market's own price didn't fill in ${Math.round(Number(e.age_s) / 60)} min — letting this one go`
        : `${e.symbol ?? "order"}: our price sat unfilled for ${Math.round(Number(e.age_s) / 60)} min — pulling it`;
    case "order_reprice":
      return `retrying ${e.symbol ?? e.short} at the market's price ($${e.natural}) — a filled trade beats a perfect price`;
    case "order_reprice_skipped":
      return `no retry for ${e.symbol ?? e.short}: ${String(e.reason ?? "").includes("already exists") ? "an earlier fill already covered it" : "the market's price no longer pays enough"}`;
    case "exit_signal":
      return `${e.symbol}: ${friendlyExit(String(e.reason ?? ""))}`;
    case "order_close":
      return `buying back ${e.symbol} ×${e.qty} at $${e.limit} — ${friendlyExit(String(e.reason ?? ""))}`;
    case "position_unmanageable":
      return `${e.symbol}: credit $${e.credit} is too small to manage — holding to the time stop instead of paying the spread to exit`;
    case "journal_price_mismatch":
      return `order ${e.client_order_id ?? e.order_id}: parent and leg fill prices disagree by $${e.divergence} — trusting the legs`;
    default:
      return JSON.stringify(e);
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
