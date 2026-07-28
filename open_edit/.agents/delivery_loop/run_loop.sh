#!/usr/bin/env bash
# Delivery debug heartbeat — wakes the agent on a schedule.
# Stop: kill this shell or delete the loop PID file.
set -euo pipefail
INTERVAL="${1:-900}"  # default 15 minutes
PROMPT='Delivery loop tick: read open_edit/.agents/delivery_loop/ORCHESTRATOR.md and PROGRESS.md. Run checklist tests. If not 100% ready, assign Composer worker tasks and update PROGRESS.md. If 100% ready, output AGENT_LOOP_DONE delivery certified.'
while true; do
  sleep "$INTERVAL"
  echo "AGENT_LOOP_WAKE_delivery {\"prompt\":\"$PROMPT\"}"
done
