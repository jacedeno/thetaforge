import { NextRequest, NextResponse } from "next/server";
import Database from "better-sqlite3";
import path from "path";
import { alpaca } from "@/lib/alpaca";
import { sessionDate } from "@/lib/localtime";

export const dynamic = "force-dynamic";

/**
 * Equity curve, sampled by the agent once per five-minute bar.
 *
 * Two things the broker's own portfolio history could not do:
 *
 *  - Resolution. It serves five-minute buckets for about a week and answers
 *    a 400 for a month at that grain, so every range past a week was drawn
 *    at daily resolution. The loop's samples keep five minutes for the life
 *    of the account.
 *  - Closed-market time. The agent only samples while the market is open, so
 *    nights, weekends and holidays leave no points at all — and the ranges
 *    below are cut in SESSIONS rather than wall-clock days, which is the
 *    same idea applied to the axis.
 *
 * The response is ordered oldest-first and carries session boundaries, so
 * the chart can plot against an ordinal axis and never draw the flat
 * overnight run that a time axis is obliged to draw.
 */

// How many sessions each range covers. `1H` is the exception: it is a
// window inside the current session, measured in samples.
const RANGES: Record<string, { sessions?: number; samples?: number; label: string }> = {
  "1H":  { samples: 12,  label: "last hour" },
  "1D":  { sessions: 1,  label: "this session" },
  "1W":  { sessions: 5,  label: "last 5 sessions" },
  "1M":  { sessions: 21, label: "last 21 sessions" },
  "ALL": { label: "all time" },
};

interface Sample { ts: string; equity: number }
export interface Point { t: number; equity: number }
export interface Session { date: string; start: number; count: number }

function readSamples(): Sample[] {
  const db = new Database(path.join(process.cwd(), "..", "data", "thetaforge.db"), {
    readonly: true, fileMustExist: true,
  });
  try {
    return db.prepare(
      "SELECT ts, equity FROM equity_samples ORDER BY ts ASC",
    ).all() as Sample[];
  } finally {
    db.close();
  }
}

/** Group consecutive points by the New York date they were sampled in. */
function sessions(points: Point[]): Session[] {
  const out: Session[] = [];
  for (const [i, p] of points.entries()) {
    const date = sessionDate(p.t);
    const last = out[out.length - 1];
    if (last && last.date === date) last.count++;
    else out.push({ date, start: i, count: 1 });
  }
  return out;
}

/**
 * The broker's daily buckets, for an account whose curve predates sampling
 * or whose journal is not readable. Coarse by nature — the point is that a
 * chart with a real history beats an empty one.
 */
async function brokerFallback(): Promise<Point[]> {
  interface History { timestamp: number[]; equity: (number | null)[] }
  const h = (await alpaca(
    "/v2/account/portfolio/history?period=1M&timeframe=1D&intraday_reporting=market_hours",
  )) as History;
  return h.timestamp
    .map((t, i) => ({ t: t * 1000, equity: h.equity[i] }))
    .filter((p): p is Point => p.equity != null && p.equity > 0);
}

export async function GET(req: NextRequest) {
  const requested = (req.nextUrl.searchParams.get("range") ?? "1D").toUpperCase();
  const spec = RANGES[requested];
  if (!spec) return NextResponse.json({ error: "unknown range" }, { status: 400 });

  let all: Point[] = [];
  let source = "journal";
  try {
    all = readSamples().map((s) => ({ t: Date.parse(s.ts), equity: s.equity }));
  } catch {
    all = [];
  }

  if (all.length < 2) {
    try {
      all = await brokerFallback();
      source = "broker";
    } catch {
      return NextResponse.json({
        range: requested, requested, label: spec.label,
        points: [], sessions: [], source: "none",
      });
    }
  }

  const bySession = sessions(all);
  let points = all;
  if (spec.samples) {
    // A window inside the newest session, never spilling into the one before.
    const current = bySession[bySession.length - 1];
    points = all.slice(Math.max(current.start, all.length - spec.samples));
  } else if (spec.sessions) {
    const keep = bySession.slice(-spec.sessions);
    points = all.slice(keep[0].start);
  }

  return NextResponse.json({
    range: requested,
    requested,
    label: spec.label,
    points,
    sessions: sessions(points),
    source,
    sampledSessions: bySession.length,
  });
}
