/**
 * Buy-and-hold benchmarks for the equity curve.
 *
 * The question the chart has to answer is not "did the account go up" but
 * "did it beat just buying the index on day one". So for each benchmark
 * symbol the same capital the account started with is spent at the first
 * sample's price, and the position is marked at every later sample. The
 * result is a series aligned one-to-one with the equity points, so it can
 * sit on the same ordinal axis and share every session divider.
 *
 * Prices come from five-minute bars, held in memory for the life of the
 * process and topped up incrementally — the whole history is fetched once,
 * then only what is newer than the last bar. SIP bars run about fifteen
 * minutes behind on this plan, so the last few samples of an open session
 * are priced from IEX until the SIP bars catch up and replace them.
 */

const DATA = "https://data.alpaca.markets/v2/stocks";
const TIMEFRAME = "5Min";
const BAR_MS = 5 * 60_000;
const REFRESH_MS = 60_000;

export interface Bar { t: number; c: number }
interface Cache { bars: Bar[]; from: number; sipUntil: number; refreshed: number }

const cache = new Map<string, Cache>();

function headers(): Record<string, string> {
  return {
    "APCA-API-KEY-ID": process.env.ALPACA_API_KEY!,
    "APCA-API-SECRET-KEY": process.env.ALPACA_SECRET_KEY!,
  };
}

async function fetchBars(symbol: string, fromMs: number, feed: string): Promise<Bar[]> {
  const out: Bar[] = [];
  let page: string | null = null;
  do {
    const url = new URL(`${DATA}/${symbol}/bars`);
    url.searchParams.set("timeframe", TIMEFRAME);
    url.searchParams.set("start", new Date(fromMs).toISOString());
    url.searchParams.set("feed", feed);
    url.searchParams.set("limit", "10000");
    url.searchParams.set("sort", "asc");
    if (page) url.searchParams.set("page_token", page);
    const r = await fetch(url, { headers: headers(), cache: "no-store" });
    if (!r.ok) throw new Error(`${symbol} bars (${feed}) -> ${r.status} ${await r.text()}`);
    const j = (await r.json()) as {
      bars: { t: string; c: number }[] | null;
      next_page_token: string | null;
    };
    for (const b of j.bars ?? []) out.push({ t: Date.parse(b.t), c: b.c });
    page = j.next_page_token;
  } while (page);
  return out;
}

/** Drop every bar at or after `t`, then append `next` — the refetched span replaces the stale one. */
function splice(bars: Bar[], t: number, next: Bar[]): Bar[] {
  let keep = bars.length;
  while (keep > 0 && bars[keep - 1].t >= t) keep--;
  return bars.slice(0, keep).concat(next);
}

/** Five-minute closes for `symbol` from `fromMs` on, served from memory when fresh. */
export async function bars(symbol: string, fromMs: number): Promise<Bar[]> {
  const feed = process.env.ALPACA_DATA_FEED ?? "iex";
  const now = Date.now();
  let c = cache.get(symbol);
  if (c && c.from > fromMs) c = undefined;         // history now starts earlier than what we hold
  if (c && now - c.refreshed < REFRESH_MS) return c.bars;

  // Refetch from the last bar the primary feed gave us: that bar may have
  // been in progress, and everything after it was IEX filler.
  const since = c ? c.sipUntil : fromMs;
  let fresh: Bar[];
  try {
    fresh = await fetchBars(symbol, since, feed);
  } catch (e) {
    if (feed === "iex") throw e;
    fresh = await fetchBars(symbol, since, "iex"); // unentitled key: IEX for everything
  }
  let merged = c ? splice(c.bars, since, fresh) : fresh;
  const sipUntil = merged.length ? merged[merged.length - 1].t : fromMs;

  if (feed !== "iex" && now - sipUntil > 2 * BAR_MS) {
    try {
      const tail = await fetchBars(symbol, sipUntil + BAR_MS, "iex");
      merged = merged.concat(tail.filter((b) => b.t > sipUntil));
    } catch {
      // Delayed but still correct — never fail the whole series over the tail.
    }
  }

  cache.set(symbol, { bars: merged, from: fromMs, sipUntil, refreshed: now });
  return merged;
}

/**
 * The close of the last bar that ENDED at or before `t`, per sample. A bar
 * stamped 14:10 covers 14:10–14:15, so its close is the price at 14:15 —
 * which is what the account was marked at when the 14:15 sample was taken.
 * Samples before the first bar get null; samples past the last bar carry
 * the last close forward, since that is still the latest price known.
 */
export function markToBars(samples: number[], series: Bar[]): (number | null)[] {
  const out: (number | null)[] = [];
  let i = 0;
  let last: number | null = null;
  for (const t of samples) {
    while (i < series.length && series[i].t + BAR_MS <= t) last = series[i++].c;
    out.push(last);
  }
  return out;
}

export interface Benchmark {
  capital: number;
  start: number;
  series: Record<string, (number | null)[]>;
  error?: string;
}

/**
 * Value of `capital` put into each symbol at the first sample, marked at every
 * sample in `samples` (which may be a later slice of the same history).
 */
export async function benchmarks(
  symbols: string[], capital: number, startMs: number, samples: number[],
): Promise<Benchmark> {
  const out: Benchmark = { capital, start: startMs, series: {} };
  const results = await Promise.allSettled(symbols.map(async (sym) => {
    const b = await bars(sym, startMs - 2 * BAR_MS);
    const [entry] = markToBars([startMs], b);
    if (entry == null) throw new Error(`${sym}: no bar at the first sample`);
    const shares = capital / entry;
    return [sym, markToBars(samples, b).map((c) => (c == null ? null : shares * c))] as const;
  }));
  const failed: string[] = [];
  results.forEach((r, i) => {
    if (r.status === "fulfilled") out.series[r.value[0]] = r.value[1];
    else failed.push(`${symbols[i]}: ${(r.reason as Error).message}`);
  });
  if (failed.length) out.error = failed.join("; ");
  return out;
}
