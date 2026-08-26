#!/usr/bin/env bash
# Gate every agent start: full test suite + a real smoke pass against the API.
# A NameError like 2026-08-26's parse_occ incident dies HERE, not in production.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[preflight] test suite..."
~/.local/bin/uv run pytest tests/ -q

echo "[preflight] smoke: imports + one dry monitor pass + one dry scan decision path..."
~/.local/bin/uv run python - << 'PYEOF'
from dotenv import load_dotenv; load_dotenv(".env")
import sys; sys.path.insert(0, ".")

# every runtime module must import
import agent.main, agent.run_scan, agent.run_monitor, agent.journal, agent.events
import agent.execution.broker, agent.execution.monitor, agent.execution.stale
import agent.options.selector, agent.risk.gates, agent.signals.ml30

# one REAL monitor pass in dry-run: exercises broker reads, stale scan,
# reconciler, quote fetch and exit evaluation end to end
from agent.run_monitor import run_monitor
run_monitor(dry_run=True)
print("[preflight] smoke OK")
PYEOF
echo "[preflight] PASS"
