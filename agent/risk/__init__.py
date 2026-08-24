"""Risk gates.

Every candidate order passes through all gates before execution:
position sizing, buying-power caps, open-position limits, and
per-leg liquidity checks. A single failed gate vetoes the trade.
"""
