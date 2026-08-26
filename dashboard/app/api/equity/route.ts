import { NextRequest, NextResponse } from "next/server";
import { alpaca } from "@/lib/alpaca";

export const dynamic = "force-dynamic";

/**
 * Equity history for one of the selectable ranges.
 *
 * A freshly opened account returns null equity for every bucket that predates
 * it, so a long range comes back empty rather than wrong. Each range therefore
 * falls back to the next shorter one until a series has real data — a new
 * account shows its first day instead of a blank chart.
 */
const RANGES: Record<string, { period: string; timeframe: string; label: string; tailPoints?: number }> = {
  "1H":  { period: "1D", timeframe: "1Min", label: "last hour", tailPoints: 60 },
  "1D":  { period: "1D", timeframe: "5Min", label: "today" },
  "1W":  { period: "1W", timeframe: "1H",   label: "last week" },
  "1M":  { period: "1M", timeframe: "1D",   label: "last month" },
  "ALL": { period: "all", timeframe: "1D",  label: "all time" },
};

const FALLBACK: Record<string, string> = { ALL: "1M", "1M": "1W", "1W": "1D", "1D": "1H" };

interface History { timestamp: number[]; equity: (number | null)[] }

async function series(rangeKey: string): Promise<[number, number][]> {
  const r = RANGES[rangeKey];
  const h = (await alpaca(
    `/v2/account/portfolio/history?period=${r.period}&timeframe=${r.timeframe}` +
    `&intraday_reporting=market_hours`,
  )) as History;

  let points = h.timestamp
    .map((t, i) => [t * 1000, h.equity[i]] as [number, number | null])
    .filter((p): p is [number, number] => p[1] != null && p[1] > 0);

  if (r.tailPoints) points = points.slice(-r.tailPoints);
  return points;
}

export async function GET(req: NextRequest) {
  const requested = (req.nextUrl.searchParams.get("range") ?? "1D").toUpperCase();
  if (!RANGES[requested])
    return NextResponse.json({ error: "unknown range" }, { status: 400 });

  let key = requested;
  const tried: string[] = [];
  for (let i = 0; i < 5; i++) {
    try {
      const points = await series(key);
      tried.push(key);
      if (points.length > 1 || !FALLBACK[key]) {
        return NextResponse.json({
          range: key,
          requested,
          label: RANGES[key].label,
          fellBack: key !== requested,
          points,
        });
      }
    } catch {
      /* try the shorter range */
    }
    if (!FALLBACK[key]) break;
    key = FALLBACK[key];
  }
  return NextResponse.json({ range: requested, requested, label: RANGES[requested].label, points: [] });
}
