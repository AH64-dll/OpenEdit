# mlt-pipeline — Complete Project Reference (`info.md`)

> A single source of truth describing **everything** in this repository: every
> directory, every module, every public function, the data model, the tool
> surface, how the pieces connect, how to build/run/test, known bugs, and
> limitations.
>
> Generated 2026-07-19 after a full source-tree exploration. The repo has two
> halves:
> 1. **`mlt-pipeline` (Go)** — the original deterministic pipeline:
>    raw footage → `edl.json` → `project.mlt` (MLT 7 XML).
> 2. **`pyagent-kdenlive-guide` (Python)** — "PyAgent": an AI chat-driven
>    editor that reads & writes **`.kdenlive`** files (full Kdenlive projects,
>    not bare MLT) via 38 tool-callable operations, plus a chat UI, a live
>    D-Bus sync, and a render/QC pass.
>
> `info.md` lives at the repo root. `PROJECT_EXPLAINED.md` covers the Go half
> in prose; this file covers **both** halves function-by-function.

---

# TABLE OF CONTENTS

- [0. Repository layout](#0-repository-layout)
- [1. The Go pipeline (`mlt-pipeline`)](#1-the-go-pipeline-mlt-pipeline)
  - [1.1 Top-level build & scripts](#11-top-level-build--scripts)
  - [1.2 `cmd/` — CLI entry points](#12-cmd--cli-entry-points)
  - [1.3 `internal/` — libraries](#13-internal--libraries)
  - [1.4 `prompts/` — the agent prompt](#14-prompts--the-agent-prompt)
  - [1.5 Testing (Go)](#15-testing-go)
- [2. PyAgent (`pyagent-kdenlive-guide`)](#2-pyagent-pyagent-kdenlive-guide)
  - [2.1 Phase 1 — knowledge base / catalog](#21-phase-1--knowledge-base--catalog)
  - [2.2 Phase 2 — project engine (the backend)](#22-phase-2--project-engine-the-backend)
  - [2.3 Phase 3 — pyagent core (tool dispatch)](#23-phase-3--pyagent-core-tool-dispatch)
  - [2.4 Phase 4 — chat UI](#24-phase-4--chat-ui)
  - [2.5 Phase 5 — D-Bus live sync](#25-phase-5--dbus-live-sync)
  - [2.6 Phase 6 — render & QC](#26-phase-6--render--qc)
  - [2.7 Phase 7 — real-session e2e harness](#27-phase-7--real-session-e2e-harness)
  - [2.8 The 38-tool surface (master table)](#28-the-38-tool-surface-master-table)
  - [2.9 System prompt & error contract](#29-system-prompt--error-contract)
- [3. Cross-cutting: data model, error model, transport](#3-cross-cutting-data-model-error-model-transport)
- [4. How to build, run, test](#4-how-to-build-run-test)
- [5. Known bugs & limitations](#5-known-bugs--limitations)
- [6. Glossary](#6-glossary)

---

# 0. Repository layout

```
mlt-pipeline/                                   (git repo root, /home/ah64/apps/mlt-pipeline)
├── README.md                                   Go pipeline overview
├── PROJECT_EXPLAINED.md                        Go pipeline, deep prose walkthrough
├── go.mod                                      module mlt-pipeline; Go 1.22; ZERO external deps
├── edit.sh                                     one-shot wrapper: symlink footage → run.sh → open Kdenlive
├── run.sh                                      the 5-stage driver (analyze→agent→compile→render)
├── PyAgent.desktop                             desktop launcher for the chat UI
├── bin/                                        compiled Go binaries (gitignored)
├── cmd/                                        analyze / compile / render CLIs (Go)
├── internal/                                   metadata, edl, mlt libraries (Go)
├── docs/superpowers/                           design specs + plans (the agent's own notes)
├── prompts/edl_writer.md                       system prompt for the Go-pipeline agent
├── test/                                       e2e + agent-canary (Go)
├── testdata/                                   synthetic fixtures (clip_short.*)
├── projects/                                   per-project working dirs (gitignored)
└── pyagent-kdenlive-guide/                     ← the Python "PyAgent" system (see §2)
    ├── 00_START_HERE.md                        orientation / reading order
    ├── 01_FINDINGS_AND_ARCHITECTURE.md         why-decisions + Kdenlive internals findings
    ├── BUGS_FIXED.md                           running log of fixed bugs
    ├── PHASE_0..8_*.md                         phase design docs
    ├── phase1_knowledge_base/
    ├── phase2_project_engine/
    ├── phase3_pyagent_core/
    ├── phase4_chat_ui/
    ├── phase5_dbus_sync/
    ├── phase6_render_qc/
    ├── phase7_real_session/
    ├── docs/  spike-results/  .agents/         research artifacts
    └── pyproject.toml per phase (phase3..7 each ship one)
```

**Two mental models:**
- **Go pipeline** = "AI writes an edit decision list; deterministic Go compiles it to MLT." Output is a `.mlt` that Kdenlive opens as *Untitled*.
- **PyAgent** = "AI drives a chat UI that calls Python tools to read/write real `.kdenlive` projects directly." Output is a real Kdenlive project (named, reloadable). This is the more complete system and where the bulk of the code lives.

---

# 1. The Go pipeline (`mlt-pipeline`)

Design philosophy (from `docs/superpowers/specs/2026-07-13-mlt-pipeline-design.md`):
> **Everything deterministic is testable Go. The AI's only job is to read
> `metadata.json` and write `edl.json`.**

No third-party Go packages; all heavy lifting delegated to external CLIs via
`os/exec`: `ffprobe`, `ffmpeg`, `melt`, `opencode`, `nice`, `xdg-open`.

## 1.1 Top-level build & scripts

| File | Purpose |
|---|---|
| `run.sh` | 5-stage driver. `set -euo pipefail`. Resolves `ROOT`, `PROJECT_DIR=ROOT/projects/$PROJECT`. Idempotent via `should_run` (runs a stage only if its output file is missing, unless `--force`). Stages: `analyze`→`agent`(opencode)→`compile`→`render --dry-run`→(optional `--render`) final. Stage 2 fails → prints message, `exit 1`, skips stages 3+. Final render skipped by default. |
| `edit.sh` | One-shot: derive name from folder, `mkdir -p projects/<name>/footage`, **symlink** raw clips in (idempotent, refuses to clobber real files), delegate to `run.sh`, then `xdg-open` the `.mlt`. Flags: `<source>` required (dir or file), `[project-name]`, `--render`, `--force`, `-h`. |
| `go.mod` | `module mlt-pipeline`, `go 1.22`. No `require` block. |

Build:
```bash
go build -o bin/analyze ./cmd/analyze
go build -o bin/compile ./cmd/compile
go build -o bin/render  ./cmd/render
# or just: go test ./...   (builds + runs everything)
```

## 1.2 `cmd/` — CLI entry points

Each is a thin `main.go` that parses flags, calls `internal/`, writes a file.

### `cmd/analyze/main.go`
Flags: `-scenes` (default true), `-scene-threshold` (default 0.3), `-output` (default `metadata.json`).
Behavior: takes positional file paths → `metadata.Analyze(paths, scenes, threshold)` → `metadata.Save(output, m)`.

### `cmd/compile/main.go`
Flags: `-edl` (default `edl.json`), `-metadata` (default `metadata.json`), `-output` (default `project.mlt`), `-no-clamp`.
Strict linear pipeline:
```go
m, _ := metadata.Load(metadataPath)
e, _ := edl.Load(edlPath)
edl.Validate(e, m)              // mutates e; gating
if !noClamp { edl.Clamp(e, m) } // trim out-of-range
out, _ := mlt.Generate(e, m)    // MLT XML string
os.WriteFile(output, []byte(out), 0644)
```
`Validate` runs before `Clamp`. Every failure exits 1 with a `compile:`-prefixed message.

### `cmd/render/main.go`
Flags: `-mlt`, `-output`, `-dry-run` (default false), `-nice` (default 10), `-vcodec` (`libx264`), `-acodec` (`aac`).
Builds a `melt` command: `melt <mlt> -consumer avformat:<output> vcodec=.. acodec=..`; if `-dry-run` adds `s=640x360 preset=ultrafast`. Wraps in `nice -n N` when `-nice>0`. Streams stdout/stderr.

## 1.3 `internal/` — libraries

### `internal/metadata` — the media manifest
Types (`types.go`):
- `Manifest{Version, Clips[]Clip, TotalDurationSec}`
- `Clip{Path, DurationSec, Width, Height, FPS, HasAudio, Scenes[]Scene}`
- `Scene{StartSec, EndSec}`

Functions:
- `Analyze(paths []string, scenes bool, threshold float64) (*Manifest, error)` — loops clips, sums durations.
- `analyzeOne(path)` — runs `ffprobe -show_format -show_streams`; parses width/height/`r_frame_rate` (num/den→fps), audio flag.
- `detectScenes(path, threshold)` — runs `ffmpeg -vf select='gt(scene,<t>)',showinfo -f null -`; scrapes `pts_time:` → `Scene` ranges; one whole-clip scene if no cuts.
- `Load(path) (*Manifest, error)` / `Save(path, m) error` — plain `encoding/json` (2-space indent). Absolute file paths are recorded.

### `internal/edl` — the Edit Decision List (the AI↔system contract)
Types (`types.go`):
```go
type EDL struct { Version int; TargetDurationSec float64; Segments []Segment }
type Segment struct { Source string; InSec float64; OutSec float64; Transition Transition } // Transition: "cut"|"fade"
```
- `Load(path) (*EDL, error)` / `Save(path, e) error`.
- `Validate(e *EDL, m *metadata.Manifest) error` — **mutates `e`**, is the validation gate. Order: version==1; ≥1 segment; unknown transition rejected (`dissolve` explicitly out of scope — `"v1 only supports cut/fade"`); empty `Transition` → `"cut"`; `inSec<outSec`, `inSec>=0`; `source` must be in manifest; `outSec<=clip.DurationSec`; default `targetDurationSec` to sum of segment lengths. **Every error string contains a `fix:` hint** (e.g. `fix: set inSec=%v outSec=%v`) so the agent can self-correct.
- `Clamp(e, m) ([]string, error)` — bounds `inSec`/`outSec` against real clip duration; returns warnings (one per adjustment); hard error only if source missing. Call `Validate` first, then `Clamp`.

### `internal/mlt` — EDL → MLT XML
- `Generate(e *edl.EDL, m *metadata.Manifest) (string, error)`:
  - One `<producer>` per segment (id `producerN`, `<property name="resource">path</property>`).
  - Profile (width/height/fps) derived from `m.Clips[0]` **only** (mixed-resolution unsupported).
  - `secToTC(s)` → `HH:MM:SS.mmm`.
  - Emits a single-tractor MLT 7.0.0 doc: `<mlt>` → `<profile>` → producers → `<playlist id="video_track">` with one `<entry>` per segment (+ `<transition name="fade" duration="1"/>` between segments when the later segment's transition is `fade`) → `<tractor id="main_tractor">`.

## 1.4 `prompts/` — the agent prompt
`prompts/edl_writer.md` (34 lines): read `metadata.json`, write `edl.json`, run `compile` + `render --dry-run`, fix errors, stop. Prohibitions: never run `ffmpeg`/`melt` directly, never modify footage, never hand-edit `project.mlt`. Allowed tools: only `./compile` and `./render --dry-run`. On error, **read stderr first** (the `fix:` is in the last line). 3 attempts total; on exhaustion write `edl.failed.json`.

## 1.5 Testing (Go)
- **Unit**: `internal/metadata/*_test.go` (skips if ffprobe missing), `internal/edl/validate_test.go` (10 cases), `internal/edl/clamp_test.go`, `internal/mlt/generate_test.go` (incl. **golden byte-match** vs `testdata/clip_short.expected.mlt`), `cmd/*/main_test.go` (smoke).
- **Fixtures** (`testdata/`): `clip_short.mp4` (10s, 1920×1080@30fps, synthetic, no audio) + hand-authored `clip_short.metadata.json`, `clip_short.edl.handwritten.json`, `clip_short.expected.mlt`.
- **E2E** (`test/e2e_test.go`, `TestPipelineE2E_NoLLM`): builds all 3 CLIs, runs analyze → compile → render, asserts video stream + duration ±20%.
- **Agent canary** (`test/agent_test.go`, build tag `agent_canary`, env `MLT_PIPELINE_RUN_AGENT_TESTS=1`): runs the full `run.sh` with the real opencode agent.

```bash
go test ./...                              # unit + e2e (no agent)
go test -tags=agent_canary ./test/...      # also agent canary (needs opencode + model)
```

---

# 2. PyAgent (`pyagent-kdenlive-guide`)

A Python system that lets an LLM edit real `.kdenlive` files through 38
tool-callable operations, with a chat UI, optional live D-Bus sync, and a
render/QC pass. Each phase is a package; `PYTHONPATH=.` from the guide root.
Phases 3–7 each ship a `pyproject.toml` + `Makefile`.

**Verified facts:** `all_tools()` returns **38 tools** (25 mutating, 13 read-only). `phase3_pyagent_core/extension.ts` exists (367 lines) — this is the pi/OpenCode extension entry point.

## 2.1 Phase 1 — knowledge base / catalog

**`phase1_knowledge_base/build_catalog.py`** — Ingests local Kdenlive/MLT data
into a normalized `catalog.json` consumed by Phase 3's system prompt & tool
defs.
- Constants: `KDE_NS`, `ANIMATION_STRING_KEYFRAME_TYPES` (frozenset),
  `SIMPLEKEYFRAME_TYPES = {"simplekeyframe"}`, `KDENLIVE_DATA=/usr/share/kdenlive`,
  `MLT_DATA=/usr/share/mlt-7`.
- `_ns(root)`, `_t(root, local, ns)`, `parse_param(param, ns="")`,
  `parse_effect_xml(path) -> dict|None` (returns `{kind, kdenlive_id,
  mlt_service, source, ...parameters}`; `None` on parse error),
  `_parse_param(...)` (also sets `"keyframes"` flag),
  `load_kdenlive_category_index() -> dict` (parses `kdenliveeffectscategory.rc`),
  `parse_mlt_yaml(path) -> dict|None` (minimal line-based YAML reader),
  `main() -> int` (orchestrates parsing + MLT YAML cross-reference, writes `catalog.json`).

## 2.2 Phase 2 — project engine (the backend)

The deterministic "hands." Reads/writes `.kdenlive` XML via `lxml`, preserving
unknown elements (round-trip safe). Exposes `EditorBackend` (abstract) with two
impls: `KdenliveFileBackend` (concrete, file-based) — the only one shipped.

### `phase2_project_engine/__init__.py`
Re-exports: `EditorBackend`, `KdenliveFileBackend`, all dataclasses
(`ProjectInfo`, `ClipSummary`, `TrackSummary`, `TransitionSummary`,
`MarkerSummary`, `EffectSummary`, `TimelineSummary`), exceptions
(`BackendError`, `ValidationError`, `NotFoundError`, `CatalogError`), `Catalog`.

### `phase2_project_engine/types.py` — frozen dataclasses (the JSON contract)
- `ProjectInfo(name, fps, width, height, colorspace, track_count, duration_sec, path)`
- `ClipSummary(clip_id, track_index, start_sec, end_sec, source_id, source_path, source_name, source_in_sec, source_out_sec, effects: tuple[str,...])`
- `TrackSummary(index, kind, name, clip_count)`
- `TransitionSummary(transition_id, track_index, start_sec, end_sec, kind)`
- `MarkerSummary(position_sec, label, kind)`
- `EffectSummary(effect_id, clip_id, params: dict[str,str])`
- `TimelineSummary(project, tracks, clips, transitions, markers)` — renders as a markdown table in Phase 3.

### `phase2_project_engine/errors.py`
- `BackendError(Exception)` — base.
- `ValidationError(BackendError)` — bad input; message **must** contain a `fix:` line.
- `NotFoundError(BackendError)` — clip/track/effect/transition not present.
- `CatalogError(BackendError)` — effect/transition id not in the Phase 1 catalog.
- `validation_error(msg: str, fix_hint: str|None=None) -> ValidationError` — appends a `fix:` line if absent.

### `phase2_project_engine/catalog.py`
- `Catalog(effects, transitions, generators, by_id: dict[str,dict])` — `by_id` maps `kdenlive_id`→entry.
- `Catalog.from_json(path) -> Catalog` (classmethod).

### `phase2_project_engine/io.py` — low-level XML I/O
- Constants: `MLT_VERSION="7.40.0"`, `KdenliveDocVersion="1.1"`.
- Timecode: `_sec_to_tc(sec) -> str`, `_tc_to_sec(s) -> float`.
- `ProjectTree` (dataclass: `root, path`): `get_profile()`, `get_profile_fps() -> float`, `get_profile_resolution() -> (int,int)`, `get_main_bin()`, `get_tractor()` (prefers tractor with `<multitrack>`), `get_docproperties() -> dict`; write helpers `ensure_kdenlive_properties_on_producer(...)`, `ensure_docproperties()`, `ensure_root_attrs()`.
- `load_project(path) -> ProjectTree`, `save_project(tree, path=None)`, `_probe_duration_sec(path) -> float` (ffprobe; 0.0 on fail).

### `phase2_project_engine/tracks.py` — navigation helpers
- `get_tracks(tree) -> list` (user-facing, video first; skips `main_seq`/`projectTractor`),
- `get_track_playlists(tree, tractor) -> list`, `is_audio_track(tree, tractor) -> bool`,
- `get_video_playlist(tree, tractor) -> etree|None` (returns `None` if unidentifiable — Bug-1 fix),
- `_playlist_has_video_entries(tree, pl) -> bool`,
- `resolve_producer(tree, source_id) -> etree` (raises `BackendError`),
- `resolve_source_duration(tree, source_id) -> float`,
- `find_clip_entry(tree, clip_id) -> (entry, track_index)` (raises `BackendError`),
- `find_all_entries(tree, clip_id) -> list`,
- `next_kdenlive_id(tree) -> str`,
- `bump_tractor_duration(tree)` (sets tractor `out` to max playlist duration; Bug-4 fix).

### `phase2_project_engine/validators.py` — pure validators (raise `ValidationError`)
- `validate_track_index(idx, count)`, `validate_position_sec(pos)` (rejects negative),
- `validate_clip_range(in_sec, out_sec, source_duration)`,
- `_catalog_id_lookup(catalog, kind) -> str` (case-insensitive),
- `validate_transition_kind(kind, catalog) -> str`, `validate_effect_id(effect_id, catalog) -> str`,
- `_coerce_param(name, ptype, value) -> str`, `validate_effect_params(entry, params) -> dict` (rejects unknown names),
- `validate_source_path(path) -> Path` (requires existing file), `validate_marker_kind(kind) -> str`.

### `phase2_project_engine/_keyframes.py` — animation-string parse/serialize
- Curve chars: `CURVE_LINEAR="\`"`, `DISCRETE="|"`, `HOLD="!"`, `SMOOTH="~"` (+ `a,b,c,d,A,B,C,D`).
- `Keyframe(frame, value, type)` (frozen).
- `parse_animation_string(s) -> list[Keyframe]`, `serialize_keyframes(kfs) -> str`,
- `is_keyframable_param(catalog, effect_id, param_name) -> bool|str` (`True` / `"simplekeyframe"` / `False`),
- `coerce_param_value(param_type, value) -> str` (raises `ValueError`).

### `phase2_project_engine/backend.py` — `EditorBackend` ABC + private summary helpers
- Abstract methods (all raise `NotImplementedError`): `get_project_info`, `get_timeline_summary`, `import_media`, `insert_clip`, `append_clip`, `move_clip`, `trim_clip`, `delete_clip`, `add_transition`, `remove_transition`, `apply_effect`, `remove_effect`, `add_marker`, `slip_clip`, `ripple_delete_clip`, `change_clip_speed`, `split_clip`, `replace_clip_source`, `group_clips`, `ungroup_clips`, `list_groups`, `save` — plus richer set in the concrete impl below.
- Private: `_track_kind(tr)`, `_entry_to_clip_summary(entry, track_index, playlist, tree)`, `_iter_transitions(tree)`, `_iter_markers(tree)`.

### `phase2_project_engine/backend_dispatch.py` — `KdenliveFileBackend`
Concrete impl. `__init__(project_path, catalog)` loads project or builds an
empty one via `_new_empty_project()` (1080p/30fps, main_bin, video_track,
main_tractor). **Every method delegates to a function in `ops.*`.** This is
where `get_timeline_summary()` is implemented (iterates tracks →
`TrackSummary`/`ClipSummary`; assembles `TimelineSummary`). Methods mirror the
ABC plus extras: `set_transition_property`, `get_effect_param`, `set_effect_param`,
`list_keyframes`, `set_keyframe`, `remove_keyframe`, `set_clip_speed_ramp`,
`add_effect_to_track`, `list_track_effects`. `save(path=None)`.

### `phase2_project_engine/ops/` — the operation implementations
Each op is a free function taking `(tree: ProjectTree, ...)` and returning a
result (typically a `kdenlive:id` string or a dict).

| File | Functions (signature summary) | Raises |
|---|---|---|
| `ops/__init__.py` | re-exports all op functions | — |
| `ops/_helpers.py` | `playlist_duration(pl)`, `entry_start_sec(pl, entry)`, `shift_entry_on_timeline(pl, entry, shift)`, `insert_entry_at_position(pl, entry, position_sec)`, `copy_elem(elem)`, `get_project_fps(tree)`, `probe_duration_sec(path)` | — |
| `ops/bin.py` | `import_media(tree, paths: Sequence[str]) -> list[str]` (returns `kdenlive:id`s; `validation_error` on empty/blank; `BackendError` if no id) | `ValidationError`, `BackendError` |
| `ops/clips.py` | `insert_clip(tree, track_index, position_sec, source_id, source_in_sec=0, source_out_sec=None, video_only=False, audio_only=False) -> str`; `append_clip(...)` (delegates to insert at end); `move_clip(tree, clip_id, new_track, new_position_sec)`; `trim_clip(tree, clip_id, new_in_sec, new_out_sec)`; `delete_clip(tree, clip_id)` | `BackendError`, validators |
| `ops/clips_edit.py` | `slip_clip(tree, clip_id, delta_sec) -> dict`; `ripple_delete_clip(tree, clip_id) -> dict` (returns deleted + shifted ids); `change_clip_speed(tree, clip_id, rate) -> dict` (rate ∈ [0.1,10]); `split_clip(tree, clip_id, at_sec) -> dict` (returns left/right ids); `replace_clip_source(tree, clip_id, new_source_id) -> dict`; re-exports `set_clip_speed_ramp` | `NotFoundError`, `ValidationError` |
| `ops/clips_speed.py` | `_find_clip_producer(tree, entry)`; `set_clip_speed_ramp(tree, clip_id, keyframes: Sequence[Mapping]) -> dict` (writes `<link mlt_service="timeremap">` time_map; keyframes must be non-empty, non-negative time_ms, rate∈(0,10], ascending, first at time_ms=0/rate=1.0) | `validation_error`, `NotFoundError`, `BackendError` |
| `ops/effects.py` | `apply_effect(tree, clip_id, effect_id, params=None, *, catalog=None) -> str`; `remove_effect(tree, clip_id, effect_index) -> dict`; `get_effect_param(tree, clip_id, effect_index, param_name, *, catalog=None) -> dict`; `set_effect_param(tree, clip_id, effect_index, param_name, value, *, catalog=None) -> dict` (replaces keyframes if keyframable) | `CatalogError`, `NotFoundError`, `ValidationError` |
| `ops/groups.py` | `group_clips(tree, clip_ids: list[str], group_name: str) -> dict`; `ungroup_clips(tree, group_name) -> dict`; `list_groups(tree) -> dict` (Kdenlive JSON `kdenlive:sequenceproperties.groups`) | `NotFoundError`, `ValidationError` |
| `ops/keyframes.py` | `list_keyframes(tree, clip_id, effect_index, param_name) -> dict`; `set_keyframe(tree, clip_id, effect_index, param_name, frame: int, value, type="linear", *, catalog=None) -> dict`; `remove_keyframe(tree, clip_id, effect_index, param_name, frame, *, catalog=None) -> dict` (type ∈ linear|discrete|hold|smooth|a..d|A..D) | `NotFoundError`, `ValidationError` |
| `ops/markers.py` | `add_marker(tree, position_sec, label, kind="marker") -> None` | `BackendError`, `ValidationError` |
| `ops/track_effects.py` | `add_effect_to_track(tree, track_index, effect_id, params=None, *, catalog=None) -> dict`; `list_track_effects(tree, track_index) -> dict` | `NotFoundError`, `ValidationError` |
| `ops/transitions.py` | `add_transition(tree, *, clip_a_id, clip_b_id, kind="dissolve", duration_sec=1.0, catalog=None) -> str` (centered on the cut `a_out`; cross-track → `validation_error`); `remove_transition(tree, transition_id) -> dict`; `set_transition_property(tree, transition_id, prop_name, value) -> dict` (rejects reserved prop names; coerces `a_track/b_track`→int, `in/out`→timecode) | `NotFoundError`, `ValidationError`, `BackendError` |

**Module-connection graph (Phase 2):**
`backend_dispatch.KdenliveFileBackend` is the single dispatch hub → `ops.*`.
`ops/*` depend on `io` (ProjectTree, timecode, ffprobe), `tracks` (navigation),
`validators` (input checks), `errors` (exception types), `ops/_helpers`
(playlist math). Effects/keyframes reach back into `clips_edit._find_entry_for_clip`
and `_keyframes`. `Catalog` is threaded (as `catalog=None`) through
`add_transition`, `apply_effect`, `set_keyframe`, `remove_keyframe`,
`set_effect_param`, `add_effect_to_track` for id resolution & param validation.

### Phase 2 tests (`phase2_project_engine/tests/`)
`ops_fixtures.py` is shared fixtures (NOT a test). Test files & representative
cases:
- `test_backend.py` — ABC is abstract; construct with path / in-memory.
- `test_catalog.py` — load/lookup (missing → `None`).
- `test_errors.py` — `fix:`-hint propagation; inheritance from `BackendError`.
- `test_io.py` — `sec_to_tc` roundtrip; load/save roundtrip; idempotent docprops.
- `test_keyframes.py` — parse/serialize animation strings; keyframable detection; coercion.
- `test_ops_bin.py` — import returns one id per path; unique ids; root-level producers; rejects missing/empty/blank path (incl. `test_import_media_rejects_empty_paths_list`).
- `test_ops_clips.py` — insert into correct playlist; no audio→video misroute; track/position/range validation; append lands at end; move; trim; delete; slip; speed; split; ripple; replace.
- `test_ops_clips_edit.py` — speed-ramp basic + monotonic-violation.
- `test_ops_effects.py` — apply w/ explicit params & w/ catalog defaults; `kdenlive:id` colon form; reject unknown id / bad param; remove; get/set param (set clobbers keyframes).
- `test_ops_groups.py` — group/ungroup/list; dup-name & empty-clip rejection; AVSplit preservation.
- `test_ops_helpers.py` — playlist duration; entry start; shift; insert-at-position splitting.
- `test_ops_keyframes.py` — list/add/update/remove; type & simplekeyframe rejection.
- `test_ops_markers.py` — marker/guide/chapter; negative/bad-kind rejection; kind normalization.
- `test_ops_track_effects.py` — add to audio track; video-effect-on-audio rejected; list; range error.
- `test_ops_transitions.py` — returns id + writes to correct tractor; unknown kind rejected; cross-track rejected w/ `fix:`; remove; set-transition-property timing & reserved-name rejection; **`test_add_transition_centers_on_cut_not_midpoint`** (the Bug-A regression).
- `test_tracks.py` — track enumeration; video playlist; producer resolution; tractor duration (incl. blanks); find entry; next id.
- `test_types.py` — dataclass shapes.
- `test_validators.py` — all validator paths.

## 2.3 Phase 3 — pyagent core (tool dispatch)

Bridges LLM tool-calls to the Phase 2 backend; returns `(exit_code, response_dict)`.

### `phase3_pyagent_core/runtime.py`
- `list_tools() -> list[dict]` — every tool's metadata as JSON: `name` (`pyagent_*`), `label`, `description`, `op`, `is_mutating`, `parameters_schema` (properties only), `required`.
- `OP_TABLE: dict[str,str]` — op name → backend method name (32 entries; `list_catalog` handled specially).
- `MUTATING_OPS: frozenset[str]` — runtime auto-saves after any of these (or `save`).
- `_ALLOWED_CATALOG_KINDS = ("effects","transitions","generators")`.
- `_run_list_catalog(args, catalog_path) -> (int, dict)`.
- `_to_jsonable(obj) -> Any` — coerces Phase-2 dataclasses to JSON-safe dicts.
- `emit(response) -> None` — writes **exactly one JSON line** to stdout + flush.
- `run_op(op, args, project_path, catalog_path) -> (int, dict)`:
  - `0` success → `{"ok":True,"result":...}`
  - `1` validation error → `{"ok":False,"error":...}` (LLM self-corrects via `fix:`)
  - `2` fatal → `{"ok":False,"fatal":True,"error":...}` (unknown op / unreadable project / `BackendError` / generic `Exception`)

### `phase3_pyagent_core/__main__.py`
- `main(argv=None) -> int` — argparse: positional `op`, `--project` (req), `--catalog` (req), `--args-json` (default `{}`). On JSON-decode error → emit fatal, return 2. Else `run_op` + write JSON. Invoked: `python3 -m phase3_pyagent_core <op> --project P --catalog C --args-json '{...}'`.

### `phase3_pyagent_core/catalog_slice.py`
- `DEFAULT_KINDS = ("effects","transitions","generators")`.
- `build_catalog_slice(catalog: dict|str|Path, kinds=DEFAULT) -> str` — newline-joined `"{mlt_service} | {kdenlive_id} | {name} | {description}"`.

### `phase3_pyagent_core/phase3_types.py` — re-exports Phase 2 types.

### `phase3_pyagent_core/tools/` — the 38-tool registry
- `tools/__init__.py` — `all_tools() -> list` (asserted = **38** in tests). Canonical order: `project → catalog → bin → clips → clips_edit → transitions → effects → keyframes → track_effects → groups → markers → render_qc`.
- `tools/project.py` — `ToolDef` frozen dataclass (`name,label,description,is_mutating,parameters_schema,op="",required=()`); `GET_PROJECT_INFO`, `GET_TIMELINE_SUMMARY`.
- `tools/catalog.py` — `LIST_CATALOG` (`kind` enum, `filter`).
- `tools/bin.py` — `IMPORT_MEDIA` (`paths: array<string, minItems 1>`).
- `tools/clips.py` — `INSERT_CLIP`, `APPEND_CLIP`, `MOVE_CLIP`, `TRIM_CLIP`, `DELETE_CLIP`.
- `tools/clips_edit.py` — `SLIP_CLIP`, `RIPPLE_DELETE_CLIP`, `CHANGE_CLIP_SPEED`, `SPLIT_CLIP`, `REPLACE_CLIP_SOURCE`, `SET_CLIP_SPEED_RAMP`.
- `tools/transitions.py` — `ADD_TRANSITION`, `REMOVE_TRANSITION`, `SET_TRANSITION_PROPERTY`.
- `tools/effects.py` — `APPLY_EFFECT`, `REMOVE_EFFECT`, `GET_EFFECT_PARAM`, `SET_EFFECT_PARAM`.
- `tools/keyframes.py` — `LIST_KEYFRAMES`, `SET_KEYFRAME`, `REMOVE_KEYFRAME`.
- `tools/track_effects.py` — `ADD_EFFECT_TO_TRACK`, `LIST_TRACK_EFFECTS`.
- `tools/groups.py` — `GROUP_CLIPS`, `UNGROUP_CLIPS`, `LIST_GROUPS`.
- `tools/markers.py` — `ADD_MARKER`, `SAVE_PROJECT`.
- `tools/render_qc.py` — 6 Phase-6 tools (`op=""`): `RENDER`, `GET_THUMBNAIL`, `GET_QC_CROP`, `LIST_BLACK_FRAMES`, `LIST_SILENCE`, `GET_AUDIO_LEVELS`.

### `phase3_pyagent_core/extension.ts` — the pi/OpenCode extension (transport into Python)
Loads tool defs via `runtime.list_tools()` (Python subprocess), registers with pi. Routes backend tools through `python3 -m phase3_pyagent_core`, Phase-6 tools through `phase6_render_qc.*`, and (if `PYAGENT_LIVE=1`) mutating tools through Phase 5 D-Bus.
Key functions/types: `ToolDef` (TS mirror), `buildTypeBoxSchema(def)` (wraps properties-only schema with `Type.Object(...,{additionalProperties:false})`), `loadToolDefs()`, `resolveProjectPath/CatalogPath/LiveSyncDir/RenderQcDir`, `liveSyncEnabled()` (`PYAGENT_LIVE==="1"`), `liveApply(toolName,args)`, `callPhase6(module,args)`, `loadSystemPrompt(catalogPath)` (replaces `{{CATALOG_SLICE}}`), `toToolResult(rr)`, `runRuntime(op,args,project,catalog)`, `callRuntime(op,args,ctx)` (auto-save after mutating; `confirm` when `!PYAGENT_AUTO_APPROVE`), `phase6Handler(name)`. Default export appends system prompt + registers all tools.

### `phase3_pyagent_core/system_prompt.md`
Injected into pi. Identity block ("You are PyAgent…"), hard rules (never shell to ffmpeg/melt; never hand-edit `.kdenlive`; `effect_id`/`kind` must come from catalog; `get_timeline_summary()` before planning; state intent before mutating; retry on `fix:` up to 3×), a **Transport-limit** section (keep each tool result small — no raw XML / whole-file dumps; use compact `get_timeline_summary()` JSON), Phase 5 live mode (`PYAGENT_LIVE=1`), Phase 6 QC flow, tool summary, and the `{{CATALOG_SLICE}}` placeholder.

### Phase 3 tests
- `test_runtime.py` — dispatch as subprocess: unknown op → fatal(2); missing project → fatal; read ops vs demo; mutating chain; list_catalog kinds/filter.
- `test_extension.py` — mutating-set coverage; humanize; system prompt (slice >100 lines, placeholder present).
- `test_integration.py` — pi RPC integration (skipped unless LLM env set).
- `tests/test_golden_io.py` — golden-file lock for 19+ (op,args) pairs; `_compare_key_subset` skips volatile keys (`uuid/name/path/transition_id`…).
- `tests/test_tools.py` — `test_all_tools_count_is_38`, unique names, required fields.
- Fixtures: `tests/fixtures/{demo.kdenlive, catalog.json, golden_io.json, make_demo.py}`.

## 2.4 Phase 4 — chat UI

A companion web app (FastAPI + vanilla JS, no build step) beside Kdenlive.

### `phase4_chat_ui/app.py`
- `_REPO_ROOT`, `DEFAULT_CATALOG = _REPO_ROOT/phase1_knowledge_base/catalog.json`.
- `_bootstrap_default_session(project) -> Session`.
- `create_app(project, provider="opencode-go", model="minimax-m3", pi_binary=None, catalog=None, default_app="piagent") -> FastAPI` — builds `ChatConnectionManager`, `session_state`, `sessions_cache`, `WsHandler`; mounts `/static`; routes: `GET /` (index.html), `GET /api/project` (`{project,info,summary}`), `GET /api/apps`, `POST /api/plan/{approved|rejected}`. `websocket("/ws")`.
- `lifespan`: `start_watching`, `cleanup_stale_uploads`, periodic cleanup.

### `phase4_chat_ui/__main__.py`
- `main(argv=None) -> int` — argparse `--project` (req), `--host` (127.0.0.1), `--port` (8765), `--provider` (opencode-go), `--model` (minimax-m3), `--pi-binary`; `uvicorn.run`.

### `phase4_chat_ui/types.py`
- `ChatMessage(role, content, tool_name=None, timestamp=0, images=[])`; `PlanCard(plan_id, summary, diff, status="pending")`; `PiEvent(kind, role?, text?, tool?, args?, result?, error?, cost?)` — normalized event kinds: message, message_delta, thinking, tool, plan, error, cost, done.

### `phase4_chat_ui/state.py`
- `get_project_info(project, catalog=None) -> dict|None`, `get_timeline_summary(project, catalog=None) -> dict|None` (thin wrappers over Phase 3 `run_op`).

### `phase4_chat_ui/session.py`
- `MAX_HISTORY=500`, `DEFAULT_APP="piagent"`. `Session` (`history`, `pending_plan`, `last_project_state`, `cost_usd`): `to_dict`/`from_dict`, atomic `save()`, `load()`, `add_user_message`, `add_assistant_message`, `add_tool_event`, `set_pending_plan`/`resolve_plan`/`clear_pending_plan`, `set_project_state`.

### `phase4_chat_ui/pi_client.py`
- `PiClient(provider, model, project, binary=None, session_id="pyagent-chat", pi_args=None)` — spawns `pi --mode json --print --session-id <id>`, parses JSON lines into `PiEvent`s. `async run_prompt(text, image_paths?)` (forces PATH; sets `PYAGENT_PROJECT`, `PYAGENT_LIVE=1`, `PYAGENT_AUTO_APPROVE=false`; 1900s timeout), `stop()`, `_normalize`, `_parse_message`, `_extract_cost`.

### `phase4_chat_ui/uploads.py`
- `save_base64_image(data_url) -> str` (validates ext/size; raises `ValueError`); `cleanup_stale_uploads(max_age_hours=1)`; `periodic_cleanup(interval_sec=1800)`.

### `phase4_chat_ui/watcher.py`
- `async watch_project(project, on_change, poll_delay_ms=200, mtime_window_sec=1.0)` — `watchfiles.awatch` on project's parent dir; fires on project mtime change or matching sibling write (within window); tolerates rename (OSError = just renamed).

### `phase4_chat_ui/adapters/` — agent adapter protocol & two impls
- `adapters/__init__.py` — `AgentAdapter` (Protocol: `app_id, session_id, run_prompt, list_models, stop, available`), `build_adapter(app_id, model, project, session_id)`, `list_apps()`, `_APP_NAMES`.
- `adapters/_registry.py` — `_APP_REGISTRY = {"piagent": PiAgentAdapter, "opencode": OpenCodeAdapter}`.
- `adapters/piagent.py` — `PiAgentAdapter` wraps `PiClient`, auto-appends `-e <phase3 extension.ts>`. `available()` → `shutil.which("pi")`. `list_models()` reads `~/.pi/agent/models-store.json`.
- `adapters/opencode.py` — `OpenCodeAdapter` shells `opencode run --format json --auto` and parses its JSON event stream into `PiEvent`s (the **opencode transport**; each stdout line → one `PiEvent`: `message_delta`/`tool`/`cost`/`error`/`done`). `available()` → `shutil.which("opencode")`. `list_models()` parses `opencode models`. **Note:** this adapter emits deltas as they arrive; it does not impose its own byte cap — the per-message size limit reported as "chunk exceeds the limit" comes from the upstream opencode binary, not this adapter (see §5, Bug C).

### `phase4_chat_ui/ws/` — WebSocket layer
- `ws/__init__.py` — re-exports `ChatConnectionManager`, `WsHandler`, `try_reload_kdenlive`.
- `ws/manager.py` — `try_reload_kdenlive() -> bool` (imports `phase5_dbus_sync.dbus_client`; if Kdenlive running → `clean_restart`); `ChatConnectionManager` (connect/disconnect/broadcast).
- `ws/handler.py` — `WsHandler`: `_info`/`_summary`, `broadcast_state`, `start_watching`, `_rebuild_adapter`, `_new_session`, `_send_initial_snapshot`, `ws_endpoint`, `handle(data)` (dispatch by `type`: refresh_state, reload_kdenlive, approve/reject, stop, new_session, delete_session, change_project, switch_session, set_app/model, prompt).
- `ws/handlers.py` — free-function handlers: `handle_delete`, `handle_change_project`, `handle_switch`, `handle_set` (app/model), `handle_prompt` (saves images, spawns `run()` background task), `relay(ws, ev, sess, handler)` (translates `PiEvent`→wire; after `tool` events sets `reload_needed[project]=True`).

### `phase4_chat_ui/static/`
- `index.html`, `app.js`, `style.css` — chat transcript, project-state panel, plan card, quick actions, agent/model selectors; WebSocket client at `/ws`.

### Phase 4 tests
`test_app.py` (TestClient: index, static, `/api/project`, plan approve/reject, `save_base64_image`), `test_pi_client.py` (fake pi), `test_session.py`, `test_state.py`, `test_agent_adapters.py` (Pi/OpenCode + `build_adapter`), `test_websocket.py` (full WS w/ fake pi), `test_watcher.py`, `test_task4_apps.py`, `test_task5_ui.py`, `tests/fake_pi.py`.

## 2.5 Phase 5 — D-Bus live sync

Routes mutating calls to D-Bus (live) or file backend, + reload notification.

### `phase5_dbus_sync/dbus_client.py`
- Constants: `SERVICE="org.kde.kdenlive"`, `PATH="/kdenlive/MainWindow_1"`, `INTERFACE="org.kde.kdenlive.MainWindow"`.
- `is_running() -> bool` (`pgrep -x kdenlive`), `detect_service_name() -> str|None` (`busctl --user list`).
- `KdenliveDBus` (jeepney, SESSION bus; **no-throw**, all methods return `bool`/`None`): `available`, `add_project_clip(url, folder="")`, `add_timeline_clip(url)`, `add_effect(effect_id)`, `script_render(url)`, `update_project_path(path)`, `clean_restart(clean=False)`, `exit_app()`, `has_scripting_api` (property), `insert_clip_to_track(track_index, clip_id, start_frame)`, `get_timeline_duration()`.

### `phase5_dbus_sync/live_sync.py`
- `LIVE_CAPABLE: frozenset` — **intentionally EMPTY** (Kdenlive 26.04 D-Bus live methods crash the running instance — so all mutating ops currently go file-mode + notify).
- `RELOAD_AFTER: frozenset` — the 10 mutating tools that need a reload notice. `_OP_FOR_TOOL` (pi tool → backend op).
- `notify(title, body)` (`notify-send`), `apply(tool, args, project, notifier=notify) -> dict`.
- `LiveResult(ok, mode, result, fatal)`, `.to_dict()`. `LiveSync(project_path, dbus=None, notifier=notify)`: `is_live(tool)`, `apply(tool, args) -> LiveResult` (live→D-Bus; else quit Kdenlive, apply via file backend, notify reload; `fatal` if `run_op` code 2).

### `phase5_dbus_sync/__main__.py`
- `_cmd_apply` (stdin JSON `{project,tool,args}` → `LiveSync`, exit 0/1/2), `_cmd_notify` (if running `clean_restart`+notify else notify to reopen), `main()` argparse subcommands `apply`/`notify`.

### Phase 5 tests
`test_apply_cli.py`, `test_dbus_client.py`, `test_live_sync.py`.

## 2.6 Phase 6 — render & QC

Six tools, each run as `python3 -m phase6_render_qc.<module>`, printing one JSON (exit 0 ok / 1 error).

### `phase6_render_qc/render/__init__.py`
- `_NICE_DEFAULT=10`, `_PROXY_SIZE="640x360"`. `RenderResult(ok, output_path, mode, profile, duration_sec, elapsed_sec, error)`.
- `parse_profile(kdenlive_path) -> dict` (regex `<profile>`), `parse_project_duration_sec(kdenlive_path) -> float` (`<tractor out=>`), `_profile_args(profile)` (incl. `progressive=1`, `colorspace=709`), `render(kdenlive_path, output_path, mode="proxy", in_sec=None, out_sec=None, nice_level=10) -> RenderResult` (600s timeout; `melt`).

### `phase6_render_qc/thumbnails/__init__.py`
- `MAX_LONG_EDGE=480`, `JPEG_QUALITY=70`, `MAX_BYTES=250_000`. `ThumbnailResult(ok, output_path, width, height, file_bytes, timestamp_sec, error)`.
- `_probe(path)`, `_long_edge_scale(w,h)`, `get_thumbnail(video, timestamp_sec, output)`, `get_qc_crop(video, timestamp_sec, region{x,y,w,h}, output)` (ffmpeg).

### `phase6_render_qc/audio/__init__.py`
- `DEFAULT_SILENCE_DB=-35`, `DEFAULT_SILENCE_MIN_SEC=1`. Dataclasses `AudioLevels(ok, in_sec, out_sec, rms_db, peak_db, error)`, `SilenceSpan`, `SilenceResult`.
- `get_audio_levels(video, in_sec=0, out_sec=0) -> AudioLevels` (60s), `list_silence(video, in_sec=0, out_sec=0, threshold_db=-35, min_sec=1) -> SilenceResult` (ffmpeg `astats`/`silencedetect`).

### `phase6_render_qc/black_frames/__init__.py`
- `DEFAULT_BLACK_THRESHOLD=0.10`, `DEFAULT_BLACK_MIN_SEC=0.5`. `BlackSpan`, `BlackFramesResult`.
- `list_black_frames(video, in_sec=0, out_sec=0, threshold=0.10, min_sec=0.5) -> BlackFramesResult` (ffmpeg `blackdetect`; rejects `out_sec<=in_sec`).

### `phase6_render_qc/{render,thumbnails,audio,black_frames}/__main__.py`
CLIs: argparse → call matching function → `print(json.dumps(...))`; `audio/__main__.py` has subcommand `levels|silence`.

### Phase 6 tests
`test_parsers.py` (21, no ext deps), `test_render_integration.py` (8, needs melt+ffmpeg+ffprobe+demo), `test_e2e_pipeline.py` (1, full edit→render/QC roundtrip).

## 2.7 Phase 7 — real-session e2e harness

Drives real `pi` + Kdenlive + Xvfb + chat UI WS and asserts the LLM edited the project.

### `phase7_real_session/e2e.py`
- Skipif helpers: `_has(name)`, `_has_opencode_auth()`, `_kdenlive_already_on_bus()`.
- `XvfbContext` (CM; display `:n` in [99,199]; `RuntimeError` if missing), `KdenliveLaunch` (`kdenlive --no-welcome`; `wait_ready` polls D-Bus), `ChatUIServer` (`python3 -m phase4_chat_ui`; `wait_ready` polls `/api/project`).
- `read_timeline_state(project_path=None) -> dict` — XML-parse → `{"transitions":[...]}`; **source of truth** for verifying edits (KdenliveDBus is write-only). Raises `RuntimeError`/`FileNotFoundError`.
- Process helpers `_terminate_proc`, `_pick_free_port`.

### `phase7_real_session/ws_client.py`
- `WSClient(url, timeout=180)`: `connect`, `close`, `send_prompt(text) -> list[dict]` (collects until `status:"ready"`/`done`), `run_prompt_sync`. Single event loop per instance.

### `phase7_real_session/{xvfb.py, skipif.py, __init__.py}`
- `xvfb.py` — standalone `XvfbContext`.
- `skipif.py` — re-export shim `_has/_has_opencode_auth/_kdenlive_already_on_bus`.
- `__init__.py` — docstring only.

### Phase 7 tests
`tests/test_e2e.py` — `TestReadTimelineStateParser` (3) + `TestE2EPiSession` (gated by `@skipUnless` on pi/kdenlive/Xvfb/dbus-send/opencode-auth, `@skipIf` on existing kdenlive-on-bus). Two pytest-skips: `test_groups_round_trip_through_real_kdenlive`, `test_2b_round_trip_through_real_kdenlive` (kdenlive CLI has no headless open+save; melt drops `kdenlive:*` props).

## 2.8 The 38-tool surface (master table)

Read-only (13): `get_project_info`, `get_timeline_summary`, `list_catalog`, `get_effect_param`, `list_keyframes`, `list_track_effects`, `list_groups`, `get_thumbnail`, `get_qc_crop`, `list_black_frames`, `list_silence`, `get_audio_levels`, plus `GET_*` mirror tools. (Verified: 25 mutating / 13 read-only.)

| Tool (pyagent_*) | op | mutating | required args | purpose |
|---|---|---|---|---|
| `get_project_info` | `get_project_info` | no | — | project metadata |
| `get_timeline_summary` | `get_timeline_summary` | no | — | compact JSON of tracks/clips/transitions/markers |
| `list_catalog` | `list_catalog` | no | `kind` | effect/transition/generator lookup (+`filter`) |
| `import_media` | `import_media` | yes | `paths[]` | add files to bin → source ids |
| `insert_clip` | `insert_clip` | yes | `track_index, position_sec, source_id` | place clip at position |
| `append_clip` | `append_clip` | yes | `track_index, source_id` | place at track end |
| `move_clip` | `move_clip` | yes | `clip_id, new_track, new_position_sec` | relocate |
| `trim_clip` | `trim_clip` | yes | `clip_id, new_in_sec, new_out_sec` | set in/out |
| `delete_clip` | `delete_clip` | yes | `clip_id` | remove |
| `add_transition` | `add_transition` | yes | `clip_a_id, clip_b_id` | crossfade at the cut (+`kind`,`duration_sec`) |
| `remove_transition` | `remove_transition` | yes | `transition_id` | remove |
| `set_transition_property` | `set_transition_property` | yes | `transition_id, prop_name, value` | tweak transition |
| `apply_effect` | `apply_effect` | yes | `clip_id, effect_id` | add effect (+`params`) |
| `remove_effect` | `remove_effect` | yes | `clip_id, effect_index` | remove effect |
| `get_effect_param` | `get_effect_param` | no | `clip_id, effect_index, param_name` | read param |
| `set_effect_param` | `set_effect_param` | yes | `clip_id, effect_index, param_name, value` | set param (clobbers keyframes) |
| `list_keyframes` | `list_keyframes` | no | `clip_id, effect_index, param_name` | list keyframes |
| `set_keyframe` | `set_keyframe` | yes | `clip_id, effect_index, param_name, frame, value` | add/update keyframe (+`type`) |
| `remove_keyframe` | `remove_keyframe` | yes | `clip_id, effect_index, param_name, frame` | remove keyframe |
| `add_effect_to_track` | `add_effect_to_track` | yes | `track_index, effect_id` | track-level effect |
| `list_track_effects` | `list_track_effects` | no | `track_index` | track effect stack |
| `slip_clip` | `slip_clip` | yes | `clip_id, delta_sec` | shift source in/out |
| `ripple_delete_clip` | `ripple_delete_clip` | yes | `clip_id` | delete + shift followers |
| `change_clip_speed` | `change_clip_speed` | yes | `clip_id, rate` | set warp_speed (0.1–10) |
| `split_clip` | `split_clip` | yes | `clip_id, at_sec` | split in two |
| `replace_clip_source` | `replace_clip_source` | yes | `clip_id, new_source_id` | swap source |
| `set_clip_speed_ramp` | `set_clip_speed_ramp` | yes | `clip_id, keyframes[]` | timeremap |
| `group_clips` | `group_clips` | yes | `clip_ids[], group_name` | group |
| `ungroup_clips` | `ungroup_clips` | yes | `group_name` | ungroup |
| `list_groups` | `list_groups` | no | — | list groups |
| `add_marker` | `add_marker` | yes | `position_sec, label` | marker/guide/chapter |
| `save_project` | `save` | yes | `path?` | write `.kdenlive` |
| `render` (qc) | `""` | yes | `mode, output` | melt proxy/final |
| `get_thumbnail` (qc) | `""` | no | `video, timestamp_sec, output` | capped JPEG |
| `get_qc_crop` (qc) | `""` | no | `video, timestamp_sec, region, output` | 1:1 crop |
| `list_black_frames` (qc) | `""` | no | `video` | blackdetect |
| `list_silence` (qc) | `""` | no | `video` | silencedetect |
| `get_audio_levels` (qc) | `""` | no | `video` | RMS/peak dB |

## 2.9 System prompt & error contract

**Hard rules (from `system_prompt.md`):** never shell to ffmpeg/melt; never hand-edit `.kdenlive`; `effect_id`/`transition kind` must come from the catalog; call `get_timeline_summary()` before planning; state intent in one sentence before mutating (or `PYAGENT_AUTO_APPROVE=true`); on `fix:`-hinted error, fix & retry, stop after 3 attempts; **keep each tool result small** (transport per-message cap — no raw XML / whole-file dumps).

**Error contract:** every `ValidationError` message carries a `fix:` line. `run_op` exit codes: `0` ok, `1` validation (LLM self-corrects), `2` fatal (unknown op / unreadable project / backend error / unexpected exception).

---

# 3. Cross-cutting: data model, error model, transport

**Data model flow (PyAgent):**
```
catalog.json (Phase 1) ──► Catalog ──► name validation in ops/*
                                       └─► system_prompt catalog slice
.kdenlive ──► load_project ──► ProjectTree ──► ops/* mutate ──► save_project
TimelineSummary / dataclasses ──► runtime._to_jsonable ──► emit (one JSON line)
```

**Error model:** `BackendError` base → `ValidationError` (fix:-hinted, exit 1) / `NotFoundError` / `CatalogError` (both fatal, exit 2). Plus `RuntimeError`/`FileNotFoundError`/`ValueError` in harness/util layers.

**Transport:** LLM (in pi/OpenCode) → `extension.ts` → `python3 -m phase3_pyagent_core <op> --project --catalog --args-json` → `run_op` → one JSON line on stdout. Phase 6 tools → `phase6_render_qc.*`. Live mode (`PYAGENT_LIVE=1`) mutating ops → `python3 -m phase5_dbus_sync apply`. **Per-message size cap:** the opencode binary streams one message per tool call with a hard cap; overflow → "Separator is not found, chunk exceeds the limit" (see Bug C, §5). Mitigation: compact `get_timeline_summary()` JSON, never paste raw XML.

---

# 4. How to build, run, test

### Go pipeline
```bash
cd /home/ah64/apps/mlt-pipeline
go test ./...                                   # build + run all Go tests
go build -o bin/analyze ./cmd/analyze && ...    # or build individually
./edit.sh ~/Videos/my-raw-clips                 # one-shot: symlink → run.sh → open Kdenlive
./run.sh my-clip [--force] [--render]           # analyze→agent→compile→render
```

### PyAgent (Python)
```bash
cd /home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide
pip install -e phase3_pyagent_core phase4_chat_ui phase5_dbus_sync phase6_render_qc phase7_real_session
# Run a single tool:
PYTHONPATH=. python3 -m phase3_pyagent_core get_timeline_summary \
    --project /home/ah64/Videos/edit.kdenlive \
    --catalog phase1_knowledge_base/catalog.json
# Launch chat UI:
PYTHONPATH=. python3 -m phase4_chat_ui --project /path/to/edit.kdenlive --port 8765
# Env knobs: PYAGENT_PROJECT, PYAGENT_LIVE=1, PYAGENT_AUTO_APPROVE=true
# Tests:
PYTHONPATH=. python3 -m pytest phase2_project_engine phase3_pyagent_core phase4_chat_ui phase6_render_qc -q
# Phase 7 e2e (needs real kdenlive/pi/opencode):
PYTHONPATH=. python3 -m pytest phase7_real_session -q
```
> Note: run `pytest` from the **guide root** (`pyagent-kdenlive-guide`), not from inside `phase4_chat_ui` — the latter shadows stdlib `types` with a local `types.py` and breaks imports.

**Test counts:** Go ≈ 20+ (unit/e2e). Python: Phase 2 ≈ 130 cases, Phase 3 ≈ 40, Phase 4 ≈ 40, Phase 6 ≈ 30, plus Phase 7 gated e2e. README claims ~127 tests across phases. Full run reported clean: **202 passed, 1 skipped** at last verification.

---

# 5. Known bugs & limitations

### Fixed bugs (see `BUGS_FIXED.md` for full log)
- **Bug A — `add_transition` midpoint vs cut:** previously centered at `(a_out + b_in)/2` (b_in sources' in-point=0) → wrong position; now centers on `cut = a_out`. `phase2_project_engine/ops/transitions.py`. Regression: `test_add_transition_centers_on_cut_not_midpoint`.
- **Bug B — `import_media([])` silent `{}`:** empty/blank paths now raise `ValidationError` with a `fix:` line. `phase2_project_engine/ops/bin.py`. Regression: `test_import_media_rejects_empty_paths_list`. (Golden `set_transition_property.previous_value` updated 01.500→03.500 to match corrected transition position.)
- **Bug C — "Separator is not found, chunk exceeds the limit":** NOT a backend bug. Originates in the compiled **opencode binary**'s transport (hard per-message size cap). Triggered by pasting the full 71KB `.kdenlive` XML / giant single-turn histories. Mitigated via the `system_prompt.md` "keep each tool result small" rule (use `get_timeline_summary()`, never dump XML). The opencode binary itself (`~/.opencode/bin/opencode`) cannot be patched from this repo.
- Many earlier bugs (track misroute, video-playlist detection, tractor duration with blanks, catalog-default params, simplekeyframe guard, track-effect tools registration, phase-4 watcher false positives, phase-6 audio/timeout/black-frames) are logged in `BUGS_FIXED.md`.

### Limitations
**Go pipeline (v1):** `dissolve` not supported (cut/fade only); single-tractor; no captions/music/voiceover; footage must be local; profile from `Clips[0]` only (no mixed resolution); `.mlt` opens in Kdenlive as *Untitled* (save for a real project).
**PyAgent:** manual reload unless `PYAGENT_LIVE=1` (and even then, live D-Bus editing is disabled — `LIVE_CAPABLE` is empty, so it's file-write + notify); QC is sanity-only (not broadcast-grade); no native in-Kdenlive dock (Phase 8 stretch, deferred); Phase 7's fork track (Phase 7 in `PHASE_7_*.md`) deferred because upstream Kdenlive already exposes the D-Bus methods Phase 5 uses.

---

# 6. Glossary

- **EDL** — Edit Decision List; the Go-pipeline AI's output (`edl.json`).
- **MLT** — Media Lovin' Toolkit; the framework Kdenlive + `melt` render through. XML dialect = `.mlt` / `.kdenlive`.
- **`.kdenlive`** — Kdenlive project file = MLT XML + `kdenlive:`-namespaced metadata (gives it a real name & reloadable project state).
- **catalog** — `catalog.json` built by Phase 1 from Kdenlive/MLT XML defs; the allowed `effect_id`/`transition kind` set.
- **PyAgent** — the Python tool-calling process + chat UI that edits `.kdenlive` files.
- **EditorBackend** — the abstract interface (Phase 2) behind which file/D-Bus backends sit.
- **op / tool** — an operation; `op` is the internal backend method name, `tool` is the `pyagent_*` LLM-facing name.
- **fix:** hint — a machine-readable suffix on `ValidationError` messages enabling LLM self-correction.
- **Live mode** — `PYAGENT_LIVE=1`; routes mutating tools to Kdenlive D-Bus (currently file-write + notify, since `LIVE_CAPABLE` is empty).
- **QC** — Quality Control; Phase 6 render + black-frame/silence/audio-level/thumbnail checks.
- **D-Bus fork (D-Ogi/kdenlive)** — a patched Kdenlive with 108 scriptable methods; referenced by `.agents/` but not adopted (deferred).
