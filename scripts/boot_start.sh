#!/usr/bin/env bash
# Bring ThetaForge back up after the host reboots.
#
# The agent loop runs detached rather than as a service, so nothing owns its
# lifecycle: when the machine restarts, the loop simply stops existing. On
# 2026-09-02 a reboot took it down mid-session and the only reason anyone
# noticed was a human asking. This script is the @reboot entry point that
# closes that gap.
#
# Safe to run at any time, any number of times:
#   - it refuses to start a second agent tree;
#   - starting outside market hours is a no-op inside the loop, which sleeps
#     on its own clock guard until the open.
#
# Exit codes, so a caller can tell the three outcomes apart without parsing
# log lines (a caller that greps for a phrase reports whatever the phrase
# happens to say, and announces a restart that never happened):
#   0   the agent was started
#   10  nothing to do — it was already up
#   1   it should have started and did not; alert on this
#
# A dashboard failure is reported but never fatal — the trading loop matters,
# a web page does not.
set -uo pipefail

EXIT_STARTED=0
EXIT_NOOP=10
EXIT_FAILED=1

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

# cron runs with a minimal PATH; uv, node and ss must all be discoverable.
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

HEARTBEAT="$REPO/data/heartbeat.json"
BROKER_URL="https://paper-api.alpaca.markets/v2/clock"
NET_WAIT_S=300        # boot races DNS; give the network five minutes
START_WAIT_S=300      # preflight runs the full suite + a live smoke pass

log() { echo "$(date -Is) boot_start: $*"; }

# One boot, one run. data/ is gitignored, so the lock lives there.
mkdir -p "$REPO/data"
exec 9>"$REPO/data/.boot.lock"
if ! flock -n 9; then
    log "another boot_start already holds the lock — exiting"
    exit "$EXIT_NOOP"
fi

# 1. Never a second tree. Two loops on one account would double every order.
if pgrep -f "agent\.main --loop" >/dev/null; then
    log "agent already running (pid $(pgrep -f 'agent\.main --loop' | tr '\n' ' ')) — nothing to do"
    exit "$EXIT_NOOP"
fi

# 2. Wait for the network. preflight ends in a live broker call, and at
#    @reboot time DNS is routinely not up yet — without this the gate fails
#    for a reason that has nothing to do with the code.
#    Deliberately NO --fail and no credentials: this asks "can I reach the
#    broker", not "am I authorised". The endpoint answers 401 to an unsigned
#    request, which --fail would treat as a failure and spin here until the
#    timeout, never starting the agent. curl still exits non-zero on the
#    cases that actually matter at boot — DNS not up, no route, timeout.
log "waiting for broker connectivity..."
deadline=$(( $(date +%s) + NET_WAIT_S ))
until curl -s -m 5 -o /dev/null "$BROKER_URL"; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
        log "FATAL: no broker connectivity after ${NET_WAIT_S}s — agent NOT started"
        exit "$EXIT_FAILED"
    fi
    sleep 5
done
log "broker reachable"

# 3. Start the loop detached from cron's process group. run_loop.sh gates
#    itself on preflight, so there is deliberately no second gate here.
before=0
[ -f "$HEARTBEAT" ] && before=$(stat -c %Y "$HEARTBEAT")
# 9>&- keeps the lock out of the child. Without it the agent inherits the
# open descriptor and holds the lock for its entire life, so every later run
# stops at the lock instead of reaching the "already running" check above —
# reporting a stale-lock collision where there is simply a healthy agent.
setsid nohup ./scripts/run_loop.sh >/dev/null 2>&1 </dev/null 9>&- &

# 4. Verify it actually came up. The loop writes the heartbeat at the top of
#    its first iteration — i.e. only AFTER preflight passed. A refreshed
#    heartbeat is therefore proof of a real start, which "the process exists"
#    is not: a failing preflight also leaves a process around, briefly.
log "waiting for the first heartbeat..."
deadline=$(( $(date +%s) + START_WAIT_S ))
until [ -f "$HEARTBEAT" ] && [ "$(stat -c %Y "$HEARTBEAT")" -gt "$before" ]; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
        log "FATAL: no heartbeat after ${START_WAIT_S}s — preflight likely failed."
        log "       check the newest logs/agent-*.log for PREFLIGHT FAILED"
        exit "$EXIT_FAILED"
    fi
    sleep 5
done
log "agent up — $(cat "$HEARTBEAT")"

# 5. Dashboard. deploy_dashboard.sh kills by port before starting, which is a
#    no-op when nothing is listening, so it doubles as the boot path.
#    9>&- for the same reason as the agent: the server it leaves running would
#    otherwise hold the lock for its entire life, and a long-lived web server
#    is the least obvious thing to go looking for when the next boot reports
#    that another boot_start is already running.
if ./scripts/deploy_dashboard.sh >/dev/null 2>&1 9>&-; then
    log "dashboard up on :3777"
else
    log "WARNING: dashboard did not come up (agent is unaffected)"
fi

log "done"

exit "$EXIT_STARTED"
