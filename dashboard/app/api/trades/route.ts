import { NextResponse } from "next/server";
import Database from "better-sqlite3";
import path from "path";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const db = new Database(path.join(process.cwd(), "..", "data", "thetaforge.db"), {
      readonly: true, fileMustExist: true,
    });
    interface TradeRow {
      status: string; realized_pl: number | null;
      entry_credit: number; exit_debit: number | null; qty: number;
      source?: string;
      [k: string]: unknown;
    }
    const trades = db.prepare(
      "SELECT * FROM trades ORDER BY open_ts DESC LIMIT 200",
    ).all() as TradeRow[];
    db.close();

    // Manual/out-of-band orders stay visible in the list (badged) but never
    // count toward the agent's performance stats.
    const agentTrades = trades.filter((t) => t.source !== "manual");
    const closed = agentTrades.filter((t) => t.status === "closed");
    const wins = closed.filter((t) => (t.realized_pl ?? 0) > 0);
    const grossWin = wins.reduce((a, t) => a + (t.realized_pl ?? 0), 0);
    const grossLoss = closed
      .filter((t) => (t.realized_pl ?? 0) <= 0)
      .reduce((a, t) => a + Math.abs(t.realized_pl ?? 0), 0);

    return NextResponse.json({
      trades,
      stats: {
        closed: closed.length,
        open: agentTrades.length - closed.length,
        totalPl: closed.reduce((a, t) => a + (t.realized_pl ?? 0), 0),
        winRate: closed.length ? wins.length / closed.length : null,
        profitFactor: grossLoss > 0 ? grossWin / grossLoss : null,
        avgWin: wins.length ? grossWin / wins.length : null,
        avgLoss: closed.length - wins.length ? grossLoss / (closed.length - wins.length) : null,
        creditCaptured: closed.reduce(
          (a, t) => a + (t.entry_credit - (t.exit_debit ?? 0)) * 100 * t.qty, 0),
      },
    });
  } catch {
    return NextResponse.json({ trades: [], stats: null, note: "journal not initialized yet" });
  }
}
