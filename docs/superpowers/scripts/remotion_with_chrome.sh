#!/usr/bin/env bash
# Phase-1 only: invoke chrome-aware remotion bridge via OPEN_EDIT_REMOTION_BIN.
set -euo pipefail
BRIDGE="$(cd "$(dirname "$0")" && pwd)/remotion_bridge_chrome.mjs"
exec node "$BRIDGE" "$@"
