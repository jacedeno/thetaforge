import { NextResponse } from "next/server";
import { alpaca } from "@/lib/alpaca";

export const dynamic = "force-dynamic";

interface History { timestamp: number[]; profit_loss: (number | null)[] }
interface Account { equity: string; last_equity: string }

/**
 * Daily P&L bars: past sessions from portfolio history (close-to-close,
 * realized + floating), today computed live from equity vs yesterday's
 * close — the history's daily bucket only settles after the close.
 */
export async function GET() {
  const [history, account] = await Promise.all([
    alpaca("/v2/account/portfolio/history?period=1M&timeframe=1D") as Promise<History>,
    alpaca("/v2/account") as Promise<Account>,
  ]);

  const todayKey = new Date().toISOString().slice(0, 10);
  const days = history.timestamp
    .map((t, i) => ({
      date: new Date(t * 1000).toISOString().slice(0, 10),
      pl: history.profit_loss[i] ?? 0,
      live: false,
    }))
    .filter((d) => d.date < todayKey && d.pl !== 0);

  days.push({
    date: todayKey,
    pl: +(parseFloat(account.equity) - parseFloat(account.last_equity)).toFixed(2),
    live: true,
  });

  return NextResponse.json({ days: days.slice(-10) });
}
