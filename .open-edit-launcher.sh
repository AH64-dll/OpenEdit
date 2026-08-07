#!/usr/bin/env bash
# .open-edit-launcher.sh — start the Open Edit server and open the browser.
#
# Idempotent: if the server is already running, just opens the browser.
# Logs to /tmp/open-edit-launcher.log. Leaves a PID file for the stop script.
#
# Usage:
#   .open-edit-launcher.sh           # default port 8765
#   .open-edit-launcher.sh 9000      # custom port

set -euo pipefail

# --- Config ----------------------------------------------------------------

PROJECT_DIR="${OPEN_EDIT_PROJECT_DIR:-/home/amr/apps/mlt-pipeline/open_edit}"
VENV_PY="$PROJECT_DIR/.venv/bin/python"
CLI="$PROJECT_DIR/.venv/bin/open_edit"
DEFAULT_PORT="${OPEN_EDIT_PORT:-8765}"
PORT="${1:-$DEFAULT_PORT}"
HOST="${OPEN_EDIT_HOST:-127.0.0.1}"
URL="http://${HOST}:${PORT}/"
PID_FILE="/tmp/open-edit-server.pid"
LOG_FILE="/tmp/open-edit-server.log"

# --- Helpers ---------------------------------------------------------------

log() { printf '[open-edit] %s\n' "$*" | tee -a "$LOG_FILE" >&2 ; }

is_server_up() {
    curl -sf -o /dev/null --max-time 2 "$URL" 2>/dev/null
}

wait_for_server() {
    local i
    for i in $(seq 1 30); do
        if is_server_up; then
            return 0
        fi
        sleep 0.5
    done
    return 1
}

notify() {
    local title="$1" body="$2" icon="$3"  # icon: info|warning|critical
    if command -v kdialog >/dev/null 2>&1; then
        kdialog --passivepopup "$body" 5 --title "$title" >/dev/null 2>&1 || true
    elif command -v notify-send >/dev/null 2>&1; then
        notify-send -t 5000 -u "$icon" "$title" "$body" 2>/dev/null || true
    fi
}

open_browser() {
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$URL" >/dev/null 2>&1 || true
    fi
}

# --- Main ------------------------------------------------------------------

cd "$PROJECT_DIR"

# If a server is already running on this port, just open the browser.
if is_server_up; then
    log "server already up at $URL — opening browser"
    open_browser
    notify "Open Edit" "Already running at $URL" "info"
    exit 0
fi

# If a stale PID file points at a dead process, clean it up.
if [[ -f "$PID_FILE" ]] && ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    rm -f "$PID_FILE"
fi

# Verify venv exists.
if [[ ! -x "$VENV_PY" ]]; then
    log "ERROR: venv python not found at $VENV_PY"
    log "Run: cd $PROJECT_DIR && python -m venv .venv && .venv/bin/pip install -e '.[serve]'"
    notify "Open Edit" "Venv missing — see $LOG_FILE" "critical"
    exit 1
fi

# Start server in background; redirect output to log file.
log "starting server on $URL (logs: $LOG_FILE)"
: > "$LOG_FILE"
export OPEN_EDIT_PROJECTS_ROOT="${OPEN_EDIT_PROJECTS_ROOT:-/home/amr/OpenEditProjects}"
log "sandbox allowed roots: $OPEN_EDIT_PROJECTS_ROOT"
nohup "$CLI" serve \
    --host "$HOST" \
    --port "$PORT" \
    --log-level info \
    >>"$LOG_FILE" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"
log "server pid=$SERVER_PID"

# Wait up to 15s for the server to start accepting connections.
if ! wait_for_server; then
    log "ERROR: server did not start within 15s — last log lines:"
    tail -n 20 "$LOG_FILE" | sed 's/^/    /' >&2
    notify "Open Edit" "Failed to start — see $LOG_FILE" "critical"
    rm -f "$PID_FILE"
    exit 1
fi

log "server up — opening browser"
open_browser
notify "Open Edit" "Running at $URL" "info"

# Disown so the server keeps running after the launcher exits.
disown "$SERVER_PID" 2>/dev/null || true
exit 0
