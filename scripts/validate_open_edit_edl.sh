#!/usr/bin/env bash
# validate_open_edit_edl.sh — validate an Open Edit exported EDL through the Go pipeline.
#
# Usage:
#   bin/validate_open_edit_edl.sh <project-dir> [edl-file] [--render]
#
# Example:
#   bin/validate_open_edit_edl.sh projects/my-clip edl.open_edit.json --render
#
# The script does not replace edl.json or project.mlt. It writes sibling bridge
# artifacts so users can inspect them before promotion:
#   project.open_edit.mlt
#   preview.open_edit.mp4  (only with --render)

set -euo pipefail

usage() {
    cat >&2 <<'USAGE'
usage: scripts/validate_open_edit_edl.sh <project-dir> [edl-file] [--render]

Validate an Open Edit exported EDL against the production Go pipeline.

Arguments:
  <project-dir>   Project directory containing metadata.json.
  [edl-file]      EDL file name/path. Defaults to edl.open_edit.json inside project-dir.
  --render        Also render preview.open_edit.mp4 using bin/render --dry-run.

Environment:
  MLT_PIPELINE_BRIDGE_RENDER_TIMEOUT  Render timeout, default 10m.
USAGE
}

if [[ $# -gt 0 && ( "$1" == "-h" || "$1" == "--help" ) ]]; then
    usage
    exit 0
fi

if [[ $# -lt 1 ]]; then
    usage
    exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="$1"
shift

EDL_PATH=""
DO_RENDER=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --render)
            DO_RENDER=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            if [[ -n "$EDL_PATH" ]]; then
                echo "unexpected extra argument: $1" >&2
                usage
                exit 2
            fi
            EDL_PATH="$1"
            shift
            ;;
    esac
done

PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"
if [[ -z "$EDL_PATH" ]]; then
    EDL_PATH="$PROJECT_DIR/edl.open_edit.json"
elif [[ "$EDL_PATH" != /* ]]; then
    EDL_PATH="$PROJECT_DIR/$EDL_PATH"
fi

METADATA_PATH="$PROJECT_DIR/metadata.json"
MLT_OUT="$PROJECT_DIR/project.open_edit.mlt"
PREVIEW_OUT="$PROJECT_DIR/preview.open_edit.mp4"

if [[ ! -f "$METADATA_PATH" ]]; then
    echo "missing metadata.json: $METADATA_PATH" >&2
    exit 1
fi
if [[ ! -f "$EDL_PATH" ]]; then
    echo "missing Open Edit EDL export: $EDL_PATH" >&2
    exit 1
fi

if [[ ! -x "$ROOT/bin/compile" ]]; then
    echo "building bin/compile" >&2
    (cd "$ROOT" && go build -o "$ROOT/bin/compile" ./cmd/compile)
fi
if [[ $DO_RENDER -eq 1 && ! -x "$ROOT/bin/render" ]]; then
    echo "building bin/render" >&2
    (cd "$ROOT" && go build -o "$ROOT/bin/render" ./cmd/render)
fi

"$ROOT/bin/compile" \
    --edl "$EDL_PATH" \
    --metadata "$METADATA_PATH" \
    --output "$MLT_OUT"

echo "validated: $MLT_OUT"

if [[ $DO_RENDER -eq 1 ]]; then
    "$ROOT/bin/render" \
        --mlt "$MLT_OUT" \
        --output "$PREVIEW_OUT" \
        --dry-run \
        --timeout "${MLT_PIPELINE_BRIDGE_RENDER_TIMEOUT:-10m}"
    echo "rendered: $PREVIEW_OUT"
fi

echo "Bridge validation passed. Promote artifacts manually only after review."
