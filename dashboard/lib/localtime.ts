import type { Time } from "lightweight-charts";

// lightweight-charts renders UNIX timestamps as UTC on its time scale, so
// bar times must be pre-shifted into the viewer's zone (per-timestamp, so
// DST transitions stay correct).
export const toLocal = (utcSec: number): Time =>
  (utcSec - new Date(utcSec * 1000).getTimezoneOffset() * 60) as Time;

export const toLocalMs = (utcMs: number): number =>
  utcMs - new Date(utcMs).getTimezoneOffset() * 60_000;
