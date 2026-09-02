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
    # 0 for the last judged session (2026-09-03), Jose's call: entries are OFF.
    #
    # The judged number is equity at EOD Thursday and the book is already at
    # its 15-position cap. The only way a new entry appears tomorrow is by
    # refilling a slot the moment a profit target frees it — exactly how
    # today's NVDA close became a TSLA open minutes later. A position opened
    # hours before the score is read has no time to collect its theta; it can
    # only add fresh delta risk to a number we want frozen. Exits stay fully
    # live: targets can only realize gains, and the monitor never opens.
    # RESTORE TO 3 after the window closes, together with the stop loss below.
    max_new_positions_per_scan: int = 0    # calmest valid signals first
    # Skip overextended breakouts — they mean-revert. Raised 0.012 -> 0.02 on
    # 2026-08-27 for the 5m burn-in: on 5-minute bars the median trigger
    # strength is ~0.003 and the ceiling mostly vetoes opening-gap crosses,
    # so one notch looser still blocks the violent gaps. UNDER REVIEW — decide
    # with the live signal data (events now log sma55/sma21/bar_time).
    max_signal_strength: float = 0.02
    max_new_per_sector_per_scan: int = 1   # one fresh bet per sector per scan
    # Free-tier SIP history trails ~15 min, and with the RTH filter the first
    # scans of a session (8:30-8:50 CT) see YESTERDAY'S closing bar as
    # "latest" — six of its signals fired live on 2026-08-28 and only the
    # option-liquidity gates stopped them. A signal bar that closed more than
    # this many seconds ago is treated exactly like an unreachable feed: no
    # order. 30 min covers the normal delay with margin and blocks any
    # overnight replay.
    max_signal_bar_age_s: int = 1800
    order_stale_after_s: int = 180         # cancel unfilled entries after 3 minutes
    # A stale entry older than this is cancelled WITHOUT a reprice — its
    # signal died with it. (2026-08-26: a downed monitor swept 2-hour-old
    # orders into blind reprices; the worst entries of the day.)
    reprice_max_age_s: int = 600
    # An unfilled exit older than this is cancelled so the next pass can
    # re-decide at the fresh cost — a position must never sit unmanaged
    # behind a resting close (2026-08-27: COP's stop rested three hours).
    exit_stale_after_s: int = 120
    entry_concession_pct: float = 0.03     # shade the entry limit below mid to actually fill
    entry_concession_min: float = 0.01
    profit_target_pct: float = 0.50        # close at 50% of collected credit
    stop_loss_credit_mult: float = 2.0     # stop when loss reaches 2x credit
    # OFF for the judged window (2026-09-01 .. 09-03), Jose's call.
    #
    # The stop protects capital over months, by cutting a loser before it
    # reaches max loss. Over a three-day horizon it buys almost nothing and
    # costs something real: risk here is already defined and collateralized
    # (max loss = width - credit, -19,742 across the whole book), nothing
    # expires before 2026-09-18, and a loser that is 2x credit down sits in
    # the widest-quoted part of the chain, so stopping out pays the bid-ask
    # at the worst moment AND destroys the recovery the remaining 17 days
    # might deliver. The score reads total equity, which already carries the
    # open loss either way: closing CAT at natural moves equity by +12 on a
    # -375 position.
    #
    # Profit targets and the time stop stay ON. Winners close, losers ride.
    # RESTORE TO True after the window closes — over a full quarter an
    # unstopped loser is exactly how a premium-selling book dies.
    stop_loss_enabled: bool = False
    # Credit-relative thresholds collapse on tiny credits: at 0.03 the whole
    # decision band is eight cents wide and quote flicker exits the trade.
    # Both exit rules must sit at least this far from the entry credit.
    min_exit_band_usd: float = 0.10
    min_exit_limit_usd: float = 0.02       # floor for the pad on the closing limit
    # An unfilled close is re-placed one step closer to the natural price each
    # time, reaching it on the third retry — with exit_stale_after_s at 120
    # that is six minutes from "stop fired" to "pay what the book asks".
    # Anchoring every retry at the midpoint means a wide-quoted spread never
    # exits at all (CAT, 2026-09-01).
    exit_escalation_steps: int = 3


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
