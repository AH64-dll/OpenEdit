#!/usr/bin/env bash
# .open-edit-stop.sh — stop the Open Edit server started by .open-edit-launcher.sh.

set -euo pipefail

PID_FILE="/tmp/open-edit-server.pid"
URL="${OPEN_EDIT_URL:-http://127.0.0.1:8765/}"

if [[ ! -f "$PID_FILE" ]]; then
    echo "[open-edit] no pid file at $PID_FILE — nothing to stop"
    exit 0
fi

PID="$(cat "$PID_FILE")"
if ! kill -0 "$PID" 2>/dev/null; then
    echo "[open-edit] pid $PID is not running — cleaning up"
    rm -f "$PID_FILE"
    exit 0
fi

echo "[open-edit] stopping pid $PID (server at $URL)"
kill "$PID"
# Give it 3 seconds to exit cleanly, then SIGKILL.
for _ in $(seq 1 6); do
    if ! kill -0 "$PID" 2>/dev/null; then
        rm -f "$PID_FILE"
        echo "[open-edit] stopped"
        exit 0
    fi
    sleep 0.5
done

kill -9 "$PID" 2>/dev/null || true
rm -f "$PID_FILE"
echo "[open-edit] force-killed"
