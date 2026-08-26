import { NextRequest, NextResponse } from "next/server";
import { alpaca } from "@/lib/alpaca";

export const dynamic = "force-dynamic";

interface Leg {
  symbol: string; side: string; position_intent: string;
  filled_qty: string; filled_avg_price: string | null; filled_at: string | null;
}
interface Order {
  id: string; filled_at: string | null; filled_avg_price: string | null;
  qty: string; legs: Leg[] | null;
}

/**
 * The individual fills behind one spread — both legs of the opening order and,
 * once closed, both legs of the closing order. The journal stores net credit
 * and debit; this is the per-contract detail behind those numbers.
 */
export async function GET(req: NextRequest) {
  const short = req.nextUrl.searchParams.get("short");
  const long = req.nextUrl.searchParams.get("long");
  if (!short || !long)
    return NextResponse.json({ error: "short and long symbols required" }, { status: 400 });

  const orders = (await alpaca(
    "/v2/orders?status=closed&asset_class=us_option&limit=500&nested=true",
  )) as Order[];

  const rows = orders
    .filter((o) => o.filled_at && (o.legs ?? []).some((l) => l.symbol === short))
    .filter((o) => (o.legs ?? []).some((l) => l.symbol === long))
    .flatMap((o) =>
      (o.legs ?? []).map((l) => ({
        at: l.filled_at ?? o.filled_at,
        symbol: l.symbol,
        side: l.side.toUpperCase(),
        intent: l.position_intent,
        qty: l.filled_qty,
        price: l.filled_avg_price,
        opening: l.position_intent?.includes("to_open") ?? false,
      })),
    )
    .sort((a, b) => (a.at ?? "").localeCompare(b.at ?? ""));

  return NextResponse.json({ transactions: rows });
}
