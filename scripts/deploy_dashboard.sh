#!/usr/bin/env bash
# Build and restart the dashboard together — a rebuild without a restart leaves
# the running server pointing at deleted chunks (blank page for visitors).
set -euo pipefail
cd "$(dirname "$0")/../dashboard"
npm run build
pkill -f next-server || true
sleep 1
setsid nohup npm run start -- -p 3777 >/dev/null 2>&1 < /dev/null &
sleep 4
curl -sf -o /dev/null http://localhost:3777 && echo "dashboard live on :3777"
