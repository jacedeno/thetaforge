#!/usr/bin/env bash
# ThetaForge agent loop — run inside a herdr session so it survives disconnects:
#   herdr --session thetaforge
#   ./scripts/run_loop.sh            # live orders (paper account from .env)
#   ./scripts/run_loop.sh --dry-run  # decisions only, no orders
set -euo pipefail
cd "$(dirname "$0")/.."
./scripts/preflight.sh || { echo "PREFLIGHT FAILED — refusing to start the agent"; exit 1; }
mkdir -p logs
exec ~/.local/bin/uv run python -m agent.main --loop "$@" 2>&1 | tee -a "logs/agent-$(date +%F).log"
