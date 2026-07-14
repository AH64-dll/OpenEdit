#!/usr/bin/env bash
# edit.sh — one-shot wrapper: take a folder of raw clips, set up a project,
# run the pipeline, and open the result in Kdenlive.
#
# Usage:
#   ./edit.sh <source> [<project-name>] [--render] [--force]
#   ./edit.sh --help
#
# Forwards to ./run.sh <name> and xdg-opens projects/<name>/project.mlt
# when the pipeline succeeds.
#
# Idempotent: re-running is safe; existing symlinks are detected, finished
# pipeline stages are skipped, Kdenlive is re-launched.

set -euo pipefail

# Resolve script's own directory (the project root, since edit.sh lives there).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<EOF
Usage: $0 <source> [<project-name>] [--render] [--force]

  <source>        A directory of raw video files (.mp4/.mov/.mkv/.webm)
                  OR a single video file.
  <project-name>  Optional. Default: basename of <source>, last extension
                  stripped, spaces → '-', unsafe chars stripped.
  --render        Also run the final melt render to produce final.mp4.
  --force         Wipe existing project outputs (metadata.json, edl.json,
                  project.mlt, preview.mp4, final.mp4, *.lck) and re-run.
                  Does NOT touch footage/ symlinks. To re-point symlinks,
                  run: rm -rf projects/<name>/footage
  -h, --help      Show this help and exit.

Examples:
  $0 ~/Videos/wedding-raw
  $0 ~/Videos/wedding-raw my-wedding --render
  $0 ~/Videos/wedding-raw my-wedding --force
EOF
}

# --- Arg parsing -----------------------------------------------------------

if [[ $# -eq 0 ]]; then
    usage >&2
    exit 2
fi

# Handle --help before requiring a source.
case "${1:-}" in
    -h|--help)
        usage
        exit 0
        ;;
esac

if [[ $# -lt 1 ]]; then
    echo "edit.sh: missing <source> argument" >&2
    usage >&2
    exit 2
fi

SOURCE="$1"
shift

PROJECT_NAME=""
DO_RENDER=0
DO_FORCE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --render) DO_RENDER=1; shift ;;
        --force)  DO_FORCE=1;  shift ;;
        -h|--help) usage; exit 0 ;;
        *)
            # First non-flag arg after <source> is the project name.
            if [[ -z "$PROJECT_NAME" ]]; then
                PROJECT_NAME="$1"
                shift
            else
                echo "edit.sh: unknown argument: $1" >&2
                usage >&2
                exit 2
            fi
            ;;
    esac
done

# --- Sanity checks (placeholders, filled in by later tasks) ---------------

echo "edit.sh skeleton OK; source=$SOURCE project_name=$PROJECT_NAME render=$DO_RENDER force=$DO_FORCE" >&2
exit 0
