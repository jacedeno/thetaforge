import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic";

export async function GET() {
  const root = path.join(process.cwd(), "..");
  let heartbeat: Record<string, unknown> | null = null;
  try {
    heartbeat = JSON.parse(await fs.readFile(path.join(root, "data", "heartbeat.json"), "utf8"));
  } catch { /* agent not started yet */ }

  let eventsToday = 0;
  try {
    const raw = await fs.readFile(path.join(root, "logs", "events.jsonl"), "utf8");
    const today = new Date().toISOString().slice(0, 10);
    eventsToday = raw.split("\n").filter((l) => l.includes(`"ts": "${today}`) || l.startsWith(`{"ts": "${today}`)).length;
  } catch { /* no events yet */ }

  const ts = heartbeat?.ts ? new Date(heartbeat.ts as string).getTime() : 0;
  const ageS = (Date.now() - ts) / 1000;
  const failures = Number(heartbeat?.consecutive_failures ?? 0);
  return NextResponse.json({
    agent: {
      alive: ageS < 360,           // loop beats at least every ~5min when closed, 1min when open
      degraded: failures >= 3,     // beating, but its passes keep crashing
      consecutiveFailures: failures,
      lastBeat: heartbeat?.ts ?? null,
      lastScan: heartbeat?.last_scan ?? null,
      started: heartbeat?.started ?? null,
      iteration: heartbeat?.iteration ?? null,
      marketOpen: heartbeat?.market_open ?? null,
    },
    eventsToday,
  });
}
