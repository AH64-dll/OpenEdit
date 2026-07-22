# mlt-pipeline

Autonomous video-editing pipeline. Raw footage → Kdenlive-editable `project.mlt` via an OpenCode-driven agent.

## Design

- **Spec:** [`docs/superpowers/specs/2026-07-13-mlt-pipeline-design.md`](docs/superpowers/specs/2026-07-13-mlt-pipeline-design.md)
- **Plan:** [`docs/superpowers/plans/2026-07-13-mlt-pipeline-impl.md`](docs/superpowers/plans/2026-07-13-mlt-pipeline-impl.md)
- **Architecture boundary:** [`docs/architecture-boundary.md`](docs/architecture-boundary.md)

## Architecture status

The supported production path is the Go pipeline in `cmd/`, `internal/`,
`run.sh`, and `edit.sh`.

`open_edit/` is an experimental prototype for a larger AI-native editor. It is
kept in this repository for exploration, but production scripts do not depend on
it. See [`open_edit/README.md`](open_edit/README.md) before installing or using
that package.

## Setup

Production Go pipeline:

1. Install Go 1.22+, `ffmpeg`/`ffprobe`, `melt`, `opencode`, and Kdenlive.
2. Build the Go CLIs with the commands in [Build](#build).

Experimental `open_edit/` prototype only:

1. `pip install -e open_edit/` (Python deps)
2. `npm install` at the repo root — installs `hyperframes@0.7.65` for prototype
   overlay experiments.

## Dependencies

- Go 1.22+
- `ffmpeg` / `ffprobe` (with libass for completeness — not strictly required for v1)
- `melt` 7.x (MLT framework command-line renderer)
- `opencode` Go binary, 1.17+ — https://github.com/sandonair/opencode or the upstream
- `nice` (standard on Linux/macOS)
- Kdenlive 26.x for the human-review step (open `project.mlt` after the agent runs)

## Build

```bash
go build -o bin/analyze ./cmd/analyze
go build -o bin/compile ./cmd/compile
go build -o bin/render  ./cmd/render
```

Or use the test-driven build: `go test ./...` builds and runs every test.

## Use

### 1. Set up a project

```bash
mkdir -p projects/my-clip/footage
cp /path/to/raw/*.mp4 projects/my-clip/footage/
```

### 2. Run the pipeline

```bash
./run.sh my-clip
```

The driver:
1. Runs `analyze` → `projects/my-clip/metadata.json`
2. Invokes OpenCode with `prompts/edl_writer.md` → agent writes `edl.json`
3. Runs `compile` → `projects/my-clip/project.mlt`
4. Runs `render --dry-run` → `projects/my-clip/preview.mp4`

By default, final `render` is skipped (use `--render` to enable). The driver's output is a `project.mlt` you open in Kdenlive.

### 3. Open in Kdenlive

```bash
xdg-open projects/my-clip/project.mlt
# or just: open it from Kdenlive's File menu
```

Kdenlive opens it as an "Untitled" project. Refine the cut, save as `.kdenlive` if you want a full project, or render to MP4 from Kdenlive.

### 4. (Optional) Bake a final MP4 from the pipeline

```bash
./run.sh my-clip --render
```

This skips Kdenlive and runs `melt` directly to `projects/my-clip/final.mp4`.

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

## Re-running stages

`run.sh` is idempotent. To re-run from scratch:

```bash
rm projects/my-clip/{metadata.json,edl.json,project.mlt,preview.mp4,final.mp4}
./run.sh my-clip
```

Or with one flag:

```bash
./run.sh my-clip --force
```

## Testing

```bash
go test ./...                                    # all unit + e2e tests
go test -tags=agent_canary ./test/...            # agent canary (requires opencode + model)
```

## Project layout

```
mlt-pipeline/
├── cmd/                # three CLI entry points
├── internal/           # metadata, edl, mlt libraries
├── schema/             # JSON Schema for edl.json
├── testdata/           # synthetic fixtures
├── prompts/            # system prompt for the agent
├── test/               # e2e + agent canary
├── projects/           # working directories, one per user project (gitignored)
├── run.sh              # the driver
└── docs/               # spec + plan
```

## Limits (v1)

- `transition: "dissolve"` is not supported (use `cut` or `fade`).
- Single-tractor timeline (no nested tracks).
- No captions / subtitles.
- No music / voiceover generation.
- Footage must already be on disk; no remote sources.
- Minimal MLT only — Kdenlive opens the file as "Untitled." For a full `.kdenlive` project, save the file in Kdenlive after opening.
