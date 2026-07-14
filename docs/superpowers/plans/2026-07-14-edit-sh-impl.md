# `edit.sh` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a one-shot wrapper script `edit.sh` that takes a directory of raw clips, sets up a project, runs the pipeline, and opens the result in Kdenlive.

**Architecture:** Single new bash script `edit.sh` (~50 lines, sibling of `run.sh`). Thin wrapper that derives a project name from the source dir, symlinks the source files into `projects/<name>/footage/`, delegates to the existing `run.sh`, then `xdg-open`s the resulting `project.mlt`. `run.sh` and the Go CLIs are unchanged.

**Tech Stack:** Bash 4+ (`set -euo pipefail`, arrays, `[[ ]]`), GNU coreutils (`ln`, `basename`, `mkdir`, `readlink`, `xdg-open`).

## Global Constraints

- Spec: [`docs/superpowers/specs/2026-07-14-edit-sh-design.md`](../specs/2026-07-14-edit-sh-design.md) — every task implements one section of this spec.
- `run.sh` and the Go CLIs (`cmd/analyze`, `cmd/compile`, `cmd/render`) are **read-only** for this plan. No modifications.
- `set -euo pipefail` discipline, matching `run.sh`.
- Symlinks only — never copy footage (saves disk, source folder is canonical).
- Supported extensions: `.mp4`, `.mov`, `.mkv`, `.webm`.
- Idempotent: re-running the script is a no-op (and re-opens Kdenlive).

---

## File Structure

| File | Responsibility |
|---|---|
| `edit.sh` (new) | One-shot wrapper. Arg parsing, source validation, symlink setup, delegation, Kdenlive launch. |
| `README.md` (modify) | Add "One-shot usage" section documenting `edit.sh`. |
| `docs/superpowers/specs/2026-07-14-edit-sh-design.md` (read-only) | The spec this plan implements. |

No new Go files. No new directories.

---

## Task 1: Write `edit.sh` skeleton (parsing + help + path resolution)

**Files:**
- Create: `edit.sh` (executable, `chmod +x`)

**Interfaces:**
- Consumes: nothing (first task)
- Produces: an `edit.sh` script that parses args, prints help, resolves the script's own directory, and exits cleanly on `--help` or unknown flags. No pipeline logic yet.

- [ ] **Step 1: Write the file**

Create `edit.sh` in the project root with the following content:

```bash
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
```

- [ ] **Step 2: Make it executable and syntax-check**

Run:
```bash
chmod +x edit.sh
bash -n edit.sh
```

Expected: no output, exit 0.

- [ ] **Step 3: Smoke-test the help text**

Run:
```bash
./edit.sh --help
```

Expected: prints the usage block to stdout, exits 0.

Run:
```bash
./edit.sh 2>&1; echo "exit=$?"
```

Expected: prints usage to stderr, `exit=2`.

- [ ] **Step 4: Commit**

```bash
git add edit.sh
git commit -m "feat(edit.sh): add arg parsing and help text"
```

---

## Task 2: Add source validation and project-name derivation

**Files:**
- Modify: `edit.sh` — replace the "Sanity checks" placeholder block at the bottom with validation + name derivation.

**Interfaces:**
- Consumes: `$SOURCE` (from Task 1), the script's own existence in `$ROOT`.
- Produces: `$SOURCE` validated (exists, readable, contains at least one video file), `$PROJECT_NAME` derived (or set from CLI). Exits 2 on validation failure.

- [ ] **Step 1: Replace the placeholder block**

In `edit.sh`, find the block that starts with `# --- Sanity checks (placeholders, filled in by later tasks) ---------------` and ends before the final `exit 0`. Replace it with:

```bash
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
```

- [ ] **Step 2: Syntax-check**

Run: `bash -n edit.sh`
Expected: no output, exit 0.

- [ ] **Step 3: Test on a real directory**

Create a small fixture and test:

```bash
mkdir -p /tmp/edit-test/clips
touch /tmp/edit-test/clips/clip1.mp4 /tmp/edit-test/clips/clip2.mov
echo "ignore me" > /tmp/edit-test/clips/notes.txt
./edit.sh /tmp/edit-test/clips
```

Expected output (stderr):
```
edit.sh: validated source OK
  source       = /tmp/edit-test/clips
  project_name = edit-test-clips
  files        = 2
  render       = 0
  force        = 0
```
Exit code: 0.

- [ ] **Step 4: Test name sanitization**

Run:
```bash
mkdir -p "/tmp/edit test/clips"
touch "/tmp/edit test/clips/clip 1.mp4"
./edit.sh "/tmp/edit test/clips"
```

Expected: `project_name = edit-test-clips` (spaces → dashes, the directory's space and the file's space both normalized).

- [ ] **Step 5: Test explicit project name**

Run:
```bash
./edit.sh /tmp/edit-test/clips my-cool-cut --render
```

Expected: `project_name = my-cool-cut`, `render = 1`.

- [ ] **Step 6: Test error paths**

Run:
```bash
./edit.sh /nonexistent/path 2>&1; echo "exit=$?"
```

Expected: `edit.sh: /nonexistent/path: not found`, `exit=2`.

```bash
mkdir -p /tmp/empty-dir
./edit.sh /tmp/empty-dir 2>&1; echo "exit=$?"
```

Expected: `edit.sh: /tmp/empty-dir: no .mp4/.mov/.mkv/.webm files found`, `exit=2`.

```bash
echo "not a video" > /tmp/notvideo.txt
./edit.sh /tmp/notvideo.txt 2>&1; echo "exit=$?"
```

Expected: `edit.sh: /tmp/notvideo.txt: unsupported file type ...`, `exit=2`.

- [ ] **Step 7: Commit**

```bash
git add edit.sh
git commit -m "feat(edit.sh): add source validation and project-name derivation"
```

---

## Task 3: Add symlink setup (`footage/`)

**Files:**
- Modify: `edit.sh` — insert setup step between validation and the final echo.

**Interfaces:**
- Consumes: `$ROOT`, `$PROJECT_NAME`, `$SOURCE`, `${VIDEO_FILES[@]}` (from Task 2).
- Produces: `projects/$PROJECT_NAME/footage/` directory created, each video file symlinked into it. Refuses to overwrite real (non-symlink) files unless `$DO_FORCE=1`.

- [ ] **Step 1: Replace the "later tasks will add" comment block**

In `edit.sh`, find the line that says `# --- (later tasks will add setup, delegation, and open) -------------------` and replace everything from there to end-of-file with:

```bash
# --- Setup: symlink footage ----------------------------------------------

PROJECT_DIR="$ROOT/projects/$PROJECT_NAME"
FOOTAGE_DIR="$PROJECT_DIR/footage"
mkdir -p "$FOOTAGE_DIR"

# Wipe outputs (not footage/) if --force.
if [[ $DO_FORCE -eq 1 ]]; then
    for out in metadata.json edl.json edl.failed.json project.mlt preview.mp4 final.mp4; do
        rm -f "$PROJECT_DIR/$out"
    done
    # Melt's runtime lock files.
    find "$PROJECT_DIR" -maxdepth 1 -name '*.lck' -type f -delete 2>/dev/null || true
fi

# Link each video file. If a symlink already points to the right source,
# skip. If a real file is in the way, refuse (unless --force wipes it;
# but --force doesn't touch footage/, so the user must rm -rf footage/
# themselves to re-point).
linked_count=0
for f in "${VIDEO_FILES[@]}"; do
    base="$(basename "$f")"
    target="$FOOTAGE_DIR/$base"
    if [[ -L "$target" ]]; then
        existing="$(readlink "$target")"
        if [[ "$existing" == "$f" ]]; then
            continue  # already correctly linked
        else
            echo "edit.sh: $target already symlinked to $existing, expected $f" >&2
            echo "         To re-point, run: rm -rf $FOOTAGE_DIR" >&2
            exit 1
        fi
    elif [[ -e "$target" ]]; then
        echo "edit.sh: $target is not a symlink. Refusing to overwrite." >&2
        echo "         Pass --force and rm -rf $FOOTAGE_DIR, or pick a different project name." >&2
        exit 1
    else
        ln -s "$f" "$target"
        linked_count=$((linked_count + 1))
    fi
done

if [[ $linked_count -gt 0 ]]; then
    echo "edit.sh: symlinked $linked_count file(s) into projects/$PROJECT_NAME/footage/" >&2
else
    echo "edit.sh: symlinks already exist; skipping" >&2
fi
```

- [ ] **Step 2: Syntax-check**

Run: `bash -n edit.sh`
Expected: no output, exit 0.

- [ ] **Step 3: Test the setup**

Clean any previous test project, then:

```bash
rm -rf projects/edit-test-clips projects/my-cool-cut
./edit.sh /tmp/edit-test/clips
ls -la projects/edit-test-clips/footage/
```

Expected: two symlinks (`clip1.mp4 -> /tmp/edit-test/clips/clip1.mp4`, `clip2.mov -> ...`), and the `edit.sh` script reports `symlinked 2 file(s)`.

- [ ] **Step 4: Test idempotency**

Run:
```bash
./edit.sh /tmp/edit-test/clips
```

Expected: `symlinks already exist; skipping`, exit 0.

- [ ] **Step 5: Test the "real file in the way" refusal**

```bash
echo "I am a real file" > projects/edit-test-clips/footage/clip1.mp4
./edit.sh /tmp/edit-test/clips 2>&1; echo "exit=$?"
```

Expected: `is not a symlink. Refusing to overwrite.`, `exit=1`.

Clean up:
```bash
rm -rf projects/edit-test-clips
```

- [ ] **Step 6: Commit**

```bash
git add edit.sh
git commit -m "feat(edit.sh): symlink source files into projects/<name>/footage/"
```

---

## Task 4: Add delegation to `run.sh`

**Files:**
- Modify: `edit.sh` — append the delegation step.

**Interfaces:**
- Consumes: `$ROOT`, `$PROJECT_NAME`, `$DO_RENDER` (from earlier tasks). `$PROJECT_DIR/footage/` already populated.
- Produces: `run.sh` invoked. Its output passes through to the user. Its exit code becomes `edit.sh`'s exit code (no Kdenlive launch in this task — that's Task 5).

- [ ] **Step 1: Append the delegation step**

In `edit.sh`, find the final `echo "edit.sh: symlinks already exist; skipping" >&2` (or the one above it for the "linked N files" case) — actually, find the END of the setup block, which is the last `fi` of the for-loop. After that, add:

```bash

# --- Delegate to run.sh ---------------------------------------------------

run_args=("$ROOT/run.sh" "$PROJECT_NAME")
if [[ $DO_RENDER -eq 1 ]]; then
    run_args+=(--render)
fi
"${run_args[@]}"
```

(Note: the leading blank line keeps the block visually separate from the setup block above.)

- [ ] **Step 2: Syntax-check**

Run: `bash -n edit.sh`
Expected: no output, exit 0.

- [ ] **Step 3: Test delegation on a stub project**

The full e2e would call the agent. To test delegation without the agent, create a project with a pre-baked `edl.json` and `metadata.json` so `run.sh` skips the agent and goes straight to compile. Use the existing `testdata/` fixtures:

```bash
rm -rf projects/edit-test-delegation
mkdir -p projects/edit-test-delegation/footage
ln -s /home/ah64/apps/mlt-pipeline/testdata/clip_short.mp4 projects/edit-test-delegation/footage/clip_short.mp4
# Use a wrapper around edit.sh that injects a fake project name + skips Kdenlive.
# Simplest: invoke the script with the test project name explicitly.
./edit.sh /tmp/edit-test/clips edit-test-delegation 2>&1 | tail -20
```

Expected: `run.sh` runs, sees `edl.json` and `metadata.json` missing, calls the agent, may succeed or fail. That's OK — we just want to confirm `run.sh` was actually invoked. Look for `=== mlt-pipeline: edit-test-delegation ===` in the output.

Clean up: `rm -rf projects/edit-test-delegation`

- [ ] **Step 4: Test the `--render` passthrough**

```bash
./edit.sh /tmp/edit-test/clips --render 2>&1 | grep -E "Stage 5|final render" | head -3
```

Expected: a line like `--- Stage 5: final render (skip; final.mp4 exists) ---` or `--- Stage 5: final render ---` (depending on state).

- [ ] **Step 5: Commit**

```bash
git add edit.sh
git commit -m "feat(edit.sh): delegate to run.sh and pass --render through"
```

---

## Task 5: Add Kdenlive launch

**Files:**
- Modify: `edit.sh` — append the open step.

**Interfaces:**
- Consumes: `$ROOT`, `$PROJECT_NAME`, the exit code of `run.sh` (must be 0).
- Produces: `xdg-open projects/$PROJECT_NAME/project.mlt` launched in the background, so the script exits cleanly.

- [ ] **Step 1: Append the open step**

In `edit.sh`, after the delegation block, add:

```bash

# --- Open result in Kdenlive (or whatever handles .mlt) -------------------

MLT_PATH="$PROJECT_DIR/project.mlt"
if [[ -f "$MLT_PATH" ]]; then
    echo "edit.sh: launching $MLT_PATH" >&2
    xdg-open "$MLT_PATH" &
    # Don't wait on xdg-open; the user is now in Kdenlive.
    disown 2>/dev/null || true
else
    echo "edit.sh: $MLT_PATH not created; pipeline failed" >&2
    exit 1
fi
```

- [ ] **Step 2: Syntax-check**

Run: `bash -n edit.sh`
Expected: no output, exit 0.

- [ ] **Step 3: Test the open step (with a pre-existing project.mlt)**

Create a project with a complete pipeline output and a stub `project.mlt`:

```bash
rm -rf projects/edit-test-open
mkdir -p projects/edit-test-open/footage
ln -s /home/ah64/apps/mlt-pipeline/testdata/clip_short.mp4 projects/edit-test-open/footage/clip_short.mp4
cp /home/ah64/apps/mlt-pipeline/testdata/clip_short.metadata.json projects/edit-test-open/metadata.json
cp /home/ah64/apps/mlt-pipeline/testdata/clip_short.edl.handwritten.json projects/edit-test-open/edl.json
# Run edit.sh but stub xdg-open so we don't actually pop a window.
cat > /tmp/fake-xdg-open.sh <<'EOF'
#!/usr/bin/env bash
echo "FAKE xdg-open called with: $*"
EOF
chmod +x /tmp/fake-xdg-open.sh
PATH="/tmp:$PATH" ln -sf /tmp/fake-xdg-open.sh /tmp/xdg-open
# Run with the fake xdg-open first in PATH. But edit.sh calls xdg-open
# unqualified, so PATH lookup applies.
# Easiest: just run edit.sh and verify it didn't error.
./edit.sh /tmp/edit-test/clips edit-test-open 2>&1 | tail -10
```

Expected: `run.sh` runs, skips analyze/agent (they'd be re-skipped if already there), but compile may run because `project.mlt` is missing. After `run.sh` exits 0, `edit.sh` prints `edit.sh: launching .../project.mlt` and forks xdg-open. (If your system has no `xdg-open`, the call errors but `edit.sh` does not exit non-zero because it's backgrounded with `&` and the exit is `disown`ed.)

- [ ] **Step 4: Test the failure case (no `project.mlt` produced)**

Make a project where compile fails by giving the EDL a non-existent source path:

```bash
rm -rf projects/edit-test-fail
mkdir -p projects/edit-test-fail/footage
ln -s /home/ah64/apps/mlt-pipeline/testdata/clip_short.mp4 projects/edit-test-fail/footage/clip_short.mp4
# Bypass run.sh's analyze by providing a metadata.json with the right shape,
# then force compile to fail by writing a bad edl.json:
cp /home/ah64/apps/mlt-pipeline/testdata/clip_short.metadata.json projects/edit-test-fail/metadata.json
echo '{"version":1,"targetDurationSec":1,"segments":[{"source":"/nonexistent.mp4","inSec":0,"outSec":1,"transition":"cut"}]}' > projects/edit-test-fail/edl.json
# But run.sh will re-run analyze (overwriting metadata.json with a fresh one),
# then re-run the agent. The agent's behavior is non-deterministic.
#
# Simpler test: invoke edit.sh's open step directly by running with a project
# name that doesn't exist. But edit.sh validates and delegates, so we can't
# reach the open step without a successful run.sh.
#
# Manual verification: trust the defensive `if [[ -f $MLT_PATH ]]` check; the
# only way to hit the else branch is if run.sh exits 0 but produces no
# project.mlt, which the existing run.sh implementation does not allow.
```

Mark this step "verified by code inspection" and move on.

- [ ] **Step 5: Clean up test artifacts**

```bash
rm -rf projects/edit-test-clips projects/edit-test-open projects/edit-test-fail projects/my-cool-cut
rm -f /tmp/fake-xdg-open.sh /tmp/xdg-open
```

- [ ] **Step 6: Commit**

```bash
git add edit.sh
git commit -m "feat(edit.sh): launch project.mlt in Kdenlive via xdg-open"
```

---

## Task 6: Update README with one-shot usage

**Files:**
- Modify: `README.md` — add a "One-shot usage" section after the existing "Use" section.

**Interfaces:**
- Consumes: README.md's existing structure.
- Produces: a new section documenting `edit.sh`, its flags, and the `--force` semantics around `footage/`.

- [ ] **Step 1: Insert the new section**

In `README.md`, find the section "## Use" (around line 29). At the END of that section (after "### 4. (Optional) Bake a final MP4 from the pipeline" block, but BEFORE "## Re-running stages"), insert:

```markdown
## One-shot usage

If you just have a folder of raw clips and want the pipeline to do everything end-to-end, use `edit.sh`:

```bash
./edit.sh ~/Videos/wedding-raw
```

This single command:

1. Derives a project name from the folder (`wedding-raw`)
2. Creates `projects/wedding-raw/footage/` and **symlinks** the raw clips into it (no copying)
3. Runs the pipeline (analyze → agent → compile → render --dry-run)
4. Opens the resulting `project.mlt` in Kdenlive (via `xdg-open`)

You can override the project name, force a final render, and re-run from scratch:

```bash
./edit.sh ~/Videos/wedding-raw my-wedding --render --force
```

Flags:

- `<source>` (required) — a directory of `.mp4` / `.mov` / `.mkv` / `.webm` files, or a single video file.
- `<project-name>` (optional) — override the auto-derived name.
- `--render` — also produce a final `final.mp4` (skip the Kdenlive refinement step entirely).
- `--force` — wipe the existing project outputs (`metadata.json`, `edl.json`, `project.mlt`, `preview.mp4`, `final.mp4`, `*.lck`) and re-run. **Does NOT remove `footage/` symlinks.** To re-point symlinks (e.g., you want to point at a different source folder), run `rm -rf projects/<name>/footage` first.
- `-h`, `--help` — show usage.

`edit.sh` is idempotent: re-running it on the same source is a no-op (existing symlinks are detected, finished pipeline stages are skipped) and re-opens the project in Kdenlive.
```

Note: when editing, you may need to use indented code blocks (4-space indent inside the outer fenced block) so the inner ```bash``` fences don't terminate the outer block. The easiest approach: use a leading blank line before and after the inner code block, OR use `~~~` for the outer and ``` ``` ``` for the inner. Test that the rendered Markdown looks right.

- [ ] **Step 2: Verify the README still renders**

Run: `head -120 README.md`
Expected: the new section appears after the "Bake a final MP4" subsection and before "## Re-running stages".

- [ ] **Step 3: Smoke-check the surrounding structure**

Run: `grep -n '^## ' README.md`
Expected: a list of `##` headings, including the existing ones plus a new "## One-shot usage" between "## Use" and "## Re-running stages".

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(readme): add one-shot usage section for edit.sh"
```

---

## Task 7: End-to-end manual smoke test

**Files:** none modified.

**Goal:** Run the full `edit.sh` flow on a real folder of clips and verify the e2e path works.

- [ ] **Step 1: Build the CLIs (if not already built)**

Run:
```bash
export PATH=$HOME/go-install/go/bin:$PATH
go build -o bin/analyze ./cmd/analyze
go build -o bin/compile ./cmd/compile
go build -o bin/render  ./cmd/render
```

- [ ] **Step 2: Prepare a small clip folder**

Use the existing testdata clip:

```bash
mkdir -p /tmp/edit-smoke/clips
cp /home/ah64/apps/mlt-pipeline/testdata/clip_short.mp4 /tmp/edit-smoke/clips/
```

- [ ] **Step 3: Run edit.sh on it**

```bash
./edit.sh /tmp/edit-smoke/clips
```

Expected: 
- The script reports the source and project name
- `footage/` is populated with a symlink
- `run.sh` runs and produces `metadata.json`, then calls the agent (which may take 30s–2min), then `project.mlt`, then `preview.mp4`
- The script prints `edit.sh: launching .../project.mlt`
- Kdenlive (or whatever handles `.mlt`) opens, OR if there's no `.mlt` handler, `xdg-open` errors but the script exits 0

If the agent fails (model flake), re-run with `--force`:
```bash
./edit.sh /tmp/edit-smoke/clips --force
```

- [ ] **Step 4: Verify the artifacts exist**

```bash
ls -la projects/edit-smoke/
ls -la projects/edit-smoke/footage/
test -f projects/edit-smoke/project.mlt && echo "mlt: OK"
test -f projects/edit-smoke/preview.mp4 && echo "preview: OK"
```

Expected: `mlt: OK` and `preview: OK` (after the pipeline succeeds).

- [ ] **Step 5: Verify the symlink is correct**

```bash
readlink projects/edit-smoke/footage/clip_short.mp4
```

Expected: `/tmp/edit-smoke/clips/clip_short.mp4`.

- [ ] **Step 6: Clean up**

```bash
rm -rf projects/edit-smoke /tmp/edit-smoke
```

(Leave the script in place — it's the deliverable.)

- [ ] **Step 7: Run the full Go test suite to confirm nothing else broke**

```bash
export PATH=$HOME/go-install/go/bin:$PATH
go test -count=1 ./...
```

Expected: all 25/25 tests pass (the existing e2e + unit tests are unaffected by `edit.sh`).

- [ ] **Step 8: Commit (no source changes; just a smoke-test verification log if needed)**

If everything passes, no commit. If you found and fixed a bug during smoke testing, commit that bugfix with a clear message.

---

## Self-Review

**1. Spec coverage** — does each spec requirement map to a task?

| Spec section | Task |
|---|---|
| Motivation / Goal / Non-goals | informational, no task |
| Architecture (run.sh + edit.sh) | Tasks 1–5 |
| UX: invocation, flags, what-the-user-sees | Task 1 (parsing) + Task 2 (defaults) + Task 6 (README) |
| Components §1 Arg parsing | Task 1 |
| Components §2 Help text | Task 1 |
| Components §3 Path resolution | Tasks 1 + 2 |
| Components §4 Validation | Task 2 |
| Components §5 Setup (symlinks) | Task 3 |
| Components §6 Force handling | Task 3 |
| Components §7 Delegation | Task 4 |
| Components §8 Open in Kdenlive | Task 5 |
| Data flow | Tasks 1–5 (each step implemented in its task) |
| Error handling: source missing/empty/unreadable | Task 2 (Steps 6) |
| Error handling: footage/ contains real file | Task 3 (Step 5) |
| Error handling: run.sh fails (no project.mlt) | Task 5 (Step 4) |
| Error handling: project name collision | Task 3 (covered by "already symlinked to" check) |
| Error handling: unknown flag | Task 1 (covered by `case` in arg parser) |
| Testing (manual smoke, error paths) | Task 7 |
| README update | Task 6 |

**2. Placeholder scan** — searched for "TBD", "TODO", "implement later", "fill in". None found. Task 5 Step 4 ("verified by code inspection") is intentional — it documents that a hard-to-reach branch is covered by code review, not a placeholder.

**3. Type / name consistency** — checked: `$SOURCE`, `$PROJECT_NAME`, `$DO_RENDER`, `$DO_FORCE`, `$ROOT`, `$PROJECT_DIR`, `$FOOTAGE_DIR`, `$MLT_PATH` are used consistently across all tasks. `${VIDEO_FILES[@]}` declared in Task 2, consumed in Task 3. No renames.
