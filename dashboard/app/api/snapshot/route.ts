import { NextResponse } from "next/server";
import { alpaca, parseOcc } from "@/lib/alpaca";

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
  unrealizedPl: number;
  dte: number;
}

function reconstructSpreads(positions: RawPosition[]): Spread[] {
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
    const entryCredit = parseFloat(sp.avg_entry_price) - parseFloat(lp.avg_entry_price);
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
    const spreads = reconstructSpreads(optionPositions);

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
