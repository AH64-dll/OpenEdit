#!/usr/bin/env bash
# PyAgent launcher — starts Kdenlive (the video editor) with the
# project, enables live D-Bus sync, starts the chat UI server,
# and opens it in the browser.
#
# Usage:
#   Double-click the desktop icon  -> opens the demo project.
#   Drag a .kdenlive file onto it  -> opens that project instead.
#
# Live mode: PYAGENT_LIVE=1 routes edits into the running
# Kdenlive window in real time (via D-Bus). If Kdenlive fails to
# start, the launcher falls back to file mode (edits land on the
# .kdenlive file; open it in Kdenlive yourself to see them).

set -euo pipefail

REPO="$(cd "$(dirname "$(realpath "${BASH_SOURCE[0]}")")" && pwd)"
DEMO="$REPO/phase3_pyagent_core/tests/fixtures/demo.kdenlive"
LOG_DIR="$HOME/.local/share/pyagent"
mkdir -p "$LOG_DIR"

PID_FILE="$LOG_DIR/pyagent.pid"

# Handle "stop" mode
if [[ "${1:-}" == "stop" ]]; then
    if [[ -f "$PID_FILE" ]]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo "Stopping PyAgent server (PID: $PID)..."
            kill "$PID"
            for i in $(seq 1 10); do
                if ! kill -0 "$PID" 2>/dev/null; then
                    break
                fi
                sleep 0.5
            done
        fi
        rm -f "$PID_FILE"
        echo "PyAgent stopped."
    else
        echo "No PyAgent server PID file found."
    fi
    exit 0
fi

# Resolve which .kdenlive the AI should edit.
detect_open_project() {
    local pid p
    pid=$(pgrep -x kdenlive 2>/dev/null | head -1)
    [[ -z "$pid" ]] && return 1
    p=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null | grep -o '/[^ ]*\.kdenlive' | head -1)
    [[ -n "$p" && -f "$p" ]] && { echo "$p"; return 0; }
    p=$(find "$HOME/Videos/edits" "$HOME" -maxdepth 4 -name '*.kdenlive' \
            -newermt '-2 hours' 2>/dev/null | head -1)
    [[ -n "$p" && -f "$p" ]] && { echo "$p"; return 0; }
    return 1
}

OPEN_PROJECT=""
if detect_open_project; then
    OPEN_PROJECT=$(detect_open_project)
fi

if [[ -n "${1:-}" && -f "$1" ]]; then
    PROJECT="$1"
elif [[ -n "$OPEN_PROJECT" ]]; then
    PROJECT="$OPEN_PROJECT"
    echo "Kdenlive is already open with: $PROJECT"
    echo "PyAgent will edit THAT project (live)."
else
    PROJECT="$DEMO"
fi

if [[ ! -f "$PROJECT" ]]; then
    kdialog --error "PyAgent: project file not found:\n$PROJECT" 2>/dev/null || true
    exit 1
fi

PORT=8123

# If a chat UI is already running on this port, just open the browser.
if curl -s -o /dev/null "http://127.0.0.1:$PORT/api/project"; then
    echo "Server already up on $PORT — opening browser."
    xdg-open "http://127.0.0.1:$PORT" >/dev/null 2>&1 &
    exit 0
fi

# --- Live mode + Kdenlive lifecycle --------------------------------
export PYAGENT_LIVE=1
KDENLIVE_LOG="$LOG_DIR/kdenlive.log"
kdenlive_running() {
    pgrep -x kdenlive >/dev/null 2>&1
}
if command -v kdenlive >/dev/null 2>&1; then
    if kdenlive_running; then
        echo "Kdenlive already running — syncing live to: $PROJECT"
    else
        echo "Starting Kdenlive with $PROJECT ..."
        nohup kdenlive "$PROJECT" > "$KDENLIVE_LOG" 2>&1 &
        for i in $(seq 1 20); do
            if PYTHONPATH="$REPO" python3 -c \
                "from phase5_dbus_sync.dbus_client import KdenliveDBus; import sys; sys.exit(0 if KdenliveDBus().available else 1)" \
                2>/dev/null; then
                echo "Kdenlive on D-Bus."
                break
            fi
            sleep 1
        done
    fi
else
    echo "kdenlive not found — falling back to file mode."
    unset PYAGENT_LIVE
fi

# --- Start the chat UI ----------------------------------------------
cd "$REPO"
PYTHONPATH=. nohup python3 -m phase4_chat_ui \
    --project "$PROJECT" \
    --port "$PORT" \
    --provider opencode-go \
    --model minimax-m3 \
    > "$LOG_DIR/pyagent_server.log" 2>&1 &

SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"

# Wait for it to come up, then open the browser.
for i in $(seq 1 30); do
    if curl -s -o /dev/null "http://127.0.0.1:$PORT/api/project"; then
        sleep 1
        xdg-open "http://127.0.0.1:$PORT" >/dev/null 2>&1 &
        echo "PyAgent ready at http://127.0.0.1:$PORT (project: $PROJECT)"
        echo "Live mode: ${PYAGENT_LIVE:+ON (edits go to Kdenlive)}${PYAGENT_LIVE:-OFF (file mode)}"
        exit 0
    fi
    sleep 1
done

kdialog --error "PyAgent: server failed to start.\nSee $LOG_DIR/pyagent_server.log" 2>/dev/null || true
exit 1
