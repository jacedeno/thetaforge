import { promises as fs } from "fs";
import path from "path";

// Server-side only (reads the agent's event log from disk).

interface Ev { ts: string; type: string; [k: string]: unknown }

export interface SignalMark { ts: string; barTime: string | null; price: number | null }

/** logs/events.jsonl — append-only, chronological. */
export async function loadEvents(): Promise<Ev[]> {
  const file = path.join(process.cwd(), "..", "logs", "events.jsonl");
  const raw = await fs.readFile(file, "utf8").catch(() => "");
  return raw.split("\n").filter(Boolean).flatMap((l) => {
    try { return [JSON.parse(l) as Ev]; } catch { return []; }
  });
}

/** The signal that produced a trade. Anchor on the order_open for these legs
 *  (a stale order can fill via reprice long after later re-signals of the
 *  same symbol), then take the latest signal at or before that anchor. */
export function findSignal(
  events: Ev[], underlying: string, shortSymbol: string, openTs: string,
): SignalMark | null {
  const openMs = Date.parse(openTs);
  let anchor = openMs;
  for (const e of events) {
    if (e.type === "order_open" && e.short === shortSymbol) {
      const t = Date.parse(e.ts);
      if (t <= openMs) anchor = t;
    }
  }
  let sig: Ev | null = null;
  for (const e of events) {
    if (e.type === "signal" && e.symbol === underlying && Date.parse(e.ts) <= anchor)
      sig = e;
  }
  if (!sig) return null;
  return {
    ts: sig.ts,
    barTime: (sig.bar_time as string | undefined) ?? null,
    price: (sig.price as number | undefined) ?? null,
  };
}
