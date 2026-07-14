#!/usr/bin/env bash
# run.sh — orchestrate analyze → agent → compile → render for one project.
#
# Usage:
#   ./run.sh <project-name> [--force] [--render | --no-render]
#
# Idempotent: re-running skips any stage whose output already exists.
# Writes only to projects/<name>/.

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "usage: $0 <project-name> [--force] [--render | --no-render]" >&2
    exit 2
fi

PROJECT_NAME="$1"
shift

FORCE=0
DO_RENDER=0  # 0 = --no-render (default), 1 = --render
while [[ $# -gt 0 ]]; do
    case "$1" in
        --force) FORCE=1; shift ;;
        --render) DO_RENDER=1; shift ;;
        --no-render) DO_RENDER=0; shift ;;
        *) echo "unknown flag: $1" >&2; exit 2 ;;
    esac
done

# Resolve project directory (relative to repo root).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$ROOT/projects/$PROJECT_NAME"

mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# Helper: skip a stage if its marker exists, unless --force.
should_run() {
    [[ $FORCE -eq 1 ]] && return 0
    [[ ! -e "$1" ]] && return 0
    return 1
}

echo "=== mlt-pipeline: $PROJECT_NAME ==="
echo "Project dir: $PROJECT_DIR"

# Stage 1: analyze
if should_run metadata.json; then
    echo
    echo "--- Stage 1: analyze ---"
    if [[ -d footage && -n "$(ls -A footage 2>/dev/null)" ]]; then
        "$ROOT/bin/analyze" --output metadata.json footage/*
    else
        echo "no footage/ directory or empty; skipping analyze" >&2
        # Write a minimal manifest so the driver doesn't loop.
        if [[ ! -f metadata.json ]]; then
            echo '{"version":1,"clips":[],"totalDurationSec":0}' > metadata.json
        fi
    fi
else
    echo "--- Stage 1: analyze (skip; metadata.json exists) ---"
fi

# Stage 2: agent
if should_run edl.json; then
    echo
    echo "--- Stage 2: agent (opencode) ---"
    nice -n 5 opencode -p "$ROOT/prompts/edl_writer.md" -f json -q
    AGENT_EXIT=$?
    if [[ $AGENT_EXIT -ne 0 || -f edl.failed.json ]]; then
        echo "agent failed; see edl.failed.json if present" >&2
        exit 1
    fi
    if [[ ! -f edl.json ]]; then
        echo "agent exited 0 but edl.json not found" >&2
        exit 1
    fi
else
    echo "--- Stage 2: agent (skip; edl.json exists) ---"
fi

# Stage 3: compile
if should_run project.mlt; then
    echo
    echo "--- Stage 3: compile ---"
    "$ROOT/bin/compile" \
        --edl edl.json \
        --metadata metadata.json \
        --output project.mlt
else
    echo "--- Stage 3: compile (skip; project.mlt exists) ---"
fi

# Stage 4: render --dry-run
if should_run preview.mp4; then
    echo
    echo "--- Stage 4: render --dry-run ---"
    "$ROOT/bin/render" \
        --mlt project.mlt \
        --output preview.mp4 \
        --dry-run
else
    echo "--- Stage 4: render --dry-run (skip; preview.mp4 exists) ---"
fi

# Stage 5: optional final render
if [[ $DO_RENDER -eq 1 ]]; then
    if should_run final.mp4; then
        echo
        echo "--- Stage 5: final render ---"
        "$ROOT/bin/render" \
            --mlt project.mlt \
            --output final.mp4
    else
        echo "--- Stage 5: final render (skip; final.mp4 exists) ---"
    fi
else
    echo "--- Stage 5: final render (skipped; pass --render to enable) ---"
fi

echo
echo "=== done ==="
echo "Open projects/$PROJECT_NAME/project.mlt in Kdenlive to refine."
