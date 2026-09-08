#!/usr/bin/env bash
# ThetaForge agent loop — run inside a herdr session so it survives disconnects:
#   herdr --session thetaforge
#   ./scripts/run_loop.sh            # live orders (paper account from .env)
#   ./scripts/run_loop.sh --dry-run  # decisions only, no orders
set -euo pipefail
cd "$(dirname "$0")/.."
./scripts/preflight.sh || { echo "PREFLIGHT FAILED — refusing to start the agent"; exit 1; }
mkdir -p logs
# The log file is chosen per LINE, not once at startup. This loop is run by
# hand rather than as a system service, so a single invocation routinely spans
# days: a name fixed by `date` at launch put 2026-09-06, -07 and -08 all inside
# agent-2026-09-06.log, while the 6th itself was split across two files by that
# morning's restart -- so no file held one day, and one day sat in two files.
# The date in the name now matches the lines under it, and a restart appends to
# the running day instead of opening a new file.
# `printf %()T` is a bash builtin, so this costs no subprocess per line.
~/.local/bin/uv run python -m agent.main --loop "$@" 2>&1 \
  | while IFS= read -r line; do
      printf -v day '%(%Y-%m-%d)T' -1
      printf '%s\n' "$line" | tee -a "logs/agent-$day.log"
    done
