"use client";

/**
 * Mini payoff diagram for a put credit spread — the brand motif rendered
 * per position, with the live underlying price marked on the curve.
 */
export default function PayoffDiagram({
  shortStrike, longStrike, credit, spot,
}: { shortStrike: number; longStrike: number; credit: number; spot?: number }) {
  const W = 180, H = 64;
  const width = shortStrike - longStrike;
  // x-domain: pad one width each side of the strikes
  const x0 = longStrike - width, x1 = shortStrike + width;
  const X = (p: number) => ((p - x0) / (x1 - x0)) * W;
  const maxProfit = credit, maxLoss = width - credit;
  // y: profit up; scale to fit
  const yTop = 12, yBot = H - 12;
  const Y = (pl: number) => yTop + ((maxProfit - pl) / (maxProfit + maxLoss)) * (yBot - yTop);

  const pts = [
    `${X(x0)},${Y(-maxLoss)}`,
    `${X(longStrike)},${Y(-maxLoss)}`,
    `${X(shortStrike)},${Y(maxProfit)}`,
    `${X(x1)},${Y(maxProfit)}`,
  ].join(" ");

  const spotX = spot !== undefined ? Math.max(2, Math.min(W - 2, X(spot))) : undefined;
  const spotPl = spot === undefined ? 0
    : spot >= shortStrike ? maxProfit
    : spot <= longStrike ? -maxLoss
    : maxProfit - ((shortStrike - spot) / width) * (maxProfit + maxLoss);

  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-label="payoff diagram">
      <line x1="0" y1={Y(0)} x2={W} y2={Y(0)} stroke="var(--grid)" strokeWidth="1" />
      <polyline points={pts} fill="none" stroke="var(--series-2)" strokeWidth="2"
        strokeLinejoin="round" strokeLinecap="round" />
      {spotX !== undefined && (
        <>
          <line x1={spotX} y1={yTop - 4} x2={spotX} y2={yBot + 4}
            stroke="var(--ink-muted)" strokeWidth="1" strokeDasharray="3 3" />
          <circle cx={spotX} cy={Y(spotPl)} r="4.5" fill="var(--series-1)"
            stroke="var(--surface-1)" strokeWidth="2" />
        </>
      )}
    </svg>
  );
}
