#!/usr/bin/env bash
# Install a downloaded release or a source checkout. Projects remain separate.
set -euo pipefail
PREFIX="${OPEN_EDIT_DIR:-$HOME/OpenEdit}"
NO_PROJECT=0; SYSTEM_RUNTIME=0; SKIP_SYSTEM=0; MEDIA_ONLY=0; EXTRAS=""
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help) printf '%s\n' 'Usage: install.sh [--dir PATH] [--no-project] [--system-runtime] [--skip-system-deps] [--media-only] [--with-agent] [--whisper]'; exit 0 ;;
    -dir|--dir) PREFIX="$2"; shift ;;
    --no-project) NO_PROJECT=1 ;;
    --system-runtime) SYSTEM_RUNTIME=1 ;;
    --skip-system-deps) SKIP_SYSTEM=1 ;;
    --media-only) MEDIA_ONLY=1 ;;
    --with-agent) EXTRAS="${EXTRAS:+$EXTRAS,}agent" ;;
    --whisper) EXTRAS="${EXTRAS:+$EXTRAS,}whisper" ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
  shift
done
[ "$(uname -s)" = Linux ] || { printf '%s\n' 'This release installer supports Linux. See INSTALL.md for macOS source setup.' >&2; exit 1; }
mkdir -p "$PREFIX"
PREFIX="$(cd "$PREFIX" && pwd)"
if [ ! -f "$HERE/pyproject.toml" ] && [ ! -d "$HERE/wheels" ]; then
  command -v git >/dev/null || { printf '%s\n' 'Git is required when installing without the release archive.' >&2; exit 1; }
  if [ ! -d "$PREFIX/source/.git" ]; then git clone https://github.com/AH64-dll/OpenEdit.git "$PREFIX/source"; fi
  HERE="$PREFIX/source"
fi
if [ "$SKIP_SYSTEM" = 0 ] && command -v apt-get >/dev/null; then
  # Debian/Ubuntu: browser system libraries and Python's venv module.
  RUN_AS_ROOT=()
  if [ "$(id -u)" != 0 ]; then
    command -v sudo >/dev/null || { printf '%s\n' 'Install python3-venv and Chromium system libraries as administrator, then rerun with --skip-system-deps (see INSTALL.md).' >&2; exit 1; }
    RUN_AS_ROOT=(sudo)
  fi
  "${RUN_AS_ROOT[@]}" apt-get update
  "${RUN_AS_ROOT[@]}" apt-get install -y python3-venv libnss3 libatk-bridge2.0-0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libxkbcommon0 libpango-1.0-0 fonts-liberation
fi
PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3,11,8))'; then PYTHON="$candidate"; break; fi
done
[ -n "$PYTHON" ] || { printf '%s\n' 'Python 3.11.8 or newer is required (3.12 recommended).' >&2; exit 1; }
"$PYTHON" -m venv "$PREFIX/.venv"
PY="$PREFIX/.venv/bin/python"
BOOTSTRAP=()
if [ "$SYSTEM_RUNTIME" = 1 ]; then BOOTSTRAP+=(--system-runtime); fi
"$PY" "$HERE/scripts/bootstrap_runtime.py" --prefix "$PREFIX" "${BOOTSTRAP[@]}"
"$PY" -I -m pip install --upgrade pip
if [ -d "$HERE/wheels" ]; then
  mapfile -t WHEELS < <(find "$HERE/wheels" -maxdepth 1 -name 'open_edit-*.whl' -type f)
  [ "${#WHEELS[@]}" = 1 ] || { printf '%s\n' 'Expected one OpenEdit wheel in this release.' >&2; exit 1; }
  PACKAGE="${WHEELS[0]}"
else PACKAGE="$HERE"; fi
if [ -n "$EXTRAS" ]; then PACKAGE="$PACKAGE[$EXTRAS]"; fi
"$PY" -I -m pip install --upgrade --force-reinstall -c "$HERE/requirements/release-constraints.txt" "$PACKAGE"
"$PY" -I -m pip check
FEATURE=graphics
if [ "$MEDIA_ONLY" = 1 ]; then FEATURE=media; fi
"$PY" -I -m open_edit.cli setup "$FEATURE"
VERIFY=()
if [ "$MEDIA_ONLY" = 0 ]; then VERIFY+=(--graphics); fi
"$PY" -I "$HERE/scripts/verify_install.py" "${VERIFY[@]}" --output "$PREFIX/install-report.json"
cat > "$PREFIX/OpenEdit.sh" <<'LAUNCH'
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec "$ROOT/.venv/bin/python" -I -m open_edit.cli serve "$@"
LAUNCH
chmod +x "$PREFIX/OpenEdit.sh"
PROJECT="${OPEN_EDIT_STARTER_PROJECT:-$HOME/OpenEditProjects/my-edit}"
if [ "$NO_PROJECT" = 0 ]; then
  mkdir -p "$PROJECT"
  if [ ! -f "$PROJECT/.open_edit/edit_graph.db" ]; then "$PY" -I -m open_edit.cli init "$PROJECT"; fi
  "$PY" -I -m open_edit.cli mcp-config --project "$PROJECT" --output "$PREFIX/mcp.json"
  "$PY" -I -m open_edit.cli mcp-config --project "$PROJECT" --format opencode --output "$PREFIX/opencode.json"
  "$PY" -I -m open_edit.cli mcp-config --project "$PROJECT" --format codex --output "$PREFIX/codex.toml"
fi
printf '\nVerified OpenEdit installation: %s\nStart: %s/OpenEdit.sh\nAgent configuration: %s/mcp.json (or run open_edit mcp-config --project PATH)\n' "$PREFIX" "$PREFIX" "$PREFIX"
