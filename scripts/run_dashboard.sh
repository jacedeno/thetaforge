#!/usr/bin/env bash
# ThetaForge dashboard — run inside a herdr session:
#   herdr --session tf-dash
#   ./scripts/run_dashboard.sh
set -euo pipefail
cd "$(dirname "$0")/../dashboard"
npm run build && exec npm run start -- -p 3777
