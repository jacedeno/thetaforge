import { NextResponse } from "next/server";
import { alpaca } from "@/lib/alpaca";

export const dynamic = "force-dynamic";

interface History { timestamp: number[]; profit_loss: (number | null)[] }
interface Account { equity: string; last_equity: string }

// Which session a moment belongs to, as a YYYY-MM-DD key in New York.
// Alpaca stamps each daily bucket at midnight UTC of the day AFTER the
// session it summarises: Monday 2026-08-31 arrives as 2026-09-01T00:00:00Z,
// which is 20:00 ET on the 31st. Reading that stamp in UTC dates every bar
// one day forward, and the most recent session — always the interesting one —
// collides with today's key and gets filtered out entirely.
const NY_DATE = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" });
const sessionKey = (d: Date) => NY_DATE.format(d);

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

  const todayKey = sessionKey(new Date());
  const days = history.timestamp
    .map((t, i) => ({
      date: sessionKey(new Date(t * 1000)),
      pl: history.profit_loss[i] ?? 0,
      live: false,
    }))
    .filter((d) => d.date < todayKey);
  // Trim pre-funding zero padding only — a real flat session mid-stream stays.
  while (days.length && days[0].pl === 0) days.shift();

  days.push({
    date: todayKey,
    pl: +(parseFloat(account.equity) - parseFloat(account.last_equity)).toFixed(2),
    live: true,
  });

  return NextResponse.json({ days: days.slice(-10) });
}
