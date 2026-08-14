#!/usr/bin/env bash
#
# Open Edit - one-command installer (Linux / macOS)
#
# Clones the Open Edit repository, creates a virtualenv, installs the MCP
# server, installs the npm render dependencies (hyperframes), verifies the
# MCP server, and (by default) creates a starter edit project. Ends with a
# runtime-readiness summary for the render pipeline (ffmpeg/melt/node/
# hyperframes/chrome) — missing binaries warn but never fail the install.
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
  - Node.js 22+ is required for motion-graphics (hyperframes) rendering;
    when missing, a user-local Node is downloaded from nodejs.org (no sudo).
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

# ---- Node.js (required for hyperframes rendering) --------------------------
# The render pipeline pins hyperframes@0.7.65 in package.json; its CLI needs
# Node >= 22. When the system Node is missing (or too old) we download the
# official tarball into $INSTALL_DIR/.node — user-local, no sudo.
NODE_LTS_FALLBACK="v22.14.0"
NODE_BIN=""
NODE_DIR=""
NODE_VERSION=""

fetch_url() {
  # fetch_url <url> <outfile>
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --retry 3 "$1" -o "$2"
  elif command -v wget >/dev/null 2>&1; then
    wget -q "$1" -O "$2"
  else
    return 1
  fi
}

resolve_node_lts() {
  # Latest LTS version (e.g. v24.x.y) from nodejs.org; empty on any failure.
  local json
  if command -v curl >/dev/null 2>&1; then
    json="$(curl -fsSL --max-time 20 https://nodejs.org/dist/index.json 2>/dev/null || true)"
  elif command -v wget >/dev/null 2>&1; then
    json="$(wget -qO- --timeout=20 https://nodejs.org/dist/index.json 2>/dev/null || true)"
  fi
  if [ -n "$json" ]; then
    printf '%s' "$json" | tr '}' '\n' | sed -n 's/.*"version":"\(v[0-9][0-9.]*\)".*"lts":"[^"]*".*/\1/p' | head -1
  fi
}

install_node_local() {
  # Download the official Node tarball into $INSTALL_DIR/.node (no sudo).
  local os arch node_arch node_version url tmp_tar
  os="$(uname -s)"
  case "$os" in
    Darwin)
      warn "Node.js is missing and macOS auto-install is not supported by this installer."
      warn "Install Node 22+ first, e.g. 'brew install node' (or https://nodejs.org), then re-run."
      return 1
      ;;
    Linux) ;;
    *)
      warn "Unsupported OS '$os' for Node auto-install; install Node 22+ manually from https://nodejs.org and re-run."
      return 1
      ;;
  esac
  arch="$(uname -m)"
  case "$arch" in
    x86_64|amd64) node_arch="x64" ;;
    aarch64|arm64) node_arch="arm64" ;;
    *)
      warn "Unsupported architecture '$arch' for Node auto-install; install Node 22+ manually from https://nodejs.org and re-run."
      return 1
      ;;
  esac
  node_version="$(resolve_node_lts)"
  [ -n "$node_version" ] || node_version="$NODE_LTS_FALLBACK"
  NODE_DIR="$INSTALL_DIR/.node"
  mkdir -p "$NODE_DIR"
  url="https://nodejs.org/dist/$node_version/node-$node_version-linux-$node_arch.tar.xz"
  tmp_tar="$NODE_DIR/node-download.tar.xz"
  say "Downloading Node.js $node_version ($node_arch) from nodejs.org ..."
  if ! fetch_url "$url" "$tmp_tar"; then
    rm -f "$tmp_tar" 2>/dev/null || true
    warn "downloading $url failed; install Node 22+ manually from https://nodejs.org and re-run."
    return 1
  fi
  if ! tar -xJf "$tmp_tar" -C "$NODE_DIR" --strip-components=1; then
    rm -f "$tmp_tar" 2>/dev/null || true
    warn "extracting Node from $tmp_tar failed; install Node 22+ manually from https://nodejs.org and re-run."
    return 1
  fi
  rm -f "$tmp_tar" 2>/dev/null || true
  if [ -x "$NODE_DIR/bin/node" ]; then
    export PATH="$NODE_DIR/bin:$PATH"
    NODE_BIN="$NODE_DIR/bin/node"
    return 0
  fi
  warn "Node install did not produce $NODE_DIR/bin/node; install Node 22+ manually from https://nodejs.org and re-run."
  return 1
}

node_check() {
  local ver major
  if command -v node >/dev/null 2>&1; then
    ver="$(node --version 2>/dev/null || true)"
    major="${ver#v}"
    major="${major%%.*}"
    case "$major" in
      ''|*[!0-9]*) return 1 ;;
    esac
    if [ "" -ge 22 ]; then
      NODE_BIN="$(command -v node)"
      NODE_VERSION="$ver"
      return 0
    fi
    warn "system node () is older than 22; installing a user-local Node instead."
    return 1
  fi
  return 1
}

say "Checking Node.js (>=22 required for hyperframes rendering) ..."
if node_check; then
  say "Using Node.js ${NODE_VERSION} ($NODE_BIN)"
else
  if install_node_local; then
    NODE_VERSION="$("$NODE_BIN" --version 2>/dev/null || true)"
    say "Node.js ${NODE_VERSION} installed at $NODE_DIR/bin (user-local, no sudo)."
    say "Add it to your shell profile (append to ~/.bashrc or ~/.zshrc):"
    say "  export PATH=\"$NODE_DIR/bin:\$PATH\""
  else
    warn "Node.js 22+ is required for motion-graphics (hyperframes) rendering; the MCP server itself works without it."
  fi
fi

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

# ---- Hyperframes (npm dependencies) ---------------------------------------
# The render pipeline pins hyperframes@0.7.65 in package.json; the Python
# render code resolves $INSTALL_DIR/node_modules/.bin/hyperframes (with an
# npx fallback). Uses system npm when present, or the user-local Node above.
HYPERFRAMES_BIN="$INSTALL_DIR/node_modules/.bin/hyperframes"
if command -v npm >/dev/null 2>&1; then
  say "Installing npm dependencies (hyperframes + remotion pinned in package.json) ..."
  if (cd "$INSTALL_DIR" && npm install --no-audit --no-fund); then
    :
  else
    warn "npm install failed. Retry with:  cd \"$INSTALL_DIR\" && npm install --no-audit --no-fund"
  fi
  if [ -f "$HYPERFRAMES_BIN" ]; then
    say "hyperframes ready at $HYPERFRAMES_BIN"
    if ! "$HYPERFRAMES_BIN" --version >/dev/null 2>&1; then
      warn "node_modules/.bin/hyperframes exists but could not run (is Node 22+ active?)."
      warn "Rendering will fall back to 'npx hyperframes' (network resolution + version drift risk)."
    fi
  else
    warn "node_modules/.bin/hyperframes was not created by npm install."
    warn "Rendering will fall back to 'npx hyperframes' (network resolution + version drift risk)."
  fi
else
  warn "npm was not found on PATH; skipping npm install (hyperframes rendering unavailable)."
  warn "Install Node.js 22+ (see above), then run:  cd \"$INSTALL_DIR\" && npm install --no-audit --no-fund"
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
EOF

# ---- Runtime readiness -----------------------------------------------------
# Render-pipeline dependencies. Missing ones never fail the install: the MCP
# server works without them, and the table below tells the user what to do.
FFMPEG_BIN="$(command -v ffmpeg 2>/dev/null || true)"
MELT_BIN="$(command -v melt 2>/dev/null || true)"
CHROME_BIN=""

pkg_hint() {
  # Exact install commands for ffmpeg/melt on the current OS.
  if [ "$(uname -s)" = "Darwin" ]; then
    printf 'brew install ffmpeg melt'
  elif command -v apt-get >/dev/null 2>&1; then
    printf 'sudo apt install ffmpeg melt'
  elif command -v dnf >/dev/null 2>&1; then
    printf 'sudo dnf install ffmpeg-free mlt'
  elif command -v pacman >/dev/null 2>&1; then
    printf 'sudo pacman -S ffmpeg mlt'
  else
    printf 'install ffmpeg and melt from your package manager'
  fi
}

probe_chrome() {
  # Chrome/Chromium reachable by puppeteer-core (hyperframes' renderer).
  local c d
  for c in google-chrome google-chrome-stable chromium chromium-browser; do
    if command -v "$c" >/dev/null 2>&1; then
      CHROME_BIN="$(command -v "$c")"
      return 0
    fi
  done
  for c in /opt/google/chrome/chrome /usr/bin/google-chrome /usr/bin/google-chrome-stable \
           /usr/bin/chromium /usr/bin/chromium-browser; do
    if [ -x "$c" ]; then
      CHROME_BIN="$c"
      return 0
    fi
  done
  for d in "$HOME"/.cache/ms-playwright/*/chrome-linux/chrome \
           "$HOME"/.cache/ms-playwright/*/chromium*/chrome-linux/chrome \
           "$HOME"/.cache/puppeteer/chrome/*/chrome-linux/chrome; do
    if [ -x "$d" ]; then
      CHROME_BIN="$d"
      return 0
    fi
  done
  return 1
}
probe_chrome || true

say "Checking render runtime (ffmpeg / melt / chrome) ..."
[ -n "$FFMPEG_BIN" ] && say "  ffmpeg : $FFMPEG_BIN"
[ -n "$MELT_BIN" ] && say "  melt   : $MELT_BIN"
[ -n "$CHROME_BIN" ] && say "  chrome : $CHROME_BIN"

# Readiness table: each component -> READY (with path) or MANUAL STEPS (with hint).
if [ -n "$FFMPEG_BIN" ]; then
  FF_STATUS="READY"; FF_DETAIL="$FFMPEG_BIN"
else
  FF_STATUS="MANUAL STEPS"; FF_DETAIL="$(pkg_hint)"
fi
if [ -n "$MELT_BIN" ]; then
  MELT_STATUS="READY"; MELT_DETAIL="$MELT_BIN"
else
  MELT_STATUS="MANUAL STEPS"; MELT_DETAIL="$(pkg_hint)"
fi
if [ -n "$NODE_BIN" ]; then
  NODE_STATUS="READY"
  NODE_DETAIL="${NODE_VERSION:-unknown}"
  NODE_MAJOR="${NODE_VERSION#v}"
  NODE_MAJOR="${NODE_MAJOR%%.*}"
  case "$NODE_MAJOR" in
    1[89]|2[01]) NODE_DETAIL="$NODE_DETAIL (hyperframes 0.7.65 prefers Node >=22)" ;;
  esac
else
  NODE_STATUS="MANUAL STEPS"
  if [ "$(uname -s)" = "Darwin" ]; then
    NODE_DETAIL="brew install node (or https://nodejs.org)"
  else
    NODE_DETAIL="install Node 22+ from https://nodejs.org"
  fi
fi
if [ -f "$HYPERFRAMES_BIN" ]; then
  HF_STATUS="READY"; HF_DETAIL="$HYPERFRAMES_BIN"
else
  HF_STATUS="MANUAL STEPS"
  HF_DETAIL="cd \"$INSTALL_DIR\" && npm install --no-audit --no-fund (render falls back to npx hyperframes)"
fi
if [ -n "$CHROME_BIN" ]; then
  CHROME_STATUS="READY"; CHROME_DETAIL="$CHROME_BIN"
else
  CHROME_STATUS="MANUAL STEPS"; CHROME_DETAIL="npx @puppeteer/browsers install chrome"
fi

say ""
say "Runtime readiness (render pipeline):"
printf '  %-14s %-13s %s\n' "component" "status" "detail"
printf '  %-14s %-13s %s\n' "---------" "------" "------"
printf '  %-14s %-13s %s\n' "ffmpeg"      "$FF_STATUS"     "$FF_DETAIL"
printf '  %-14s %-13s %s\n' "melt"        "$MELT_STATUS"   "$MELT_DETAIL"
printf '  %-14s %-13s %s\n' "node"        "$NODE_STATUS"   "$NODE_DETAIL"
printf '  %-14s %-13s %s\n' "hyperframes" "$HF_STATUS"     "$HF_DETAIL"
printf '  %-14s %-13s %s\n' "chrome"      "$CHROME_STATUS" "$CHROME_DETAIL"

if [ "$FF_STATUS" != "READY" ] || [ "$MELT_STATUS" != "READY" ] \
   || [ "$NODE_STATUS" != "READY" ] || [ "$HF_STATUS" != "READY" ] \
   || [ "$CHROME_STATUS" != "READY" ]; then
  warn "one or more render dependencies need manual steps (see table above)."
  warn "The MCP server still works; rendering motion graphics needs the missing pieces."
fi

say ""
say "Done."
