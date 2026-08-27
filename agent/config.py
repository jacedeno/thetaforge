"""Central configuration: universe, strategy parameters, and risk limits."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StrategyConfig:
    """Options overlay parameters (premium selling, defined risk)."""

    target_short_delta: float = 0.25       # short leg delta for credit spreads
    min_short_delta: float = 0.15          # below this the premium is not worth the risk
    max_short_delta: float = 0.32          # above this the short strike sits too close to spot
    min_credit_to_width: float = 0.12      # credit must be a real fraction of what is risked
    min_credit_usd: float = 0.15           # and enough to survive slippage
    spread_width_pct: float = 0.012        # target width as a fraction of spot price
    spread_width_min_usd: float = 1.0      # floor for cheap underlyings
    spread_width_max_usd: float = 10.0     # cap for expensive ones
    min_dte: int = 7                       # minimum days to expiration at entry
    max_dte: int = 21                      # maximum days to expiration at entry
    max_new_positions_per_scan: int = 3    # calmest valid signals first
    # Skip overextended breakouts — they mean-revert. Raised 0.012 -> 0.02 on
    # 2026-08-27 for the 5m burn-in: on 5-minute bars the median trigger
    # strength is ~0.003 and the ceiling mostly vetoes opening-gap crosses,
    # so one notch looser still blocks the violent gaps. UNDER REVIEW — decide
    # with the live signal data (events now log sma55/sma21/bar_time).
    max_signal_strength: float = 0.02
    max_new_per_sector_per_scan: int = 1   # one fresh bet per sector per scan
    order_stale_after_s: int = 180         # cancel unfilled entries after 3 minutes
    entry_concession_pct: float = 0.03     # shade the entry limit below mid to actually fill
    entry_concession_min: float = 0.01
    profit_target_pct: float = 0.50        # close at 50% of collected credit
    stop_loss_credit_mult: float = 2.0     # stop when loss reaches 2x credit
    # Credit-relative thresholds collapse on tiny credits: at 0.03 the whole
    # decision band is eight cents wide and quote flicker exits the trade.
    # Both exit rules must sit at least this far from the entry credit.
    min_exit_band_usd: float = 0.10
    min_exit_limit_usd: float = 0.02       # floor for the pad on the closing limit


@dataclass(frozen=True)
class RiskConfig:
    """Hard risk gates enforced before any order leaves the agent."""

    # 1.5% x 15 = 22.5% aggregate worst case — upper half of the canonical
    # 15-25% band, traded for more, smaller positions (Jose, 2026-08-27:
    # burn-in experiment; more concurrent positions has historically helped
    # results; veto counts measured via scripts/veto_summary.py).
    # UNDER REVIEW with the burn-in data.
    max_risk_per_position_pct: float = 0.015  # of account equity
    max_open_positions: int = 15
    max_buying_power_usage_pct: float = 0.50
    min_open_interest: int = 500              # per leg
    # A leg is tradable if its quote is tight in RELATIVE or ABSOLUTE terms.
    # Percent alone rejects cheap contracts where a few cents is a wide ratio;
    # cents alone rejects expensive ones where a normal ratio is many cents.
    max_bid_ask_width_pct: float = 0.25       # of mid, per leg
    max_bid_ask_width_usd: float = 0.10       # per leg, absolute alternative
    # The absolute branch exists for cheap-but-real contracts; below this mid
    # it would be rescuing penny dust whose "mid" is itself noise. Applied to
    # the short leg only — the protective wing may be legitimately cheap.
    min_mid_for_abs_width: float = 0.20


@dataclass(frozen=True)
class Config:
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
