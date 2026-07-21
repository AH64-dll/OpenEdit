# mlt-pipeline — Detailed Project Explanation

A complete walkthrough of how this project is structured, how its pieces connect,
and how it runs end-to-end.

---

## 1. What this project is

`mlt-pipeline` is a small, dependency-free **Go** project that turns a folder of raw
video clips into a **Kdenlive-editable `project.mlt`** file through a chain of
deterministic tools plus one AI step.

The design philosophy (from `docs/superpowers/specs/2026-07-13-mlt-pipeline-design.md`)
is the key idea that explains every decision in the codebase:

> **Everything deterministic is testable Go. The AI's only job is to read
> `metadata.json` and write `edl.json`.**

That single sentence is why the project is split the way it is. "Edit this video into
something watchable" is a fuzzy, creative task that needs a model. But "analyze a file's
resolution and duration," "validate a cut list," and "emit MLT XML" are mechanical — so
they are written as plain Go programs with unit tests. The model is sandboxed into the
one creative decision (which segments to keep and how to order them) and is given a
strict output contract plus machine-readable error hints so it can self-correct.

### The end-to-end flow

```
raw footage (.mp4/.mov/.mkv/.webm)
   │
   ▼  Stage 1: analyze   (Go binary: bin/analyze, shells to ffprobe/ffmpeg)
metadata.json            (what footage do we have? duration, size, fps, scenes)
   │
   ▼  Stage 2: agent     (opencode runs prompts/edl_writer.md)
edl.json                 (edit decision list: which slices, in what order, with what transitions)
   │
   ▼  Stage 3: compile   (Go binary: bin/compile)
project.mlt             (Kdenlive-readable MLT 7 XML timeline)
   │
   ▼  Stage 4: render --dry-run   (Go binary: bin/render, shells to melt)
preview.mp4             (fast 640x360 proxy so you can eyeball the cut)
   │
   ▼  Stage 5 (optional): render   (only with --render)
final.mp4               (full-resolution bake, or just open project.mlt in Kdenlive)
```

The project is **not** trying to be a full video editor. Its output is a `.mlt` you open
in Kdenlive and refine by hand. That keeps the scope small and the Go testable.

---

## 2. Project layout

```
mlt-pipeline/
├── cmd/                      # the three CLI entry points (compiled to bin/)
│   ├── analyze/main.go       # footage → metadata.json
│   ├── compile/main.go       # edl.json + metadata.json → project.mlt
│   └── render/main.go        # project.mlt → preview.mp4 / final.mp4 (via melt)
├── internal/                 # the reusable libraries the CLIs call
│   ├── metadata/             # types + ffprobe/ffmpeg analysis
│   ├── edl/                  # types + validation + clamping
│   └── mlt/                  # EDL → MLT XML generation
├── prompts/
│   └── edl_writer.md         # the system prompt handed to the opencode agent
├── test/                     # e2e + agent-canary tests
├── testdata/                 # synthetic fixtures (clip_short.*)
├── projects/                 # per-project working dirs (gitignored) — output lands here
├── bin/                      # compiled binaries (gitignored, built on demand)
├── run.sh                    # the 5-stage driver
├── edit.sh                   # one-shot wrapper: symlink footage → run.sh → open Kdenlive
├── go.mod                    # module mlt-pipeline, go 1.22, ZERO external Go deps
├── README.md
└── docs/superpowers/         # design specs + implementation plans
    ├── specs/                # 2026-07-13-mlt-pipeline-design.md, 2026-07-14-edit-sh-design.md
    └── plans/                # the matching implementation plans
```

**No third-party Go packages.** `go.mod` has no `require` block. All file I/O is the
standard library (`flag`, `os`, `os/exec`, `encoding/json`). The "heavy" work (probing
media, rendering video) is delegated to external command-line tools via `os/exec`:

| External tool | Used by | Purpose |
|---|---|---|
| `ffprobe` | `analyze` | read duration, width, height, fps, audio |
| `ffmpeg` | `analyze` | scene-change detection (`select='gt(scene,...)'`) |
| `melt` 7.x | `render` | turn MLT XML into MP4 |
| `opencode` | `run.sh` | run the agent that writes `edl.json` |
| `nice` | `run.sh`/`render` | lower process priority during the agent/render |
| `xdg-open` | `edit.sh` | open `project.mlt` in Kdenlive |

---

## 3. The three CLI binaries (`cmd/`)

Each is a thin `main.go` that parses flags, calls into `internal/`, and writes a file.
The real logic lives in `internal/`.

### 3.1 `analyze` — footage → `metadata.json`

Flags (`cmd/analyze/main.go:12-14`):
- `-scenes` (default `true`) — run scene detection.
- `-scene-threshold` (default `0.3`) — scene-change sensitivity, lower = more cuts.
- `-output` (default `metadata.json`).

Behavior (`cmd/analyze/main.go:17-32`):
1. Takes one or more positional file paths.
2. Calls `metadata.Analyze(paths, scenes, threshold)`.
3. Calls `metadata.Save(output, m)` → writes the JSON manifest.

Under the hood (`internal/metadata/analyzer.go`):
- `analyzeOne` runs `ffprobe -show_format -show_streams`, then parses the JSON for video
  width/height, `r_frame_rate` (split into `num/den` → fps), and an audio-stream flag.
- `detectScenes` runs `ffmpeg -vf select='gt(scene,<threshold>)',showinfo -f null -`,
  scrapes `pts_time:` lines for cut points, and turns them into `Scene` ranges. If no
  cuts are found it returns one scene spanning the whole clip.
- The manifest records **absolute file paths**.

Output shape (`metadata.json`):
```json
{
  "version": 1,
  "clips": [
    {
      "path": "/home/ah64/apps/mlt-pipeline/testdata/clip_short.mp4",
      "durationSec": 10, "width": 1920, "height": 1080,
      "fps": 30, "hasAudio": false,
      "scenes": [ {"startSec": 0, "endSec": 4}, {"startSec": 4, "endSec": 10} ]
    }
  ],
  "totalDurationSec": 10
}
```
The types live in `internal/metadata/types.go`: `Manifest`, `Clip`, `Scene`.

### 3.2 `compile` — `edl.json` + `metadata.json` → `project.mlt`

Flags (`cmd/compile/main.go:14-17`):
- `-edl` (default `edl.json`), `-metadata` (default `metadata.json`), `-output`
  (default `project.mlt`), `-no-clamp` (disable bounds clamping).

The core logic (`cmd/compile/main.go:20-53`) is a strict linear pipeline:

```go
m, _ := metadata.Load(metadataPath)   // the manifest
e, _ := edl.Load(edlPath)             // the agent's edit list
edl.Validate(e, m)                    // schema + rule checks (MUTATES e)
if !noClamp { edl.Clamp(e, m) }       // bound inSec/outSec, print warnings
out, _ := mlt.Generate(e, m)          // build the MLT XML string
os.WriteFile(output, []byte(out), 0644)
```

Order matters: **`Validate` runs before `Clamp`.** `Validate` enforces the rules and
fixes cheap things (defaults missing transitions to `cut`, defaults `targetDurationSec`).
`Clamp` only ever *trims* values that are out of range and reports each trim as a
warning (not an error). Every failure path exits 1 with a `compile:`-prefixed message.

### 3.3 `render` — `project.mlt` → MP4 (via `melt`)

Flags (`cmd/render/main.go:11-16`):
- `-mlt`, `-output`, `-dry-run` (default false), `-nice` (default 10), `-vcodec`
  (`libx264`), `-acodec` (`aac`).

Logic (`cmd/render/main.go:19-40`): builds a `melt` command. The consumer is
`avformat:<output>` and codec options are passed as separate args:
```go
args := []string{mlt, "-consumer", "avformat:"+output,
                 "vcodec="+vcodec, "acodec="+acodec}
if dryRun { args = append(args, "s=640x360", "preset=ultrafast") }
```
If `-nice > 0` the command is wrapped in `nice -n N`. Then it runs `melt`, streaming
stdout/stderr through.

- **`--dry-run`** renders a 640×360 `ultrafast` proxy — fast, for eyeballing the cut.
- Without `--dry-run` it bakes at the timeline's native profile (used by `edit.sh` only
  when `--render` is passed; `run.sh` skips the final render by default).

---

## 4. The internal packages (`internal/`)

These are the heart of the project. They are pure, tested Go — no AI, no shell.

### 4.1 `internal/metadata` — the media manifest

Types (`types.go`): `Manifest{Version, Clips[], TotalDurationSec}`, `Clip{Path,
DurationSec, Width, Height, FPS, HasAudio, Scenes[]}`, `Scene{StartSec, EndSec}`.

Functions:
- `Analyze(paths, scenes, threshold) (*Manifest, error)` — pure computation; loops clips,
  sums durations.
- `analyzeOne`, `detectScenes` — the ffprobe/ffmpeg wrappers (see §3.1).
- `Load` / `Save` — plain `encoding/json` read/write (2-space indent).

### 4.2 `internal/edl` — the Edit Decision List

This package is the **contract between the AI and the rest of the system.**

Types (`types.go`):
```go
type EDL struct {
    Version           int
    TargetDurationSec float64
    Segments          []Segment
}
type Segment struct {
    Source     string     // must match a clip path in the manifest
    InSec      float64
    OutSec     float64
    Transition Transition // "cut" | "fade"
}
```

`Validate(e *EDL, m *metadata.Manifest) error` (`validate.go:15`) — **mutates `e`
in place** and is the validation gate. It checks, in order:
- version must be 1
- at least one segment
- unknown transitions rejected (`"v1 only supports cut/fade"` — `dissolve` is explicitly
  out of scope)
- defaults empty `Transition` → `"cut"`
- `inSec < outSec`, `inSec >= 0`
- `source` must appear in the manifest
- `outSec <= clip.DurationSec`
- defaults `targetDurationSec` to the sum of segment lengths if zero

**Critical design detail:** every error string contains a `fix:` hint, e.g.
`fix: set inSec=%v outSec=%v`. This is what lets the AI agent self-correct — when
`compile` fails, the agent reads the last stderr line, applies the fix, and retries
(up to 3 times). The error messages are *machine-readable by design*, not just human
messages.

`Clamp(e, m) ([]string, error)` (`clamp.go:15`) — only bounds `inSec`/`outSec` against
each clip's real duration: floors negative `inSec` to 0, ceilings `outSec` past clip end.
Returns a list of warnings (one per adjustment) and a hard error only if a source isn't
in the manifest. The doc comment says: call `Validate` first, then `Clamp`.

### 4.3 `internal/mlt` — EDL → MLT XML

`Generate(e *edl.EDL, m *metadata.Manifest) (string, error)` (`generate.go:27`):
- Emits one `<producer>` per segment (id `producerN`, `<property name="resource">path</property>`).
- Re-checks every source exists in the manifest.
- Derives the timeline `<profile>` (width/height/fps) from `m.Clips[0]` only — a known
  limitation: mixed resolutions aren't supported in v1.
- `secToTC(s)` converts seconds → MLT timecode `HH:MM:SS.mmm`.
- Emits a single-tractor MLT 7.0.0 document: `<mlt>` → `<profile>` → one `<producer>`
  per segment → `<playlist id="video_track">` with one `<entry>` per segment (and a
  `<transition name="fade" duration="1"/>` inserted *between* segments when the later
  segment's transition is `fade`) → `<tractor id="main_tractor">` referencing the track.

Output shape (`project.mlt`):
```xml
<?xml version="1.0" encoding="utf-8"?>
<mlt version="7.0.0" title="auto_edit" producer="main_bin">
  <profile width="1920" height="1080" progressive="1"
           sample_aspect_num="1" sample_aspect_den="1"
           frame_rate_num="30" frame_rate_den="1" colorspace="709"/>
  <producer id="producer0">
    <property name="resource">footage/clip_short.mp4</property>
  </producer>
  <playlist id="video_track">
    <entry producer="producer0" in="00:00:00.000" out="00:00:04.000"/>
    <entry producer="producer1" in="00:00:04.000" out="00:00:10.000"/>
  </playlist>
  <tractor id="main_tractor">
    <track producer="video_track"/>
  </tractor>
</mlt>
```

### 4.4 How the data connects

```
metadata.Manifest (analyze)  ──┐
                                ├─→ compile:
edl.EDL (agent writes)       ──┘     edl.Load → edl.Validate(manifest) → edl.Clamp(manifest)
                                                                           │
                                                                           ▼
                                                              mlt.Generate(edl, manifest)
                                                                           │
                                                                           ▼
                                                                  project.mlt (XML)
```

- `edl.Validate` and `edl.Clamp` both build a `path → *Clip` map from the manifest to
  check source membership and bound `outSec`.
- `mlt.Generate` re-checks source membership and borrows width/height/fps from `Clips[0]`
  for the `<profile>`.
- The **manifest is the single source of truth** linking the agent's abstract `source`
  strings to real files on disk. The agent never touches MLT or ffmpeg directly.

---

## 5. The agent and its prompt (`prompts/edl_writer.md`)

This is the only non-deterministic step. `run.sh` reads this file and feeds it as the
message body to `opencode run --format json --auto` (the `--auto` flag auto-approves
tool permissions so the run is non-interactive).

The prompt (`prompts/edl_writer.md`, 34 lines) is deliberately minimal and strict:

- **Role:** read `metadata.json`, write `edl.json`, run `compile` + `render --dry-run`,
  fix errors, stop.
- **Hard prohibitions:** never run `ffmpeg`/`melt` directly; never modify footage; never
  hand-edit `project.mlt`.
- **Allowed I/O:** read `metadata.json`; write `edl.json` (and versioned retries
  `edl.v2.json`, `edl.v3.json`, `edl.failed.json` — the versioned files preserve each
  attempt so you can see what went wrong).
- **Allowed tools:** only `./compile` and `./render --dry-run`.
- **EDL schema:** the strict JSON contract from §4.2.
- **Rules:**
  1. Every `source` must appear in `metadata.json`.
  2. `0 <= inSec < outSec <= clip.durationSec`.
  3. Sum of segment lengths should approximate `targetDurationSec` (±10%).
  4. Prefer `cut`; use `fade` for time jumps/mood shifts; **`dissolve` is not in v1**.
  5. On error, **read stderr first** — the fix is in the last line (the `fix:` hints from
     `Validate`).
  6. **3 attempts total**; on exhaustion write `edl.failed.json` with a one-line reason
     and stop.

The loop closes like this: the agent writes `edl.json` → `run.sh` calls `compile` → if
`Validate`/`Clamp`/`Generate` fail, `compile` prints a `fix:`-laden error → the agent
reads it, edits `edl.json` (or writes `edl.v2.json`), retries → up to 3 times, then
gives up with `edl.failed.json`. This is why the whole system can be driven by a model
without a human in the loop: the Go side turns every mistake into a precise, actionable
instruction.

---

## 6. Orchestration scripts

### 6.1 `run.sh` — the 5-stage driver

`run.sh` is the orchestrator. It sets `set -euo pipefail`, resolves `ROOT` and
`PROJECT_DIR="$ROOT/projects/$PROJECT_NAME"`, and `cd`s into the project dir.

**Idempotency** comes from a `should_run` helper (`run.sh:39-43`): a stage runs only if
its output file does *not* already exist, unless `--force` is passed. Re-running the
script is therefore a no-op for finished stages.

| Stage | Condition | Command | Output |
|---|---|---|---|
| 1. analyze | `should_run metadata.json` | `bin/analyze --output metadata.json footage/*` | `metadata.json` |
| 2. agent | `should_run edl.json` | `nice -n 5 opencode run --format json --auto "$PROMPT_CONTENT"` | `edl.json` |
| 3. compile | `should_run project.mlt` | `bin/compile --edl edl.json --metadata metadata.json --output project.mlt` | `project.mlt` |
| 4. render (dry) | `should_run preview.mp4` | `bin/render --mlt project.mlt --output preview.mp4 --dry-run` | `preview.mp4` |
| 5. final render | only with `--render` | `bin/render --mlt project.mlt --output final.mp4` | `final.mp4` |

Notable behaviors:
- **Stage 1 fallback** (`run.sh:52-59`): if `footage/` is empty or missing, writes a
  minimal empty manifest so the driver doesn't loop forever.
- **Stage 2 failure handling** (`run.sh:76-83`): if `opencode` exits non-zero *or*
  `edl.failed.json` exists, the script prints a message and `exit 1` — stages 3+ are
  skipped. It also fails if the agent exited 0 but `edl.json` is missing.
- **Stage 5 is skipped by default** (`--no-render`); pass `--render` to bake `final.mp4`.
- Flags: `<project-name>` (required), `--force`, `--render`, `--no-render`.

At the end it prints `Open projects/<name>/project.mlt in Kdenlive to refine.`

> Practical note: in a non-interactive shell, `opencode run --auto` may stay attached
> after finishing, so the command can appear to "hang" even though all artifacts were
> produced. The artifacts on disk are the real signal of success, not the process exit.

### 6.2 `edit.sh` — the one-shot wrapper

`edit.sh` wraps the four manual steps (derive a name → create `projects/<name>/footage/`
→ copy/symlink raw clips → run the pipeline → open in Kdenlive) into a single command:

```bash
./edit.sh ~/Videos/wedding-raw            # or with overrides:
./edit.sh ~/Videos/wedding-raw my-wedding --render --force
```

What it does, in order (`edit.sh`, 216 lines):
1. **Arg parsing** (`edit.sh:42-87`): `<source>` (required dir or single file), optional
   `<project-name>`, `--render`, `--force`, `-h/--help`.
2. **Name derivation** (`edit.sh:89-116`): sanitizes the folder/file name to
   `[A-Za-z0-9_-]` (spaces → `-`).
3. **Source validation** (`edit.sh:118-147`): must exist + readable; collects
   `.mp4/.mov/.mkv/.webm` via `find ... -print0 | sort -z`; empty dir → exit 2.
4. **Setup / symlink footage** (`edit.sh:149-195`): `mkdir -p projects/<name>/footage`;
   with `--force`, wipes outputs (not `footage/` itself); symlinks each video into
   `footage/`, **skipping** already-correct symlinks (idempotent) and **refusing** if a
   real (non-symlink) file blocks the path.
5. **Delegate to `run.sh`** (`edit.sh:197-203`): builds `run.sh <name> [--render]` and
   runs it — no pipeline logic is duplicated.
6. **Open in Kdenlive** (`edit.sh:205-215`): if `project.mlt` exists, `xdg-open` it in
   the background; otherwise prints failure and exits 1.

`edit.sh` is idempotent on two levels: `run.sh`'s per-stage output checks, plus
`edit.sh`'s own "symlink already correct" check.

---

## 7. Testing strategy

Three layers, all under `test/` and `internal/*_test.go`:

**Unit tests** (pure Go, no external tools beyond ffprobe):
- `internal/metadata/loader_test.go`, `analyzer_test.go` (skips if ffprobe missing).
- `internal/edl/validate_test.go` — 10 cases: version, in≥out, negative in, out-of-range,
  unknown source, empty segments, `dissolve` rejection, `fade` acceptance, default-to-cut,
  `targetDurationSec` defaulting.
- `internal/edl/clamp_test.go` — negative-in→0, out→clip-dur, in-range no-warning,
  unknown-source error.
- `internal/mlt/generate_test.go` — valid XML, producer-per-segment count, fade-adds-a-
  transition, and a **golden byte-match** against `testdata/clip_short.expected.mlt`.
- `cmd/*/main_test.go` — CLI smoke tests (build + run each binary).

**Fixtures** (`testdata/`): `clip_short.mp4` (10s, 1920×1080@30fps, 3-color synthetic clip
with scene cuts; no audio), plus hand-authored `clip_short.metadata.json`,
`clip_short.edl.handwritten.json`, and the golden `clip_short.expected.mlt`.

**E2E test** (`test/e2e_test.go`, `TestPipelineE2E_NoLLM`): builds all three CLIs,
runs `analyze` → rewrites the fixture EDL's `source` to the absolute path `analyze`
recorded → runs `compile` → runs `render` → asserts the output has a video stream and a
duration within ±20% of the target. (Note: it renders at native profile, not 640×360,
because `melt` 7.40.0 hangs scaling 1080p→360 in this environment; it uses a process-group
kill with a 3-minute timeout.)

**Agent canary** (`test/agent_test.go`, build tag `agent_canary`): gated behind
`MLT_PIPELINE_RUN_AGENT_TESTS=1`. Runs the *full* `run.sh` (which invokes the real opencode
agent) on `projects/agent-canary/`, then asserts `edl.json` and `preview.mp4` were created.
This catches model/prompt drift and is excluded from the default `go test ./...`.

Run them with:
```bash
go test ./...                              # unit + e2e (no agent)
go test -tags=agent_canary ./test/...      # also the agent canary (needs opencode + model)
```

---

## 8. How to extend the project

A few common directions and where the code lives:

- **Add a transition type** (e.g. `dissolve`): add a `Transition` const in
  `internal/edl/types.go`, accept it in `edl.Validate` (`validate.go:37`), emit the
  matching `<transition>` in `internal/mlt/generate.go`, and update the rules in
  `prompts/edl_writer.md`.
- **Support multiple profiles / mixed resolutions:** change `mlt.Generate` to derive the
  profile per-segment or normalize inputs, instead of reading `Clips[0]` only
  (`generate.go:55-58`).
- **Add audio normalization / music / captions:** these are explicitly out-of-scope in v1
  (see the design spec's out-of-scope list) and would mean new `internal/` packages plus
  new agent instructions.

---

## 9. Known limitations & deviations from the plan

**v1 limitations:**
- `transition: "dissolve"` is not supported (use `cut` or `fade`).
- Single-tractor timeline (no nested tracks, no multi-track compositing).
- No captions/subtitles, no music/voiceover generation.
- Footage must already be on disk; no remote sources.
- Timeline profile is taken from the first clip only (mixed resolutions unsupported).
- Kdenlive opens `project.mlt` as "Untitled" — for a full `.kdenlive` project, save it
  from Kdenlive after opening.

**Where the committed code differs from the approved plan** (`docs/superpowers/plans/`):
1. The plan's `render` built the melt consumer as one arg (`avformat:<out> vcodec=...
   acodec=...`); the committed `render/main.go:19-20` uses `avformat:<out>` plus separate
   `vcodec=`/`acodec=` args.
2. The plan called for a `santhosh-tekuri/jsonschema/v5` dependency and a
   `schema/edl.schema.json`. Neither exists — EDL validation is hand-rolled in
   `edl.Validate` (no JSON-Schema, no `go.sum`).
3. The plan's `generate.go` deduped producers by source; the committed version creates
   **one producer per segment** (so a 3-segment EDL from one file yields `producer0/1/2`,
   all pointing at the same file). This matches the golden `clip_short.expected.mlt`.
4. `.superpowers/sdd/progress.md` lists the 15 implementation tasks as `pending` even
   though the work is committed — a documentation-ledger gap, not a code gap.

---

## 10. Quick start

```bash
# 1. Build the three binaries
go build -o bin/analyze ./cmd/analyze
go build -o bin/compile ./cmd/compile
go build -o bin/render  ./cmd/render
#    (or just: go test ./...  — which builds and runs everything)

# 2. One-shot: point at a folder of clips
./edit.sh ~/Videos/my-raw-clips

#    ...or drive a project manually
mkdir -p projects/my-clip/footage
cp /path/to/raw/*.mp4 projects/my-clip/footage/
./run.sh my-clip                 # analyze → agent → compile → render --dry-run
./run.sh my-clip --render        # also bake final.mp4
xdg-open projects/my-clip/project.mlt   # refine in Kdenlive
```

The artifacts you get in `projects/<name>/`:
- `metadata.json` — what `analyze` learned about your footage.
- `edl.json` — the agent's edit decision (the interesting creative output).
- `project.mlt` — open this in Kdenlive.
- `preview.mp4` — fast 640×360 proxy of the cut.
- `final.mp4` — only if you passed `--render`.
