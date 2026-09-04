"""Risk gates — every candidate order passes all gates or is vetoed."""

from __future__ import annotations

from dataclasses import dataclass

from agent.config import RiskConfig
from agent.execution.monitor import occ_root
from agent.options.selector import SpreadCandidate


@dataclass(frozen=True)
class GateResult:
    passed: bool
    reason: str = ""


def max_positions(equity: float, risk: RiskConfig) -> int:
    """How many concurrent positions the ladder allows at this equity."""
    return min(risk.slot_cap_positions, int(equity // risk.slot_growth_usd))


def position_slot(equity: float, risk: RiskConfig) -> float:
    """Dollar budget for one position at this equity (see RiskConfig ladder)."""
    if max_positions(equity, risk) >= risk.slot_cap_positions:
        return equity * risk.slot_mature_pct
    return risk.slot_growth_usd


def position_qty(spread: SpreadCandidate, equity: float, risk: RiskConfig) -> int:
    """Contracts such that max loss fills, but stays within, one slot."""
    budget = position_slot(equity, risk)
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
    # held_underlyings carries OCC roots (from position symbols); the
    # candidate carries the ticker — normalize or dotted classes slip through.
    if occ_root(spread.underlying) in held_underlyings:
        return GateResult(False, f"already holding a position on {spread.underlying}")
    if open_positions_count >= max_positions(equity, risk):
        return GateResult(False, "max open positions reached")
    total_risk = spread.max_risk_per_spread * qty
    if total_risk > options_buying_power:
        return GateResult(False, "insufficient options buying power")
    if total_risk > equity * risk.max_buying_power_usage_pct:
        return GateResult(False, "exceeds buying power usage cap")
    return GateResult(True)
