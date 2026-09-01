#!/usr/bin/env bash
# Build and restart the dashboard together — a rebuild without a restart leaves
# the running server pointing at deleted chunks (blank page for visitors).
set -euo pipefail
cd "$(dirname "$0")/../dashboard"
npm run build
# Kill by PORT, never `pkill -f next-server`: this host also serves the ml30
# screener from its own next-server, and a name-wide kill takes it down too.
# ss reports the listener; its parent `sh -c next start` must go with it or
# the shell lingers holding the port.
for pid in $(ss -ltnpH "sport = :3777" | grep -oP 'pid=\K[0-9]+'); do
    kill "$(ps -o ppid= -p "$pid" | tr -d ' ')" "$pid" 2>/dev/null || true
done
sleep 1
setsid nohup npm run start -- -p 3777 >/dev/null 2>&1 < /dev/null &
sleep 4
curl -sf -o /dev/null http://localhost:3777 && echo "dashboard live on :3777"
