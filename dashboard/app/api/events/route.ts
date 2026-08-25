import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const file = path.join(process.cwd(), "..", "logs", "events.jsonl");
    const raw = await fs.readFile(file, "utf8").catch(() => "");
    const events = raw
      .trim()
      .split("\n")
      .filter(Boolean)
      .slice(-120)
      .map((l) => JSON.parse(l))
      .reverse();
    return NextResponse.json({ events });
  } catch (e) {
    return NextResponse.json({ events: [], error: String(e) });
  }
}
