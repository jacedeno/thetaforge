import { NextResponse } from "next/server";
import Database from "better-sqlite3";
import path from "path";
import { alpaca, parseOcc } from "@/lib/alpaca";

/** Fill-derived entry credits for open trades, keyed "short|long".
 *  The journal is the single source of truth for entry_credit — the
 *  avg_entry_price derivation below is only the fallback (it averages
 *  across multiple fills on the same legs, which the 2026-08-26 doubled
 *  HD position showed drifting 4c from the surviving trade's real fill). */
function journalCredits(): Map<string, number> {
  try {
    const db = new Database(path.join(process.cwd(), "..", "data", "thetaforge.db"), {
      readonly: true, fileMustExist: true,
    });
    const rows = db.prepare(
      "SELECT short_symbol, long_symbol, entry_credit FROM trades WHERE status = 'open'",
    ).all() as { short_symbol: string; long_symbol: string; entry_credit: number }[];
    db.close();
    return new Map(rows.map((r) => [`${r.short_symbol}|${r.long_symbol}`, r.entry_credit]));
  } catch {
    return new Map();
  }
}

async function latestOptionQuotes(symbols: string[]): Promise<Record<string, number>> {
  if (symbols.length === 0) return {};
  const r = await fetch(
    `https://data.alpaca.markets/v1beta1/options/quotes/latest?symbols=${symbols.join(",")}`,
    {
      headers: {
        "APCA-API-KEY-ID": process.env.ALPACA_API_KEY!,
        "APCA-API-SECRET-KEY": process.env.ALPACA_SECRET_KEY!,
      },
      cache: "no-store",
    },
  );
  if (!r.ok) return {};
  const j = (await r.json()) as { quotes: Record<string, { bp: number; ap: number }> };
  return Object.fromEntries(
    Object.entries(j.quotes ?? {})
      .filter(([, q]) => q.bp > 0 && q.ap > 0)
      .map(([k, q]) => [k, (q.bp + q.ap) / 2]),
  );
}

async function latestSpots(symbols: string[]): Promise<Record<string, number>> {
  if (symbols.length === 0) return {};
  const r = await fetch(
    `https://data.alpaca.markets/v2/stocks/trades/latest?feed=iex&symbols=${symbols.join(",")}`,
    {
      headers: {
        "APCA-API-KEY-ID": process.env.ALPACA_API_KEY!,
        "APCA-API-SECRET-KEY": process.env.ALPACA_SECRET_KEY!,
      },
      cache: "no-store",
    },
  );
  if (!r.ok) return {};
  const j = (await r.json()) as { trades: Record<string, { p: number }> };
  return Object.fromEntries(Object.entries(j.trades ?? {}).map(([k, v]) => [k, v.p]));
}

export const dynamic = "force-dynamic";

interface RawPosition {
  symbol: string;
  qty: string;
  avg_entry_price: string;
  current_price: string;
  unrealized_pl: string;
  asset_class: string;
}

interface Spread {
  underlying: string;
  shortSymbol: string;
  longSymbol: string;
  shortStrike: number;
  longStrike: number;
  expiration: string;
  qty: number;
  entryCredit: number;
  currentCost: number;
  unrealizedPl: number;      // broker mark — can lag the live quote in thin chains
  midCost: number | null;    // cost to close at the mid — where you'd actually trade
  midPl: number | null;
  dte: number;
}

function reconstructSpreads(positions: RawPosition[], credits: Map<string, number>): Spread[] {
  const shorts = new Map<string, RawPosition>();
  const longs = new Map<string, RawPosition>();
  for (const p of positions) {
    const c = parseOcc(p.symbol);
    if (!c) continue;
    const key = `${c.root}|${c.expiration}|${c.kind}`;
    (parseFloat(p.qty) < 0 ? shorts : longs).set(key, p);
  }
  const spreads: Spread[] = [];
  const today = new Date();
  for (const [key, sp] of shorts) {
    const lp = longs.get(key);
    if (!lp) continue;
    const sc = parseOcc(sp.symbol)!;
    const lc = parseOcc(lp.symbol)!;
    const qty = Math.abs(parseFloat(sp.qty));
    const entryCredit =
      credits.get(`${sp.symbol}|${lp.symbol}`) ??
      parseFloat(sp.avg_entry_price) - parseFloat(lp.avg_entry_price);
    const currentCost = parseFloat(sp.current_price) - parseFloat(lp.current_price);
    const dte = Math.round(
      (new Date(sc.expiration + "T21:00:00Z").getTime() - today.getTime()) / 86_400_000,
    );
    spreads.push({
      underlying: sc.root,
      shortSymbol: sp.symbol,
      longSymbol: lp.symbol,
      shortStrike: sc.strike,
      longStrike: lc.strike,
      expiration: sc.expiration,
      qty,
      entryCredit: +entryCredit.toFixed(2),
      currentCost: +currentCost.toFixed(2),
      unrealizedPl: +(parseFloat(sp.unrealized_pl) + parseFloat(lp.unrealized_pl)).toFixed(2),
      midCost: null,
      midPl: null,
      dte,
    });
  }
  return spreads.sort((a, b) => a.dte - b.dte);
}

export async function GET() {
  try {
    const [account, clock, positionsRaw, history, ordersRaw] = await Promise.all([
      alpaca("/v2/account") as Promise<Record<string, string>>,
      alpaca("/v2/clock") as Promise<{ is_open: boolean; next_open: string; next_close: string }>,
      alpaca("/v2/positions") as Promise<RawPosition[]>,
      alpaca(
        "/v2/account/portfolio/history?period=1W&timeframe=1H&intraday_reporting=market_hours",
      ) as Promise<{ timestamp: number[]; equity: number[] }>,
      alpaca(
        "/v2/orders?status=all&limit=100&nested=true&asset_class=us_option",
      ) as Promise<Record<string, unknown>[]>,
    ]);

    const optionPositions = positionsRaw.filter((p) => p.asset_class === "us_option");
    const spreads = reconstructSpreads(optionPositions, journalCredits());
    const spots = await latestSpots([...new Set(spreads.map((s) => s.underlying))]);
    const optQuotes = await latestOptionQuotes(
      spreads.flatMap((s) => [s.shortSymbol, s.longSymbol]),
    );
    for (const s of spreads) {
      const sm = optQuotes[s.shortSymbol];
      const lm = optQuotes[s.longSymbol];
      if (sm != null && lm != null) {
        s.midCost = +(sm - lm).toFixed(2);
        s.midPl = +((s.entryCredit - s.midCost) * 100 * s.qty).toFixed(2);
      }
    }

    const equitySeries = history.timestamp
      .map((t, i) => [t * 1000, history.equity[i]] as [number, number])
      .filter(([, e]) => e != null && e > 0);

    return NextResponse.json({
      asOf: new Date().toISOString(),
      market: { isOpen: clock.is_open, nextOpen: clock.next_open, nextClose: clock.next_close },
      account: {
        number: account.account_number,
        equity: parseFloat(account.equity),
        lastEquity: parseFloat(account.last_equity),
        optionsBuyingPower: parseFloat(account.options_buying_power),
        cash: parseFloat(account.cash),
      },
      spreads,
      spots,
      equitySeries,
      orders: ordersRaw.slice(0, 30).map((o) => ({
        id: o.id,
        submittedAt: o.submitted_at,
        status: o.status,
        qty: o.qty,
        limitPrice: o.limit_price,
        filledAvgPrice: o.filled_avg_price,
        legs: ((o.legs as Record<string, unknown>[]) ?? []).map((l) => ({
          symbol: l.symbol,
          side: l.side,
          intent: l.position_intent,
        })),
      })),
    });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
