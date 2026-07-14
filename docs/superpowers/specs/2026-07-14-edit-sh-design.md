# `edit.sh` — One-Shot Wrapper for the mlt-pipeline

**Status:** design
**Date:** 2026-07-14
**Author:** OpenCode (brainstorming session with user)
**Parent project:** [mlt-pipeline design](./2026-07-13-mlt-pipeline-design.md)

## Motivation

The current `run.sh` requires the user to manually:

1. `mkdir -p projects/<name>/footage`
2. Copy raw clips into `footage/`
3. Run `./run.sh <name>`
4. Open `projects/<name>/project.mlt` in Kdenlive manually

That's four separate steps for the most common case ("I have a folder of raw clips, give me a first cut"). The user wants one command that does all of it.

## Goal

```bash
./edit.sh ~/Videos/wedding-raw
```

…sets up the project, runs the pipeline, and opens the result in Kdenlive. That's the entire interface.

## Non-goals

- GUI launcher / file-manager integration / TUI. Out of scope; a CLI command is what the user wants.
- Changing `run.sh` or any of the Go CLIs. `run.sh` keeps its job; `edit.sh` is a thin wrapper.
- Watching a folder for new clips. One-shot only.
- Editing the Kdenlive timeline from the command line. Kdenlive is the human-refinement step; the pipeline produces a starting point.

## Architecture

Two bash scripts, composable, each with a single job:

- **`run.sh`** (existing, unchanged) — orchestrates the four pipeline stages (analyze → agent → compile → render) for an *existing* project under `projects/<name>/`. Idempotent: skips stages whose output already exists.
- **`edit.sh`** (new) — takes a directory of raw clips, sets up a project under `projects/<name>/`, calls `run.sh`, then opens the result in Kdenlive.

```
$ ./edit.sh ~/Videos/wedding-raw
                              ┌──────────────────────────┐
                              │ edit.sh (new, ~50 lines) │
                              └──────────────────────────┘
                                       │       │        │
              1. derive name from dir  │       │        │  5. xdg-open
                                       ▼       ▼        ▼
              2. mkdir projects/<name>/  ┌──────────┐  ┌─────────────┐
              3. ln -s clips into        │ run.sh   │  │ Kdenlive    │
                  projects/<name>/       │(existing)│  │             │
                  footage/               └──────────┘  └─────────────┘
                                       │       │        │
                                       ▼       ▼        ▼
                                  analyze  agent  compile  render
```

`run.sh` is unchanged. `edit.sh` is a thin wrapper that prepares input, delegates, and opens.

## UX (user-facing surface)

### Invocation

```bash
./edit.sh <source> [<project-name>] [--render] [--force]
```

- `<source>` (required) — a directory containing raw video files, OR a single video file. Supported extensions: `.mp4`, `.mov`, `.mkv`, `.webm`. (Only the last extension is stripped when deriving the default project name; e.g., `clip.tar.gz` → `clip.tar`.)
- `<project-name>` (optional) — overrides the default name. Default is `basename <source>` with the last extension stripped. Spaces and unsafe characters in the derived name are replaced: spaces → `-`, characters outside `[A-Za-z0-9_-]` are stripped.
- `--render` — also runs the final `melt` render to produce `final.mp4` (in addition to `preview.mp4`). Passed through to `run.sh`.
- `--force` — wipe existing project outputs (`metadata.json`, `edl.json`, `edl.failed.json`, `project.mlt`, `preview.mp4`, `final.mp4`) and start over. Does NOT remove symlinks in `footage/`. To re-point symlinks, `rm -rf projects/<name>/footage` first.
- `-h`, `--help` — print usage and exit 0.

### What the user sees

First run:

```
$ ./edit.sh ~/Videos/wedding-raw
=== mlt-pipeline edit: wedding-raw ===
Source: /home/me/Videos/wedding-raw (3 files)
Project: projects/wedding-raw
  [setup]    symlinked 3 files into projects/wedding-raw/footage/
  [run]      running pipeline...

=== mlt-pipeline: wedding-raw ===
Project dir: /home/me/apps/mlt-pipeline/projects/wedding-raw

--- Stage 1: analyze ---
wrote metadata.json (3 clips, 42.5s total)

--- Stage 2: agent (opencode) ---
...

--- Stage 3: compile ---
wrote project.mlt (4 segments)

--- Stage 4: render --dry-run ---
wrote preview.mp4 (8.2s)

--- Stage 5: final render (skipped; pass --render to enable) ---

=== done ===
[open]    launching Kdenlive: projects/wedding-raw/project.mlt
```

Kdenlive pops up. The user is done.

Re-run (idempotent):

```
$ ./edit.sh ~/Videos/wedding-raw
=== mlt-pipeline edit: wedding-raw ===
Source: /home/me/Videos/wedding-raw (3 files)
Project: projects/wedding-raw
  [setup]    symlinks already exist; skipping
  [run]      running pipeline...

--- Stage 1: analyze (skip; metadata.json exists) ---
--- Stage 2: agent (skip; edl.json exists) ---
--- Stage 3: compile (skip; project.mlt exists) ---
--- Stage 4: render --dry-run (skip; preview.mp4 exists) ---
--- Stage 5: final render (skipped; pass --render to enable) ---

=== done ===
[open]    launching Kdenlive: projects/wedding-raw/project.mlt
```

The user can re-run as many times as they want. `edit.sh` is a no-op except for the Kdenlive launch (which they may want — to re-open the project after manually refining it).

## Components

### `edit.sh` — new bash script

Sibling of `run.sh`, ~50 lines. Sections:

1. **Arg parsing** — `<source>`, optional `<project-name>`, `--render`, `--force`, `-h`/`--help`. Same `set -euo pipefail` discipline as `run.sh`. Unknown flag → exit 2 with usage.
2. **Help text** — `-h`/`--help` prints usage to stdout, exit 0.
3. **Path resolution** — `ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)`. Derive `PROJECT_NAME` from `basename <source>` with extension stripped, if not given explicitly. Sanitize the name (replace spaces with `-`, strip non-`[A-Za-z0-9_-]`) so it's a safe directory name.
4. **Validation** — `<source>` must exist and be readable. If a single file is passed, the project name is the file's stem, and the project will contain a single symlink to that file.
5. **Setup** — `mkdir -p projects/$PROJECT_NAME/footage`, then for each video file in `<source>`, `ln -s` it into `footage/`. Skip files that are already correctly symlinked (idempotent). Refuse to overwrite a real (non-symlink) file in `footage/` — `--force` does NOT touch `footage/`. To re-point symlinks, `rm -rf projects/<name>/footage` first.
6. **Force handling** — if `--force`, delete `metadata.json`, `edl.json`, `edl.failed.json`, `project.mlt`, `preview.mp4`, `final.mp4`, plus any `*.lck` lock files (melt's runtime locks) from `projects/$PROJECT_NAME/`. Leave `footage/` symlinks alone.
7. **Delegation** — call `./run.sh $PROJECT_NAME` with `--render` passthrough if set. Capture exit code.
8. **Open** — if `project.mlt` exists, `xdg-open projects/$PROJECT_NAME/project.mlt &` (background, so the script exits cleanly even if Kdenlive is still loading). If `project.mlt` is missing, print error and exit non-zero (do NOT open Kdenlive on a failed project).

### `run.sh` — unchanged

### Go CLIs — unchanged

## Data flow

Step by step, when the user runs `./edit.sh ~/Videos/wedding-raw`:

```
1. edit.sh parses args
   source = /home/me/Videos/wedding-raw
   project_name = wedding-raw  (basename of source, extension stripped)
   do_force = false
   do_render = false

2. edit.sh validates source
   [[ -d /home/me/Videos/wedding-raw ]] → ok
   ls /home/me/Videos/wedding-raw/  → [clip1.mp4, clip2.mp4, clip3.mp4]
   count = 3

3. edit.sh prepares projects/wedding-raw/footage/
   mkdir -p projects/wedding-raw/footage
   for f in /home/me/Videos/wedding-raw/*.{mp4,mov,mkv,webm}:
     target = projects/wedding-raw/footage/$(basename $f)
     if [[ -L $target ]] && readlink matches: skip
     elif [[ -e $target ]] (real file): error, refuse unless --force
     else: ln -s "$f" "$target"

4. edit.sh delegates
   ./run.sh wedding-raw
   (run.sh's existing logic runs analyze → agent → compile → render --dry-run)

5. edit.sh opens result
   if [[ -f projects/wedding-raw/project.mlt ]]:
     xdg-open projects/wedding-raw/project.mlt &   # background
   else:
     echo "project.mlt not created; pipeline failed" >&2
     exit 1
```

## Error handling

| Condition | Behavior |
|---|---|
| Source doesn't exist / not readable | `edit.sh: <source>: not a directory or not readable` → exit 2 |
| Source is empty (no supported video files) | `edit.sh: <source>: no .mp4/.mov/.mkv/.webm files found` → exit 2 |
| `footage/` contains a real file (not a symlink) | `edit.sh: projects/<name>/footage/<file> is not a symlink. Refusing to overwrite. Pass --force to wipe the project and start over.` → exit 1 |
| Unknown flag | `edit.sh: unknown flag: <flag>` + usage → exit 2 |
| `run.sh` fails (agent produces no `edl.json`, etc.) | Bubbles up; `edit.sh` does NOT open Kdenlive. Exits with `run.sh`'s exit code. |
| `project.mlt` missing after `run.sh` succeeds | Defensive check (in practice `run.sh` would have exited non-zero already): `edit.sh: project.mlt not created` → exit 1 |
| `xdg-open` not available | Bubbles up as `xdg-open: command not found`; user is on a system without a desktop. Exit code is `xdg-open`'s exit code, but the project is still on disk. |
| Kdenlive not installed / not associated with `.mlt` | Out of scope. `xdg-open` delegates to whatever handles `.mlt`. The README documents that Kdenlive is required. |
| Single-file source | Detected and handled: project name = file stem, single symlink in `footage/`. |
| Permission denied writing to `projects/<name>/` | Bubbles up as `mkdir: cannot create directory` from bash. `set -e` exits with that error. |
| `--force` given, but `footage/` contains real files | `--force` only wipes outputs, not `footage/`. To re-point symlinks, `rm -rf projects/<name>/footage` first. Documented in `--help` and README. |
| Project name collision (different source dir, same name) | If the existing project's `footage/` is correctly symlinked to the same source, OK (re-run). If symlinks point to a different source, error: `edit.sh: projects/<name>/footage/<file> already symlinked to <old-source>, expected <new-source>. To re-point, run: rm -rf projects/<name>/footage` → exit 1. (Note: `--force` does not re-point symlinks — it only wipes outputs. To re-point, the user must `rm -rf footage/` first.) |

## Testing

The new functionality is a thin bash wrapper. Tests:

1. **Manual smoke test** — run `./edit.sh testdata/` (or a small fixture dir) and verify:
   - Project directory created at `projects/testdata/`
   - Symlinks in `footage/` point to the source files
   - `run.sh` runs and produces `project.mlt`
   - Kdenlive is launched (or `xdg-open` errors gracefully if no DE)

2. **Re-run test** — run `./edit.sh` a second time on the same source:
   - `edit.sh` reports "symlinks already exist; skipping"
   - `run.sh` skips all stages
   - Kdenlive is re-launched

3. **Error path tests** (manual, or a small bash test harness):
   - Source doesn't exist → exit 2 with message
   - Empty source dir → exit 2 with message
   - Existing `footage/` with real files (no `--force`) → exit 1 with refusal
   - `--force` after a successful run → outputs wiped, project re-created

4. **README update** — add a "One-shot usage" section to the README with the new command, document the `--force` semantics around `footage/`.

No new automated Go tests; the test surface is bash. A small `test/edit_test.sh` bash script could be added in a follow-up if needed.

## Open questions

None. All design decisions confirmed with the user during brainstorming.

## Implementation order

1. Write `edit.sh` (single file, ~50 lines, no Go code).
2. Manual smoke test with a real folder of clips.
3. Update README with the one-shot usage section.
4. Commit.
