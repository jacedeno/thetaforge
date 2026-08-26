import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

// Exactly the timeframes the UI offers — anything else is rejected, never
// forwarded to Alpaca.
const TIMEFRAMES = new Set(["5Min", "15Min", "30Min", "1Hour", "1Day"]);

async function fetchBars(symbol: string, from: string, to: string, tf: string, feed: string) {
  const url = new URL(`https://data.alpaca.markets/v2/stocks/${symbol}/bars`);
  url.searchParams.set("timeframe", tf);
  url.searchParams.set("start", from);
  url.searchParams.set("end", to);
  url.searchParams.set("feed", feed);
  url.searchParams.set("limit", "10000");
  url.searchParams.set("sort", "asc");
  return fetch(url, {
    headers: {
      "APCA-API-KEY-ID": process.env.ALPACA_API_KEY!,
      "APCA-API-SECRET-KEY": process.env.ALPACA_SECRET_KEY!,
    },
    cache: "no-store",
  });
}

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const symbol = sp.get("symbol");
  const from = sp.get("from");
  const to = sp.get("to");
  const tf = sp.get("tf") ?? "15Min";
  if (!symbol || !/^[A-Z.]{1,10}$/.test(symbol) || !from || !to)
    return NextResponse.json({ error: "symbol, from, to required" }, { status: 400 });
  if (!TIMEFRAMES.has(tf))
    return NextResponse.json({ error: `tf must be one of ${[...TIMEFRAMES].join(", ")}` }, { status: 400 });

  // SIP matches what the agent saw, but an unentitled key gets 403 — fall
  // back to iex rather than render a silently blank chart.
  const feed = process.env.ALPACA_DATA_FEED ?? "iex";
  let r = await fetchBars(symbol, from, to, tf, feed);
  if (r.status === 403 && feed !== "iex") r = await fetchBars(symbol, from, to, tf, "iex");
  if (!r.ok) return NextResponse.json({ error: await r.text() }, { status: r.status });
  const j = (await r.json()) as {
    bars: { t: string; o: number; h: number; l: number; c: number }[];
    next_page_token?: string | null;
  };
  return NextResponse.json({
    bars: (j.bars ?? []).map((b) => ({
      time: Math.floor(new Date(b.t).getTime() / 1000),
      open: b.o, high: b.h, low: b.l, close: b.c,
    })),
    truncated: Boolean(j.next_page_token),
  });
}
