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

# --- Derive project name --------------------------------------------------

sanitize_name() {
    # Replace spaces with '-', strip characters outside [A-Za-z0-9_-].
    local name="$1"
    name="${name// /-}"
    name="${name//[^A-Za-z0-9_-]/}"
    # Trim leading/trailing dashes/underscores.
    name="${name#[-+_]}"
    name="${name%[-+_]}"
    echo "$name"
}

if [[ -z "$PROJECT_NAME" ]]; then
    if [[ -f "$SOURCE" ]]; then
        # Single file: project name = file stem (last extension stripped).
        PROJECT_NAME="$(basename "$SOURCE")"
        PROJECT_NAME="${PROJECT_NAME%.*}"
    else
        # Directory: project name = directory basename.
        PROJECT_NAME="$(basename "$SOURCE")"
    fi
    PROJECT_NAME="$(sanitize_name "$PROJECT_NAME")"
    if [[ -z "$PROJECT_NAME" ]]; then
        echo "edit.sh: cannot derive a project name from '$SOURCE'" >&2
        exit 2
    fi
fi

# --- Validate source -------------------------------------------------------

if [[ ! -e "$SOURCE" ]]; then
    echo "edit.sh: $SOURCE: not found" >&2
    exit 2
fi
if [[ ! -r "$SOURCE" ]]; then
    echo "edit.sh: $SOURCE: not readable" >&2
    exit 2
fi

# Collect video files. If SOURCE is a file, treat it as a one-clip project.
declare -a VIDEO_FILES=()
if [[ -f "$SOURCE" ]]; then
    case "${SOURCE,,}" in
        *.mp4|*.mov|*.mkv|*.webm) VIDEO_FILES=("$SOURCE") ;;
        *) echo "edit.sh: $SOURCE: unsupported file type (need .mp4/.mov/.mkv/.webm)" >&2; exit 2 ;;
    esac
elif [[ -d "$SOURCE" ]]; then
    while IFS= read -r -d '' f; do
        VIDEO_FILES+=("$f")
    done < <(find "$SOURCE" -maxdepth 1 -type f \( -iname '*.mp4' -o -iname '*.mov' -o -iname '*.mkv' -o -iname '*.webm' \) -print0 | sort -z)
    if [[ ${#VIDEO_FILES[@]} -eq 0 ]]; then
        echo "edit.sh: $SOURCE: no .mp4/.mov/.mkv/.webm files found" >&2
        exit 2
    fi
else
    echo "edit.sh: $SOURCE: not a file or directory" >&2
    exit 2
fi

# --- (later tasks will add setup, delegation, and open) -------------------

echo "edit.sh: validated source OK" >&2
echo "  source       = $SOURCE" >&2
echo "  project_name = $PROJECT_NAME" >&2
echo "  files        = ${#VIDEO_FILES[@]}" >&2
echo "  render       = $DO_RENDER" >&2
echo "  force        = $DO_FORCE" >&2
exit 0
