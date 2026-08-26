"use client";

/**
 * Payoff diagram for a put credit spread — the brand motif rendered per
 * position, with the live underlying price marked on the curve.
 *
 * Default is the 180x64 mini used on the position cards; `detailed` scales
 * it up responsively and labels strikes, breakeven and the exit levels.
 */
export default function PayoffDiagram({
  shortStrike, longStrike, credit, spot, w, h, detailed = false,
}: {
  shortStrike: number; longStrike: number; credit: number; spot?: number;
  w?: number; h?: number; detailed?: boolean;
}) {
  const W = w ?? 180, H = h ?? 64;
  const width = shortStrike - longStrike;
  // x-domain: pad one width each side of the strikes
  const x0 = longStrike - width, x1 = shortStrike + width;
  const X = (p: number) => ((p - x0) / (x1 - x0)) * W;
  const maxProfit = credit, maxLoss = width - credit;
  // y: profit up; scale to fit
  const yTop = detailed ? 18 : 12, yBot = detailed ? H - 22 : H - 12;
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

  const breakeven = shortStrike - credit;
  // Exit rules mirrored from agent/config.py: profit_target_pct 0.50,
  // stop_loss_credit_mult 2.0, both floored by min_exit_band_usd 0.10.
  const targetPl = Math.max(0.5 * credit, 0.10);
  const stopPl = -Math.max(2 * credit, 0.10);

  return (
    <svg
      {...(detailed ? { className: "h-auto w-full" } : { width: W, height: H })}
      viewBox={`0 0 ${W} ${H}`} aria-label="payoff diagram"
    >
      <line x1="0" y1={Y(0)} x2={W} y2={Y(0)} stroke="var(--grid)" strokeWidth="1" />
      {detailed && targetPl <= maxProfit && (
        <>
          <line x1="0" y1={Y(targetPl)} x2={W} y2={Y(targetPl)}
            stroke="var(--good)" strokeWidth="1" strokeDasharray="4 3" opacity="0.7" />
          <text x={4} y={Y(targetPl) - 3} fontSize="9" fill="var(--good)">
            take profit +{targetPl.toFixed(2)}
          </text>
        </>
      )}
      {detailed && stopPl >= -maxLoss && (
        <>
          <line x1="0" y1={Y(stopPl)} x2={W} y2={Y(stopPl)}
            stroke="var(--critical)" strokeWidth="1" strokeDasharray="4 3" opacity="0.7" />
          <text x={4} y={Y(stopPl) - 3} fontSize="9" fill="var(--critical)">
            stop {stopPl.toFixed(2)}
          </text>
        </>
      )}
      <polyline points={pts} fill="none" stroke="var(--series-2)" strokeWidth="2"
        strokeLinejoin="round" strokeLinecap="round" />
      {detailed && (
        <>
          <line x1={X(breakeven)} y1={yTop - 4} x2={X(breakeven)} y2={yBot + 4}
            stroke="var(--series-1)" strokeWidth="1" strokeDasharray="2 3" />
          <text x={X(breakeven)} y={yTop - 7} fontSize="9" textAnchor="middle"
            fill="var(--series-1)">BE {breakeven.toFixed(2)}</text>
          <text x={X(shortStrike)} y={yBot + 14} fontSize="9" textAnchor="middle"
            fill="var(--ink-muted)">{shortStrike}</text>
          <text x={X(longStrike)} y={yBot + 14} fontSize="9" textAnchor="middle"
            fill="var(--ink-muted)">{longStrike}</text>
          <text x={W - 4} y={Y(maxProfit) - 4} fontSize="9" textAnchor="end"
            fill="var(--ink-muted)">max +{maxProfit.toFixed(2)}</text>
          <text x={4} y={Y(-maxLoss) + 11} fontSize="9"
            fill="var(--ink-muted)">max −{maxLoss.toFixed(2)}</text>
        </>
      )}
      {spotX !== undefined && (
        <>
          <line x1={spotX} y1={yTop - 4} x2={spotX} y2={yBot + 4}
            stroke="var(--ink-muted)" strokeWidth="1" strokeDasharray="3 3" />
          <circle cx={spotX} cy={Y(spotPl)} r="4.5" fill="var(--series-1)"
            stroke="var(--surface-1)" strokeWidth="2" />
          {detailed && spot !== undefined && (
            <text x={spotX} y={yBot + 14} fontSize="9" textAnchor="middle"
              fill="var(--series-1)">spot {spot.toFixed(2)}</text>
          )}
        </>
      )}
    </svg>
  );
}
