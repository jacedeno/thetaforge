"""Order execution through Alpaca.

Routes multi-leg options orders via the Alpaca Trading API, with the
Alpaca MCP server / CLI as the agent-facing control surface. Manages
open positions against profit targets and stops.
"""
