# mlt-pipeline — Design

**Status:** Approved (brainstorming complete)
**Date:** 2026-07-13
**Engine:** Go 1.22+, MLT 7.x (`melt`), `ffmpeg`/`ffprobe`, OpenCode Go binary
**Outcome target:** raw footage → `project.mlt` that opens in Kdenlive for human refinement → optional baked MP4

## 1. Goal

A small, local pipeline that turns raw video footage into a Kdenlive-editable `project.mlt`, with an open-weight-friendly agent doing the edit planning. The agent's entire job is to read `metadata.json` and write `edl.json`; everything else is deterministic, testable Go. The user opens the resulting `.mlt` in Kdenlive to refine the cut.

This is a fresh project at `/home/ah64/apps/mlt-pipeline/`. The existing `/home/ah64/Documents/video editing/pi-video-editor/` (ffmpeg + Pi + ffmpeg-compose) is unrelated and stays as-is.

## 2. Architecture

Three Go CLIs + one shell driver + one system prompt for the agent. The agent's only output surface is `edl.json`.

```
projects/<name>/
  footage/                  # 1+ raw clips, read-only
  metadata.json             # analyze output
  edl.json                  # agent output (also: edl.v2.json, edl.v3.json on retry)
  project.mlt               # compile output
  preview.mp4               # render --dry-run output
  final.mp4                 # render output (only with --render)
```

Each project is fully isolated — two `run.sh` invocations on two different projects never share state, files, or processes. Source clips are read-only and may be shared across projects (the filesystem handles concurrent reads).

## 3. Data flow

```
1. analyze  <footage/*>  --output metadata.json
2. agent    reads metadata.json, writes edl.json, calls compile + render --dry-run
3. compile  --edl edl.json --metadata metadata.json --output project.mlt --clamp
4. render   --mlt project.mlt --output preview.mp4 --dry-run
5. (you)    open project.mlt in Kdenlive
6. (you)    optional: ./run.sh <name> --render  to bake final.mp4
```

The driver (`run.sh`) is idempotent — re-running it skips any stage whose output already exists. Iteration is cheap.

## 4. Components

### 4.1 `analyze`

**CLI:** `./analyze <clip1.mp4> [clip2.mp4 ...] [--scenes --scene-threshold 0.3] --output metadata.json`

**Output (`metadata.json`):**
```json
{
  "version": 1,
  "clips": [
    {
      "path": "/abs/path/clip1.mp4",
      "durationSec": 42.3,
      "width": 1920, "height": 1080, "fps": 30,
      "hasAudio": true,
      "scenes": [
        { "startSec": 0,   "endSec": 12.3 },
        { "startSec": 12.3, "endSec": 42.3 }
      ]
    }
  ],
  "totalDurationSec": 42.3
}
```

**Behavior:** `ffprobe` for codec/resolution/fps/audio flag; `ffmpeg` with `select='gt(scene,N)'` for scene detection. A single static shot (no scene changes) produces one `scenes[]` entry spanning the whole clip, not an empty array.

**Failure modes:** non-existent path → exit 1, stderr message; ffprobe parse error → exit 1; out-of-disk → exit 1. Never modifies input files.

### 4.2 `compile`

**CLI:** `./compile --edl edl.json --metadata metadata.json --output project.mlt [--clamp] [--no-clamp]`

**Input contracts:**

`edl.json` (JSON Schema-validated):
```json
{
  "version": 1,
  "targetDurationSec": 60,
  "segments": [
    { "source": "/abs/path/clip1.mp4", "inSec": 12.3, "outSec": 18.0, "transition": "cut" }
  ]
}
```
- `transition`: `"cut"` (default) or `"fade"`. `dissolve` is v2.
- `0 ≤ inSec < outSec ≤ clip.durationSec` after clamp.

`metadata.json`: same shape as `analyze` outputs. Used by `--clamp` to bound `inSec`/`outSec`.

**Output:** Minimal MLT XML, written to `--output`. Always produces a `project.mlt` that opens in Kdenlive 26.x.

**Failure modes:**
- EDL doesn't match schema → exit 1, JSON-pointer error.
- `inSec`/`outSec` outside clip bounds → clamp to bounds (if `--clamp`, default), else exit 1.
- Source path missing on disk → exit 1.
- All errors include a `fix:` line in stderr: e.g., `fix: set inSec=0.0 on segment 0 (clip ends at 12.3)`. The agent reads stderr to retry.

### 4.3 `render`

**CLI:** `./render --mlt project.mlt --output final.mp4 [--dry-run] [--nice 10] [--vcodec libx264] [--acodec aac]`

**Behavior:** Wraps `melt project.mlt -consumer avformat:<output> vcodec=... acodec=...`. With `--dry-run`, appends ` s=640x360 preset=ultrafast` to the consumer string. The whole `melt` invocation runs under `nice -n <N>` so the subprocess tree inherits lower CPU priority — important when the user is concurrently using Kdenlive.

**Defaults:** `--nice 10` (background-friendly). Pass `--nice 0` to disable.

**Failure modes:** MLT parse error → exit 1, stderr captures melt's complaint; codec missing → exit 1; out-of-disk → exit 1.

### 4.4 `run.sh` (driver)

**CLI:** `./run.sh <project-name> [--force] [--render] [--no-render] [--agent opencode]`

**Behavior:**
1. `mkdir -p projects/<name> && cd projects/<name>`
2. Stage 1 — analyze: skip if `metadata.json` exists; else `./analyze` on every `projects/<name>/footage/*`.
3. Stage 2 — agent: skip if `edl.json` exists; else `nice -n 5 opencode -p ../../prompts/edl_writer.md -f json -q`. (Validation happens at the compile stage, not here.)
4. Stage 3 — compile: skip if `project.mlt` exists; else `./compile` with clamp on.
5. Stage 4 — render dry-run: skip if `preview.mp4` exists; else `./render --dry-run`. Stop on failure.
6. Stage 5 — final render: only with `--render`. Default is `--no-render`.

**Post-agent check:** after Stage 2, if the agent exited non-zero OR `edl.failed.json` exists, the driver prints the path to `edl.failed.json` and exits 1. Stages 3+ are skipped.

`--force` re-runs every stage. The driver writes only to `projects/<name>/`.

## 5. The agent

### 5.1 Harness

OpenCode Go binary (`~/.opencode/bin/opencode`, v1.17.19). Tools available to the agent: `bash`, `read`, `write`, `edit`, `glob`, `grep`. No MCP, no custom tools.

### 5.2 Workflow (the agent's loop)

```
1. read   metadata.json
2. reason about which scenes to keep
3. write  edl.json
4. bash   ../../compile --edl edl.json --metadata metadata.json --output project.mlt
5.        on non-zero exit: read stderr, edit edl.json, go to step 4
6. bash   ../../render --mlt project.mlt --output preview.mp4 --dry-run
7.        on non-zero exit: read stderr, edit edl.json, jump to step 4
8. stop. final render is opt-in.
```

### 5.3 Guardrails

| Guardrail | Where |
|---|---|
| Schema-validate `edl.json` | `./compile` |
| Clamp `inSec`/`outSec` against `metadata.json` | `./compile --clamp` (default) |
| Dry-run before any final render | `./render --dry-run` |
| Versioned EDL artifacts | `edl.json`, `edl.v2.json`, `edl.v3.json` (kept on retry) |
| Retry budget | 3 attempts total across the whole loop; on exhaustion, agent writes `edl.failed.json` |

The agent never runs `ffmpeg` or `melt` directly. The agent never edits `project.mlt` by hand. The agent never modifies footage.

### 5.4 System prompt (`prompts/edl_writer.md`)

```markdown
You are editing video. Your only job: read metadata.json, write edl.json, run the
compile + dry-run render, fix any errors, stop. You never run ffmpeg or melt yourself.
You never modify footage files. You never edit project.mlt by hand.

Files you may read:  metadata.json
Files you may write: edl.json, edl.v2.json, edl.v3.json, edl.failed.json
Tools you may call:
    ./compile --edl <f> --metadata metadata.json --output project.mlt
    ./render  --mlt project.mlt --output preview.mp4 --dry-run
            (run only after compile succeeds)

EDL schema (strict — ./compile will reject anything that doesn't match):
    {
      "version": 1,
      "targetDurationSec": <number>,
      "segments": [
        { "source": "<abs path>", "inSec": <float>, "outSec": <float>,
          "transition": "cut" | "fade" }
      ]
    }

Rules:
  1. Every segment.source MUST be a path that appears in metadata.json.
  2. 0 <= inSec < outSec <= matching clip's durationSec.
  3. Sum of (outSec - inSec) should approximate targetDurationSec. ±10% is fine.
  4. Transitions: prefer "cut" between same-energy shots; use "fade" for time
     jumps or mood shifts. "dissolve" is not in v1 — don't write it.
  5. On any compile/render error, READ STDERR FIRST. The fix is almost always
     in the last line (e.g., "fix: set inSec=0.0 on segment 0").
  6. You have 3 attempts total. If you're still failing on attempt 3, write
     edl.failed.json with the last EDL and a one-line "why I gave up" and stop.

When all stages pass, print a 2-line summary and stop. Do not call ./render
without --dry-run.
```

## 6. Project layout

```
mlt-pipeline/
├── cmd/
│   ├── analyze/main.go
│   ├── compile/main.go
│   └── render/main.go
├── internal/
│   ├── metadata/           # metadata.json types + load/save
│   ├── edl/                # edl.json types + JSON-Schema validation + clamp
│   └── mlt/                # MLT XML string templating
├── schema/edl.schema.json
├── testdata/               # see §7
├── prompts/edl_writer.md
├── run.sh
├── go.mod
├── README.md
└── docs/superpowers/specs/2026-07-13-mlt-pipeline-design.md   (this file)
```

Go module path: `mlt-pipeline` (local-only).

## 7. Testing

### 7.1 Layers

| Layer | Tool | What it covers |
|---|---|---|
| Unit | `go test ./internal/...` | Schema validation, clamp logic, MLT string templating. Fast, no I/O, no model. |
| CLI smoke | `go test ./cmd/...` | Each CLI binary: arg parsing, exit codes, stdout/stderr shape. Uses `testdata/`. |
| Pipeline e2e | `test/e2e_test.go` | Runs `analyze` → hand-written `edl.json` → `compile` → `render --dry-run` against a real clip. Asserts MP4 plays, has video + audio streams, matches expected duration. No LLM involved. |
| Agent canary | `test/agent_test.go` (manual, not in CI) | Runs `run.sh` end-to-end against a fixed prompt + fixture. Asserts pipeline produces a valid `edl.json` in ≤3 retries. Run on prompt/model changes. |

### 7.2 Fixtures (`testdata/`)

```
testdata/
├── clip_short.mp4                       # 10s synthetic, 1920x1080@30fps, color w/ scene cuts
├── clip_short.metadata.json             # expected analyze output
├── clip_short.edl.handwritten.json      # e2e test's hand-written EDL
├── clip_short.expected.mlt              # golden MLT (byte-diff)
├── clip_short.expected.preview.mp4      # generated by `go test -update`, committed
└── README.md                            # how to regenerate fixtures with ffmpeg
```

Synthetic clip is generated by a 5-line `ffmpeg` invocation (color source + `smptebars` segments). Reproducible, ~50KB, no licensing issues.

### 7.3 Load-bearing unit tests

`internal/edl/validate_test.go`:
- Valid EDL → no error.
- `inSec >= outSec` → "inSec must be less than outSec" + segment index.
- `inSec` outside [0, clip.durationSec] → clamp preview.
- `transition: "dissolve"` → rejected with "v1 only supports cut/fade".
- Source path not in `metadata.json` → "unknown source: <path>".
- Empty `segments` → rejected.
- `targetDurationSec` missing → defaults to sum of segments.

`internal/edl/clamp_test.go`:
- `inSec = -2.5, clip.durationSec = 10` → clamped to 0.0, warning logged.
- `outSec = 15.0, clip.durationSec = 10` → clamped to 10.0, warning logged.
- Already in range → unchanged, no warning.

`internal/mlt/generate_test.go`:
- Single-segment EDL → MLT matches `clip_short.expected.mlt` byte-for-byte.
- Multi-segment with mixed `cut`/`fade` → MLT has correct producer entries and a `mix` block on the fade transition.
- `transition: "fade"` adds a `<transition>` element between entries; `cut` does not.

## 8. Error handling

### Detected and recovered automatically

- Schema errors in `edl.json` → rejected by `./compile`, agent retries.
- Out-of-range `inSec`/`outSec` → clamped (default) or rejected (with `--no-clamp`).
- Missing source files → rejected by `./compile` or `./render`.
- Melt parse errors → rejected by `./render`, agent retries.
- Retry exhaustion → `edl.failed.json` written, `run.sh` exits non-zero.

### Detected only at Kdenlive (user must step in)

| Failure | How it surfaces | Recovery |
|---|---|---|
| `project.mlt` opens as "Untitled" with broken bin entries | Visible in Kdenlive on open | Re-edit `edl.json` by hand, re-run `./compile` |
| Source clip moved/deleted between analyze and render | `melt` exits with "file not found"; `./render` exits 1 | Re-run `./analyze` on the new path; the rest re-runs automatically |
| Model change (Qwen → DeepSeek, etc.) | Agent canary test fails | Re-run agent test; if it still fails, prompt may need a tweak. No code changes. |
| Kdenlive version drift (26.x → 27.x) | `project.mlt` opens but is read-only / missing tracks | Pin Kdenlive version in README; revisit `internal/mlt/` to emit the new schema. Single-file change. |

None of these are silent.

## 9. Out of scope (v2 / deferred)

- `transition: "dissolve"` (true crossfade via `xfade` filter).
- Audio normalization beyond a single-pass `loudnorm` at the end of final render.
- Multi-tractor (nested tracks) in MLT.
- Captions / subtitles burn-in.
- Distributed / multi-machine render.
- Full Kdenlive `.kdenlive` project generation (with `<kdenlivedoc>`, bin entries, render profiles). v1 produces minimal MLT.
- Music / voiceover generation.

## 10. Build order (matches doc §12, strict)

1. **Stage 1 — deterministic core.** `analyze` + `compile` + `render` Go CLIs, hand-written `edl.json`, `testdata/` fixtures, e2e test that runs the whole pipeline with no LLM. **Done when** `go test ./...` passes and `testdata/clip_short.expected.preview.mp4` matches.
2. **Stage 2 — agent + dry-run loop.** `run.sh` driver, `prompts/edl_writer.md`, end-to-end run against a real clip with a hand-fed `edl.json` first to verify the driver. **Done when** `./run.sh <name>` produces `preview.mp4` from the agent's `edl.json` in ≤3 retries.
3. **Stage 3 — guardrails live.** Schema validation in `./compile`, clamp logic, dry-run proxy, versioned EDL artifacts, retry budget enforcement. **Done when** the four guardrails from §5.3 are unit-tested and bad EDLs are rejected at the door.
4. **Stage 4 — polish.** README, `--force`/`--render`/`--no-render` flags, error message quality, Kdenlive-open verification of `testdata/clip_short.expected.mlt`. **Done when** a second clip from a different source works without code changes.

## 11. Open items

None at design time. All decisions resolved during brainstorming.
