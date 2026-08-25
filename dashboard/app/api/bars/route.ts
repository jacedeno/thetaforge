import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const symbol = sp.get("symbol");
  const from = sp.get("from");
  const to = sp.get("to");
  if (!symbol || !/^[A-Z.]{1,10}$/.test(symbol) || !from || !to)
    return NextResponse.json({ error: "symbol, from, to required" }, { status: 400 });

  const url = new URL(`https://data.alpaca.markets/v2/stocks/${symbol}/bars`);
  url.searchParams.set("timeframe", "15Min");
  url.searchParams.set("start", from);
  url.searchParams.set("end", to);
  url.searchParams.set("feed", "iex");
  url.searchParams.set("limit", "10000");

  const r = await fetch(url, {
    headers: {
      "APCA-API-KEY-ID": process.env.ALPACA_API_KEY!,
      "APCA-API-SECRET-KEY": process.env.ALPACA_SECRET_KEY!,
    },
    cache: "no-store",
  });
  if (!r.ok) return NextResponse.json({ error: await r.text() }, { status: r.status });
  const j = (await r.json()) as { bars: { t: string; o: number; h: number; l: number; c: number }[] };
  return NextResponse.json({
    bars: (j.bars ?? []).map((b) => ({
      time: Math.floor(new Date(b.t).getTime() / 1000),
      open: b.o, high: b.h, low: b.l, close: b.c,
    })),
  });
}
