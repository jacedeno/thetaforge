"""Options chain analysis and structure construction.

Maps a directional signal to a defined-risk structure:
- LONG    -> put credit spread
- SHORT   -> call credit spread
- NEUTRAL -> iron condor

Handles strike selection by delta, expiry selection by DTE window,
and chain liquidity screening.
"""
