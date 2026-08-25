"""Central configuration: universe, strategy parameters, and risk limits."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StrategyConfig:
    """Options overlay parameters (premium selling, defined risk)."""

    target_short_delta: float = 0.25       # short leg delta for credit spreads
    spread_width_usd: float = 5.0          # distance between short and long strikes
    min_dte: int = 7                       # minimum days to expiration at entry
    max_dte: int = 21                      # maximum days to expiration at entry
    max_new_positions_per_scan: int = 3    # strongest signals first
    order_stale_after_s: int = 180         # cancel unfilled entries after 3 minutes
    profit_target_pct: float = 0.50        # close at 50% of collected credit
    stop_loss_credit_mult: float = 2.0     # stop when loss reaches 2x credit


@dataclass(frozen=True)
class RiskConfig:
    """Hard risk gates enforced before any order leaves the agent."""

    max_risk_per_position_pct: float = 0.02   # of account equity
    max_open_positions: int = 10
    max_buying_power_usage_pct: float = 0.50
    min_open_interest: int = 500              # per leg
    max_bid_ask_width_pct: float = 0.10       # of mid, per leg


@dataclass(frozen=True)
class Config:
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
