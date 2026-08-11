#!/usr/bin/env bash
#
# Open Edit - one-command installer (Linux / macOS)
#
# Clones the Open Edit repository, creates a virtualenv, installs the MCP
# server, verifies it, and (by default) creates a starter edit project.
#
# Usage:
#   ./install.sh                     # clone to ~/OpenEdit, install, starter project
#   ./install.sh -dir /path/to/dir   # install into /path/to/dir
#   ./install.sh --no-project        # skip the starter project
#   ./install.sh --help              # this help
#
# Environment:
#   OPEN_EDIT_DIR   install directory (used when -dir is not given)
#
# Notes:
#   - No sudo required. Everything stays under your home directory.
#   - Re-running is safe: an existing clone is reused and updated.
#   - Pipe-safe (curl ... | bash): the only prompt (starter project)
#     defaults to "yes" when stdin is not a terminal.
set -euo pipefail

REPO_URL="https://github.com/AH64-dll/OpenEdit.git"
DEFAULT_DIR="${HOME}/OpenEdit"
DEFAULT_PROJECT_DIR="${HOME}/OpenEditProjects/my-talk"

INSTALL_DIR=""
NO_PROJECT=0

show_help() {
  cat <<'EOF'
Open Edit installer - Linux / macOS

Usage:
  ./install.sh                      install to ~/OpenEdit, create starter project
  ./install.sh -dir /path/to/dir    install into /path/to/dir
  ./install.sh --no-project         skip the starter project
  ./install.sh --help               show this help

Options:
  -dir, --dir <path>   install directory (default: ~/OpenEdit, or $OPEN_EDIT_DIR)
  --no-project         do not create the starter project (~/OpenEditProjects/my-talk)
  -h, --help           show this help

Environment:
  OPEN_EDIT_DIR        install directory (used when -dir is not given)

Notes:
  - No sudo required; everything stays under your home directory.
  - Re-running is safe: an existing clone is reused and updated.
  - Prerequisites: git, and Python 3.11 or newer.
EOF
}

say()   { printf '%s\n' "$*"; }
warn()  { printf 'warning: %s\n' "$*" >&2; }
die()   { printf 'error: %s\n' "$*" >&2; exit 1; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help) show_help; exit 0 ;;
    --no-project) NO_PROJECT=1 ;;
    -dir|--dir)
      [ "$#" -ge 2 ] || die "$1 requires an argument"
      INSTALL_DIR="$2"
      shift
      ;;
    --dir=*) INSTALL_DIR="${1#*=}" ;;
    *) die "unknown option: $1 (run with --help for usage)" ;;
  esac
  shift
done

if [ -n "$INSTALL_DIR" ]; then
  : # CLI -dir wins
elif [ -n "${OPEN_EDIT_DIR:-}" ]; then
  INSTALL_DIR="$OPEN_EDIT_DIR"
else
  INSTALL_DIR="$DEFAULT_DIR"
fi

# ---- Resolve the install directory to an absolute path ---------------------
make_abs() {
  local d="$1"
  if [ -d "$d" ]; then
    (cd "$d" && pwd -P)
  else
    local parent
    parent="$(dirname "$d")"
    if [ -d "$parent" ]; then
      printf '%s/%s\n' "$(cd "$parent" && pwd -P)" "$(basename "$d")"
    else
      printf '%s\n' "$d"
    fi
  fi
}
INSTALL_DIR="$(make_abs "$INSTALL_DIR")"

# ---- Prerequisites ---------------------------------------------------------
if ! command -v git >/dev/null 2>&1; then
  die "git is required but was not found on PATH. Install git and re-run."
fi

FOUND_OLD=""
detect_python() {
  local cand ver
  for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then
      ver="$("$cand" -c 'import sys; print(".".join(str(v) for v in sys.version_info[:3]))' 2>/dev/null || true)"
      if [ -n "$ver" ]; then
        if "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
          PYTHON="$cand"
          PYTHON_VERSION="$ver"
          return 0
        fi
        [ -n "$FOUND_OLD" ] || FOUND_OLD="$cand ($ver)"
      fi
    fi
  done
  return 1
}

if ! detect_python; then
  if [ -n "$FOUND_OLD" ]; then
    die "Python 3.11+ is required but only $FOUND_OLD was found. Install Python 3.11+ (https://www.python.org/downloads/) and re-run."
  fi
  die "Python 3.11+ is required but neither 'python3' nor 'python' was found on PATH. Install Python 3.11+ and re-run."
fi
say "Using Python ${PYTHON_VERSION} ($PYTHON)"

# ---- Clone (or reuse) ------------------------------------------------------
if [ -d "$INSTALL_DIR/.git" ]; then
  say "Reusing existing clone at $INSTALL_DIR"
  origin="$(git -C "$INSTALL_DIR" remote get-url origin 2>/dev/null || true)"
  case "$origin" in
    *OpenEdit*) ;;
    *) die "directory $INSTALL_DIR is a git repository but its origin ($origin) does not look like Open Edit; remove it or pick another -dir" ;;
  esac
  say "Updating existing clone (git pull --ff-only) ..."
  if ! git -C "$INSTALL_DIR" pull --ff-only >/dev/null 2>&1; then
    warn "could not fast-forward the existing clone; continuing with what is there"
  fi
elif [ -e "$INSTALL_DIR" ]; then
  if [ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
    die "install directory $INSTALL_DIR exists, is not empty, and is not a git clone. Remove it or choose another directory with -dir."
  fi
  say "Cloning $REPO_URL into $INSTALL_DIR ..."
  git clone "$REPO_URL" "$INSTALL_DIR"
else
  say "Cloning $REPO_URL into $INSTALL_DIR ..."
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

[ -f "$INSTALL_DIR/pyproject.toml" ] || die "clone at $INSTALL_DIR does not look like Open Edit (no pyproject.toml)"

# ---- Virtualenv + install --------------------------------------------------
cd "$INSTALL_DIR"
say "Creating virtualenv at $INSTALL_DIR/.venv ..."
if ! "$PYTHON" -m venv .venv; then
  die "failed to create the virtualenv. On Debian/Ubuntu this usually means python3-venv is missing (apt install python3-venv)."
fi

VENV_PY="$INSTALL_DIR/.venv/bin/python"
MCP_BIN="$INSTALL_DIR/.venv/bin/open-edit-mcp"
OPEN_EDIT_BIN="$INSTALL_DIR/.venv/bin/open_edit"

say "Upgrading pip ..."
"$VENV_PY" -m pip install -U pip

say "Installing core package (.[mcp]) ..."
if ! "$VENV_PY" -m pip install -e ".[mcp]"; then
  die "pip install -e '.[mcp]' failed. See the output above; check your network and Python setup, then re-run."
fi

say "Installing optional extras (.[mcp,serve]) ..."
if ! "$VENV_PY" -m pip install -e ".[mcp,serve]"; then
  warn ".[mcp,serve] (review UI) extras install failed; continuing without the review UI."
fi

say "Installing optional extras (.[mcp,whisper]) ..."
if ! "$VENV_PY" -m pip install -e ".[mcp,whisper]"; then
  warn ".[mcp,whisper] (local transcription) extras install failed; continuing without whisper support."
fi

# ---- Verify the MCP server -------------------------------------------------
say "Verifying MCP server: $MCP_BIN --help ..."
if ! "$MCP_BIN" --help >/dev/null 2>&1; then
  warn "first verification attempt failed; showing output:"
  "$MCP_BIN" --help || true
  die "MCP server verification failed ('open-edit-mcp --help' exited non-zero). Re-run the installer or inspect the pip output above."
fi

# ---- Starter project -------------------------------------------------------
PROJECT_DIR="$DEFAULT_PROJECT_DIR"
PROJECT_CREATED=0
if [ "$NO_PROJECT" -eq 1 ]; then
  say "Skipping starter project (--no-project)."
else
  ans=""
  if [ -t 0 ]; then
    printf 'Create a starter project at %s? [Y/n] ' "$PROJECT_DIR" >&2
    read -r ans || true
  else
    read -r ans <&0 || true   # EOF or piped 'n' - EOF defaults to yes
  fi
  case "$ans" in
    n|N|no|No|NO)
      say "Skipping starter project."
      ;;
    *)
      say "Creating starter project at $PROJECT_DIR ..."
      mkdir -p "$PROJECT_DIR"
      if ! "$OPEN_EDIT_BIN" init "$PROJECT_DIR"; then
        die "failed to initialize the starter project at $PROJECT_DIR"
      fi
      PROJECT_CREATED=1
      ;;
  esac
fi

# ---- Summary ---------------------------------------------------------------
if [ "$PROJECT_CREATED" -eq 1 ]; then
  PROJECT_DISPLAY="$PROJECT_DIR"
  MCP_ARGS_LINE="\"args\": [\"--project\", \"$PROJECT_DIR\"],"
  PROJECT_HINT=""
else
  PROJECT_DISPLAY="none (--no-project)"
  MCP_ARGS_LINE=""
  PROJECT_HINT="
     Create a project later with: $OPEN_EDIT_BIN init <folder>"
fi

cat <<EOF

Open Edit installed successfully.

  Clone directory : $INSTALL_DIR
  Virtualenv      : $INSTALL_DIR/.venv
  MCP server      : $MCP_BIN
  Project         : $PROJECT_DISPLAY$PROJECT_HINT

Verification passed: $MCP_BIN --help

Next steps:
  1. Register the MCP server with Cursor (or your agent host).
     Add to ${HOME}/.cursor/mcp.json:

     {
       "mcpServers": {
         "open-edit": {
           "command": "$MCP_BIN",
           ${MCP_ARGS_LINE}
           "env": { "OPEN_EDIT_RENDER_BACKEND": "cpu" }
         }
       }
     }

     Then reload MCP in Cursor.

  2. Start the Review Studio:

       $OPEN_EDIT_BIN serve --review-only --port 8000

     and open http://127.0.0.1:8000

Done.
EOF
