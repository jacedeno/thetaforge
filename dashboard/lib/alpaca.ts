const BASE = "https://paper-api.alpaca.markets";

function headers(): Record<string, string> {
  return {
    "APCA-API-KEY-ID": process.env.ALPACA_API_KEY!,
    "APCA-API-SECRET-KEY": process.env.ALPACA_SECRET_KEY!,
  };
}

export async function alpaca(path: string): Promise<unknown> {
  const r = await fetch(`${BASE}${path}`, { headers: headers(), cache: "no-store" });
  if (!r.ok) throw new Error(`${path} -> ${r.status} ${await r.text()}`);
  return r.json();
}

// ---- OCC option symbol parsing ------------------------------------------

export interface OccContract {
  root: string;
  expiration: string; // YYYY-MM-DD
  kind: "C" | "P";
  strike: number;
}

const OCC = /^([A-Z]+)(\d{2})(\d{2})(\d{2})([CP])(\d{8})$/;

export function parseOcc(symbol: string): OccContract | null {
  const m = OCC.exec(symbol);
  if (!m) return null;
  return {
    root: m[1],
    expiration: `20${m[2]}-${m[3]}-${m[4]}`,
    kind: m[5] as "C" | "P",
    strike: parseInt(m[6], 10) / 1000,
  };
}
