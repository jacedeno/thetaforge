"""Risk gates — every candidate order passes all gates or is vetoed."""

from __future__ import annotations

from dataclasses import dataclass

from agent.config import RiskConfig
from agent.options.selector import SpreadCandidate


@dataclass(frozen=True)
class GateResult:
    passed: bool
    reason: str = ""


def position_qty(spread: SpreadCandidate, equity: float, risk: RiskConfig) -> int:
    """Contracts such that max loss stays within the per-position risk cap."""
    budget = equity * risk.max_risk_per_position_pct
    if spread.max_risk_per_spread <= 0:
        return 0
    return int(budget // spread.max_risk_per_spread)


def check_all(
    spread: SpreadCandidate,
    qty: int,
    equity: float,
    options_buying_power: float,
    open_positions_count: int,
    held_underlyings: set[str],
    risk: RiskConfig,
) -> GateResult:
    if qty < 1:
        return GateResult(False, "position risk budget below one spread")
    if spread.underlying in held_underlyings:
        return GateResult(False, f"already holding a position on {spread.underlying}")
    if open_positions_count >= risk.max_open_positions:
        return GateResult(False, "max open positions reached")
    total_risk = spread.max_risk_per_spread * qty
    if total_risk > options_buying_power:
        return GateResult(False, "insufficient options buying power")
    if total_risk > equity * risk.max_buying_power_usage_pct:
        return GateResult(False, "exceeds buying power usage cap")
    return GateResult(True)
