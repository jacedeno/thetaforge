#!/usr/bin/env bash
# ThetaForge dashboard — run inside a persistent terminal session so it
# survives disconnects.
#   ./scripts/run_dashboard.sh
set -euo pipefail
cd "$(dirname "$0")/../dashboard"
npm run build && exec npm run start -- -p 3777
