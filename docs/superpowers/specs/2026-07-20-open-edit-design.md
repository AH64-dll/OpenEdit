# Open Edit — Design

**Status:** Approved (brainstorming complete)
**Date:** 2026-07-20
**Stack:** Python 3.11+, Pydantic v2, SQLite, FastAPI, Rust (sandbox, seccomp+landlock), lxml, melt/ffmpeg/ffprobe, OpenCode Go binary
**Outcome target:** an `Open Edit` project that ingests raw video files, lets the AI edit them via a structured IR, and renders to MP4 via `melt`. No Kdenlive is involved in the critical path.

## 1. Goal

A local, AI-native video editing platform that **replaces Kdenlive entirely**. The user works directly with raw video files (no `.kdenlive` project files, no editor application), chats with an AI agent (powered by OpenCode + any OpenCodeGo-subscription model), which edits a structured Intermediate Representation (IR) backed by SQLite. The user reviews the result in a chat + form-based UI, can undo/reorder/fine-tune any edit, and the system renders to MP4 via `melt`.

This is an **evolution of `pyagent-kdenlive-guide/`** (the "PyAgent" system), not a rewrite. The new project lives at `/home/ah64/apps/mlt-pipeline/open_edit/` as a sibling to the existing `pyagent-kdenlive-guide/`. We reuse what works (tool dispatch, chat UI, catalog, render, QC), replace what doesn't (the Kdenlive XML backend), add what's missing (the new IR, free-form Python mode, the style memory system).

**The whole purpose of this redesign is edit freedom and high capability.** The IR must be expressive enough that the AI can do anything a human editor can do with Kdenlive — and more, via free-form Python in the sandbox. We are not building a constrained tool surface; we are building the freedom layer above the render pipeline.

The v1 demo (no Kdenlive anywhere in the path):
1. User runs `open_edit init` in a folder of raw video files (e.g. `~/Videos/myproject/*.mp4`).
2. System ingests them as content-addressed assets (`ffprobe` for metadata, SHA-256 for identity).
3. User runs `open_edit chat`; browser opens to a chat + form UI.
4. User types: "arrange the clips in alphabetical order and fade out the last 2 seconds."
5. Agent emits a JSON array of `AddClipOp` (one per video) + `AddEffectOp` + `SetKeyframeOp` (structured, Tier 1).
6. System applies ops to the edit graph, derives the timeline, renders to MP4, runs QC.
7. User reviews the preview, clicks "undo" if needed; the timeline re-derives.

The 11 Arabic video files the user has on disk are still useful as test fixtures — **copied as raw files into `testdata/raw_videos/`**, with a hand-constructed edit graph `testdata/expected_edit_graph.json` defining the same 11-clip / 10-transition timeline. We do **not** import a `.kdenlive` file. The legacy `.kdenlive` importer is a **v2 compatibility shim** for users with existing Kdenlive projects; it is not in the v1 critical path.

## 2. Architecture (the 2-layer IR)

```
projects/<id>/
├── edit_graph.db       # SQLite: edits, jobs tables
├── assets/<hh>/<hash>  # content-addressed by SHA-256
├── renders/<hash>.mp4  # keyed by edit-graph canonical-JSON hash
└── thumbs/

~/.open-edit/
├── style_profile.json  # Style Memory (§14); chmod 600
├── style_profile_vN.json.bak  # last 3 versions for rollback
└── taste.db            # taste_events, pruned after rollup
```

Two layers:

1. **Edit Graph** — the source of truth. SQLite, append-only, every op has a stable UUID + `parent_id` + `author` + `status` (applied/reverted/superseded). This is what undo/reorder/fine-tune operate on.
2. **Timeline State** — derived projection. Re-computed by replaying non-reverted ops through `apply.py` whenever the edit graph changes. This is what MLT XML is emitted from.

MLT XML is a *render target*, not the artifact. The user never edits MLT directly. The AI never edits MLT directly (it emits IR ops that get serialized to MLT at render time).

## 3. Decisions (locked in during brainstorming)

| Dimension | Decision | Why |
|---|---|---|
| Editable artifact | Edit-graph DB (SQLite) | Stable UUIDs, append-only, undo/reorder/fine-tune all work |
| UI | Form-based + chat (no canvas) | "We don't use the editor" — minimal HTML5 preview + sliders/dropdowns |
| AI emission default | **Structured ops** (Tier 1) | Keeps the IR as source of truth; only escalate to free-form when structured can't express |
| Free-form Python | Tier 2 (escalation only) | Free-form ops MUST emit structured summary children so Timeline State stays accurate and undo works |
| Raw MLT XML | Tier 3 (escape hatch) | One-off cases; parsed into synthetic ops via ingest parser |
| Sandbox | Rust + seccomp + landlock (Linux only) | Production-grade isolation; strace-first allowlist (§6.8) |
| OS | Linux only | Matches current state; user-confirmed |
| AI models | Any OpenCodeGo subscription model | OpenCode handles versioning + provider switching; we don't pin |
| AI framework | PyAgent (existing) + OpenCode Go binary | Don't rebuild the agent loop or LLM abstraction |
| Concurrency | In-flight job lock in `jobs` table | Single sandbox run at a time; second chat message queues or rejects |
| Audio | First-class: `SetAudioGainOp`, `NormalizeAudioOp`; `track_kind: "audio"` enum | The source project is narrated; audio must not ride along inside video |
| Style Memory | Bounded, tag-gated, rollup-and-prune (§14) | Tastes biased over time without unbounded growth |
| v1 demo | `open_edit init` on a folder of raw videos, then chat "arrange + fade out 2s" via structured ops | No Kdenlive in the critical path; raw video → IR → render end-to-end |
| `.kdenlive` import | **v2 / optional** compatibility shim | Replaces the v1 demo; not load-bearing for the new system |

## 4. Reuse from `pyagent-kdenlive-guide/`

| Existing component | Reuse strategy | Why |
|---|---|---|
| `phase3_pyagent_core/extension.ts` (TypeScript OpenCode extension) | **Keep, minor edit** | This IS the agent loop. Add one new tool registration: `pyagent_run_python` for the sandbox. |
| `phase3_pyagent_core/tools/*.py` (38 Python tool wrappers) | **Repoint** to new IR API | Tools keep their `pyagent_*` names; bodies call `open_edit.ir.api.*` instead of `KdenliveFileBackend` |
| `phase3_pyagent_core/runtime.py` (tool dispatch) | **Keep** | Already works |
| `phase3_pyagent_core/system_prompt.md` | **Edit** | Add the new operations schema; keep the "keep results small" rule (Bug C mitigation) |
| `phase4_chat_ui/` (FastAPI chat + WebSocket + adapters) | **Keep, extend** | Add form-based parameter editor; style profile panel; edit history list |
| `phase1_knowledge_base/` (MLT YAML catalog) | **Keep** | The structured-op catalog seed |
| `phase6_render_qc/` (melt/ffmpeg/ffprobe/blackdetect/silencedetect) | **1:1 port** to `open_edit/qc/` | Already correct; just move it |
| `phase2_project_engine/ops/` (transitions.py, clip.py, bin.py math) | **Wrap as `apply.py`** | Reuse the *math*, replace the *XML output* (Kdenlive namespaces → clean MLT) |
| `phase5_dbus_sync/` (live editor sync) | **Drop** | No editor to sync with |
| `phase7_real_session/` (Xvfb e2e tests) | **Reshape** to scenario eval (no Xvfb) | Test against the IR directly |
| `~/.opencode/bin/opencode` (Go binary) | **Keep** | The agent loop |
| `/home/ah64/Videos/edit.kdenlive` (11 Arabic clips, 10 luma transitions) | **Test fixture source only** — copied as raw video files into `testdata/raw_videos/`. The `.kdenlive` file is not parsed; a hand-constructed edit graph defines the timeline. | Provides realistic test data without depending on Kdenlive |

## 5. Lessons from old code (load-bearing)

Three concrete bugs from `pyagent-kdenlive-guide/` that the new design must get right:

1. **Bug A: transition centering.** Old `phase2_project_engine/ops/transitions.py` centered a transition on the *midpoint* of the two clips instead of the *cut*. The user's `edit.kdenlive` golden file (kept as a reference, not as a v1 input) encoded the wrong position (00:00:01.500 instead of 00:00:03.500). **New `apply.py` places the transition at `cut = clip_a.out_point_sec` and back-solves `clip_a.out = cut - duration/2`, `clip_b.in = cut + duration/2`.** Unit test required. This is a property of the IR's `apply_operation` function — independent of any `.kdenlive` parsing.

2. **Bug B: empty paths silently accepted.** Old `bin.py` accepted `paths=[]`. **New `AssetStore.ingest()` (and any future `ImportAssetOp`) validates non-empty `paths` and raises a structured `ValidationError` with a `fix:` line.** Regression test required. This applies whether the assets come from `init` (folder scan) or from the v2 `.kdenlive` importer.

3. **Bug C: chunk exceeds limit.** Old `system_prompt.md` already has the "keep each tool result small" rule. **New design keeps that rule and adds: any new tool that returns timeline state must return a compact `get_timeline_summary()` JSON, never raw XML.** New tools added in this redesign are audited against this rule at registration. Root cause is the compiled `~/.opencode/bin/opencode` binary's per-message cap — not patchable from this repo.

## 6. Components

### 6.1 New: `open_edit/ir/types.py` — Pydantic Operation types

All operations are immutable Pydantic models with stable UUIDs.

```python
# Discriminated union on `kind`. Each subclass sets `kind: Literal[...]`.
# Use Pydantic's `Field(discriminator="kind")` on the parent Union.

class Operation(BaseModel):
    edit_id: str = Field(default_factory=new_id)
    parent_id: Optional[str] = None
    author: Literal["ai", "user"]
    timestamp: str = Field(default_factory=now_iso8601)
    status: Literal["applied", "reverted", "superseded"] = "applied"
    kind: str  # discriminator; each subclass overrides

# --- Core editing ---
class AddClipOp(Operation):
    kind: Literal["add_clip"] = "add_clip"
    asset_hash: str
    track_id: str
    track_kind: Literal["video", "audio"] = "video"
    position_sec: float
    in_point_sec: float = 0.0
    out_point_sec: Optional[float] = None
    clip_id: str = Field(default_factory=new_id)

class RemoveClipOp(Operation):
    kind: Literal["remove_clip"] = "remove_clip"
    clip_id: str

class MoveClipOp(Operation):
    kind: Literal["move_clip"] = "move_clip"
    clip_id: str
    new_track_id: str
    new_position_sec: float

class TrimClipOp(Operation):
    kind: Literal["trim_clip"] = "trim_clip"
    clip_id: str
    new_in_point_sec: float
    new_out_point_sec: float

class AddTransitionOp(Operation):
    kind: Literal["add_transition"] = "add_transition"
    clip_a_id: str
    clip_b_id: str
    transition_type: Literal["luma", "dissolve", "wipe", "fade", "cut"]
    duration_sec: float

# --- Effects & keyframes ---
class AddEffectOp(Operation):
    kind: Literal["add_effect"] = "add_effect"
    target_kind: Literal["clip", "track"]
    target_id: str
    effect_type: str  # MLT service ID, e.g. "volume", "brightness", "luma"
    params: dict      # validated against effect catalog (§6.1.1)
    effect_id: str = Field(default_factory=new_id)

class SetKeyframeOp(Operation):
    kind: Literal["set_keyframe"] = "set_keyframe"
    effect_id: str
    param: str
    keyframes: list[tuple[float, float, str]]  # (time_sec, value, interp)
    # interp ∈ {"discrete", "linear", "smooth"}  (matches MLT's interpolation types)

# --- Audio (first-class) ---
class SetAudioGainOp(Operation):
    kind: Literal["set_audio_gain"] = "set_audio_gain"
    clip_id: str
    gain_db: float
    keyframe_op_id: Optional[str] = None  # if part of a fade, points to SetKeyframeOp

class NormalizeAudioOp(Operation):
    kind: Literal["normalize_audio"] = "normalize_audio"
    target_kind: Literal["clip", "track", "project"]
    target_id: str
    target_dbfs: float = -16.0  # default for narration

# --- Grouping (parent pointer) ---
class GroupEditsOp(Operation):
    kind: Literal["group_edits"] = "group_edits"
    edit_ids: list[str]
    label: str

# --- Escape hatches (must produce structured children) ---
class RawMltXmlOp(Operation):
    kind: Literal["raw_mlt_xml"] = "raw_mlt_xml"
    xml: str
    description: str
    # On application, this is parsed by the MLT XML Ingest Parser
    # into synthetic child operations (AddEffectOp, SetKeyframeOp, etc.)
    # The raw XML is preserved for transparency.

class FreeFormCodeOp(Operation):
    kind: Literal["free_form_code"] = "free_form_code"
    code: str
    # On application, the code runs in the Rust sandbox and calls the IR API.
    # Each API call appends a child op with parent_id = this op's edit_id.
    # The code is preserved for transparency.
    # If the script produces no child ops, this op is rejected at apply time.
```

#### 6.1.1 Effect catalog

The structured-op catalog is **the load-bearing piece** of Phase 1. It defines which `effect_type` strings are valid, what their `params` shape is, and which `interp` values they accept. Phase 1 must:

- Seed from `phase1_knowledge_base/` MLT YAMLs
- Cover at minimum: `volume`, `brightness`, `contrast`, `saturation`, `panner`, `eq`, `gain`, `delay`, `luma` (transition effect), `dissolve`
- Cover audio effects required for the v1 demo: `volume`, `panner`, `gain`
- Reject unknown effect types at validation time with a `fix: use one of: <list>` line

**Catalog entry schema** (one YAML file per effect, in `open_edit/ir/catalog/effects/`):

```yaml
# open_edit/ir/catalog/effects/volume.yaml
name: volume
mlt_service: volume           # the actual MLT service ID
target_kind: [clip, track]    # where this effect can be applied
params:
  gain:
    type: float
    default: 1.0
    range: [0.0, 4.0]
    unit: linear              # 1.0 = unity, 0.0 = silence
  duration_s:
    type: float
    default: null             # null = instantaneous; >0 = ramp duration
    range: [0.0, 10.0]
keyframe_params: [gain]       # which params accept SetKeyframeOp
interp: [linear, discrete]    # legal interp values for keyframes on this effect
description: "Audio volume control. gain=1.0 is unity."
```

**Risk:** catalog completeness. If the v1 demo needs an effect not in the catalog, Phase 1 is not done. Mitigation: audit the catalog against the 11-clip project's actual effects *before* declaring Phase 1 done.

### 6.2 New: `open_edit/storage/edit_graph.py` — SQLite edit graph store

```sql
-- schema.sql (one .db file per project, at ~/.open-edit/projects/<id>/edit_graph.db)

CREATE TABLE IF NOT EXISTS project_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS edits (
    edit_id TEXT PRIMARY KEY,
    parent_id TEXT,
    kind TEXT NOT NULL,
    author TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('applied', 'reverted', 'superseded')),
    sequence_num INTEGER NOT NULL,
    payload TEXT NOT NULL,
    FOREIGN KEY (parent_id) REFERENCES edits(edit_id)
);
CREATE INDEX IF NOT EXISTS idx_edits_sequence ON edits(sequence_num);
CREATE INDEX IF NOT EXISTS idx_edits_parent ON edits(parent_id);
CREATE INDEX IF NOT EXISTS idx_edits_status ON edits(status);

-- Concurrency lock: at most one sandbox run at a time
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,        -- 'free_form_python' | 'render' | 'migration'
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);

PRAGMA journal_mode = WAL;     -- concurrent reads while writing
PRAGMA foreign_keys = ON;
```

API:
- `EditGraphStore.append(op, sequence_num=None) -> int` — append op, return seq num
- `EditGraphStore.load_all() -> list[OperationUnion]` — load all in sequence order
- `EditGraphStore.update_status(edit_id, new_status)` — for undo/redo/supersede
- `EditGraphStore.reorder(edit_id_a, edit_id_b)` — swap adjacent ops' `sequence_num`
- `JobLock.try_acquire(kind) -> Optional[str]` — returns `job_id` or `None` if busy
- `JobLock.release(job_id, status, error=None)`

### 6.3 New: `open_edit/storage/assets.py` — content-addressed asset store

```python
ASSET_DIR = Path("~/.open-edit/assets")
# Layout: ~/.open-edit/assets/<sha256[:2]>/<sha256>
```

- `AssetStore.ingest(source_path) -> Asset` — SHA-256, copy to CAS, ffprobe for metadata
- `AssetStore.get(asset_hash) -> Optional[Asset]` — read from CAS
- Asset metadata fields: `asset_hash, original_path, stored_path, type, duration_sec, fps, width, height, codec, has_audio`

### 6.4 New: `open_edit/ir/apply.py` — wraps existing Phase 2 math

Pure functions: `(Timeline, Operation) -> Timeline`.

- `_apply_add_clip`: locate or create track, append clip
- `_apply_add_transition` — **Bug A fix**: place transition at `cut = clip_a.out_point_sec`, back-solve `clip_a.out = cut - duration/2`, `clip_b.in = cut + duration/2`. **Reject** if `duration_sec > min(clip_a.duration_remaining, clip_b.duration_consumed)`.
- `_apply_remove_clip`, `_apply_move_clip`, `_apply_trim_clip` — straightforward
- `_apply_add_effect`: append to `clip.effects` or `track.effects`
- `_apply_set_keyframe`: validate `effect_id` exists, set `keyframes[param]`
- `_apply_free_form_code`: invoke sandbox (§6.8), collect child ops, set `parent_id`, apply each
- `_apply_raw_mlt_xml`: invoke ingest parser (§6.5.2), collect child ops, set `parent_id`, apply each

`derive_timeline(project) -> Timeline`:
- Replay all non-reverted ops in `sequence_num` order
- Memoize the result with a cache key = SHA-256 of the canonical JSON of the edit graph
- Invalidate on any `edits` or `jobs` table write

### 6.5 New: `open_edit/render/emitter.py` — clean MLT XML

Emit `<tractor><multitrack><playlist>...</playlist></multitrack></tractor>`. **No Kdenlive namespaces.** All MLT constructs used in the new design are documented in MLT's reference; if a new construct is needed, add it to the emitter and document the schema.

```python
def emit_timeline(timeline: Timeline) -> str:
    """Return a complete MLT XML document string for the given timeline."""
```

Subcomponents:
- `emitter.py` — main entry point
- `profiles.py` — render profile (resolution, fps, codec) selection
- `validators.py` — verify emitted XML loads in `melt -consumer xml:` (no parse errors)

#### 6.5.1 Ingest parser (`open_edit/render/ingest.py`)

Strict, narrow parser. Recognizes a subset of MLT XML and emits structured ops. **Rejected**: Kdenlive-namespaced properties, custom interpolation curves, multi-tractor nesting. On rejection, raises `IngestError` with the offending tag/attribute.

### 6.6 New: `open_edit/render/orchestrator.py` — calls melt, manages cache

```python
def render_project(project_id: str) -> RenderResult:
    timeline = derive_timeline(project.load())
    xml = emit_timeline(timeline)
    edit_graph_hash = canonical_json_hash(project.edit_graph)
    cached = cache.get(edit_graph_hash)
    if cached and cached.fresh():
        return RenderResult(path=cached.path, qc=qc.gate(cached.path))
    xml_path = write_xml(project, xml)
    mp4_path = melt_render(xml_path)
    cache.put(edit_graph_hash, mp4_path)
    return RenderResult(path=mp4_path, qc=qc.gate(mp4_path))
```

Cache key: SHA-256 of **canonical JSON** of the edit graph (sorted keys, no whitespace, sorted lists). Inconsistencies in JSON serialization must not cause cache misses.

### 6.7 Port: `open_edit/qc/` — from `phase6_render_qc/`

1:1 port. Same files, new location:
- `qc/black_frames.py` — `ffmpeg ... -vf blackdetect ...`
- `qc/silence.py` — `ffmpeg ... -af silencedetect ...`
- `qc/thumbnail.py` — `ffmpeg ... -frames:v 1 ...`
- `qc/gate.py` — runs all 5 checks, returns `QCReport` JSON:
  ```json
  {
    "passed": true,
    "checks": [
      {"name": "mlt_load", "passed": true, "detail": ""},
      {"name": "proxy_render", "passed": true, "detail": "/path/to/proxy.mp4"},
      {"name": "black_frames", "passed": true, "detail": "0 black frames"},
      {"name": "silence", "passed": true, "detail": "0 silent gaps > 1s"},
      {"name": "thumbnail", "passed": true, "detail": "/path/to/thumb.jpg"}
    ]
  }
  ```

### 6.8 New: `open_edit/sandbox/` — Rust subprocess jail

**Linux-only.** Two-layer isolation:
1. **`landlock` filesystem jail** — read-only access to `/usr/`, the global asset store, the Python stdlib. Read-write access strictly to the project's workdir. With `--with-hwaccel` flag, also allows `/dev/dri/*` and `/dev/shm` for VAAPI/DRM.
2. **`seccomp` syscall allowlist** — built from observed syscalls in Phase 0, not from documentation.

**Phase 0 prerequisite:** before writing any Rust, run `strace -f -c` against the existing pipeline (melt + ffmpeg + ffprobe) on the 11-clip project. Concrete commands:

```bash
# melt: render a 5-second slice of the imported project to a temp file
strace -f -c -o open_edit/sandbox/observations/strace_melt.txt \
  melt /tmp/probe.mlt -consumer avformat:/tmp/probe.mp4 vcodec=libx264 acodec=aac

# ffmpeg: transcode a 5-second slice
strace -f -c -o open_edit/sandbox/observations/strace_ffmpeg.txt \
  ffmpeg -y -i /home/ah64/Videos/edit.kdenlive -t 5 -c:v libx264 -c:a aac /tmp/probe.mp4

# ffprobe: get metadata
strace -f -c -o open_edit/sandbox/observations/strace_ffprobe.txt \
  ffprobe -show_streams /home/ah64/Videos/edit.kdenlive
```

The allowlist is derived from these observations, not from documentation. The `strace_*.txt` files are checked in as test fixtures so the allowlist can be regression-tested against drift.

CLI:
```
open-edit-sandbox --code <path> --workdir <path> --timeout 30 --mem 512M [--with-hwaccel]
```

Hard time + memory limits. Network blocked. Subprocess tree killed on timeout.

The Python code that runs in the sandbox imports `open_edit.ir.api as ir` and calls methods like `ir.add_clip(...)`, `ir.trim_clip(...)`. Each call appends a structured op to a temp buffer. On sandbox exit, the buffer is read by `apply.py` and the ops are appended to the edit graph with `parent_id` = the `FreeFormCodeOp.edit_id`.

**Fallback:** if Phase 3 (sandbox) blows past 3 weeks, fall back to **firejail** for v1, harden to Rust/seccomp in v1.1.

### 6.9 New: `open_edit/agent/` — IR API exposed as OpenCode tools

This is the layer `extension.ts` calls. It is a thin Python wrapper that:
- Defines the IR API for free-form Python (sandbox side)
- Defines the 38 (or fewer) `pyagent_*` tool wrappers that the agent calls (extension side)

Most existing `phase3_pyagent_core/tools/*.py` wrappers get **repointed**: their bodies swap from `KdenliveFileBackend.<op>()` to `open_edit.ir.api.<op>()`. The wrapper signatures, JSON schemas, and `pyagent_*` names stay the same so `extension.ts` doesn't change.

New tools added:
- `pyagent_run_python` — invokes the sandbox
- `pyagent_get_style_profile` — returns the active style profile slice
- `pyagent_set_pinned_value` — manages the pinned values block

### 6.10 Keep + extend: FastAPI chat UI

`phase4_chat_ui/` stays. Extensions:
- **Form-based parameter editor** — when the agent emits `AddEffectOp` or `SetKeyframeOp`, the form shows sliders/dropdowns for each param. The user can apply as-is, modify, or cancel. *On Apply*, the form diffs `proposed_params` vs form state and writes a `taste_event` (see §14).
- **Style profile panel** — read-only view of `~/.open-edit/style_profile.json`, plus Reset and Pin controls.
- **Edit history list** — vertical list of operations (kind, label, author, timestamp, status badge). Right-click: undo, redo, fine-tune, supersede.
- **HTML5 preview player** — shows the latest `renders/<hash>.mp4`. Black-frame and silence markers on the scrub bar.

### 6.11 v2: `open_edit/migration/kdenlive_to_ir.py` — legacy importer (NOT v1)

> **v2 / optional compatibility shim.** Not in the v1 critical path. Listed here for completeness because some existing PyAgent users have `.kdenlive` projects they may want to bring over.

Parse a `.kdenlive` file (XML), emit an equivalent edit graph. Steps:
1. Parse the inner MLT XML.
2. For each `<entry>`: emit an `AddClipOp`.
3. For each `<transition>`: emit an `AddTransitionOp`. **Apply the Bug A fix here**: if the transition is centered on the midpoint (old wrong behavior), reject with a `fix: <explanation>` and offer to re-import with the corrected cut position.
4. For each `<filter>`: emit an `AddEffectOp` + `SetKeyframeOp` if keyframes present.
5. Validate the resulting graph against the effect catalog. Reject unknown effect types.

The importer also imports the audio narration as a first-class audio track, not a side-effect of video.

### 6.12 New: `open_edit/style/` — Style Memory (see §14)

Three files:
- `taste_events.py` — schema + read/write of the `taste_events` table
- `aggregate.py` — rule-based rollup (no LLM)
- `retrieve.py` — tag-gated retrieval for prompt injection

## 7. Data flow

### 7.1 User makes an edit via chat (v1 demo path)

```
1. User: "fade the last 2 seconds to black"
2. OpenCode receives the message. The TypeScript extension (`extension.ts`) registers `pyagent_*` tools with OpenCode's tool-calling layer. The chat protocol is whatever OpenCode uses (JSON-RPC between the LLM and `extension.ts`); we don't build it.
3. OpenCode LLM (any OpenCodeGo model): emits a JSON array of operations
   [
     {"kind": "add_effect", "target_kind": "clip", "target_id": "clip_N",
      "effect_type": "volume", "params": {"gain": 0.0, "duration_s": 2.0}},
     {"kind": "set_keyframe", "effect_id": "fx_X", "param": "gain",
      "keyframes": [[(duration-2, 1.0, "linear"), (duration, 0.0, "linear")]]}
   ]
4. open_edit.ir.validate: Pydantic schema + referential integrity + effect catalog
5. open_edit.ir.apply: appends ops to edit_graph.db in a transaction
6. open_edit.ir.derive_timeline: re-computes Timeline (cached by edit-graph hash)
7. open_edit.render.orchestrator: emits MLT XML, calls melt → preview.mp4
8. open_edit.qc.gate: runs 5 checks
9. Phase 4 chat UI: streams result back via WebSocket
   {"type": "edit_applied", "ops": [...], "render_path": "...", "qc": {...}}
10. User: clicks "undo" → op marked "reverted", timeline re-derived, render re-done
```

### 7.2 AI escalates to free-form Python (Tier 2)

When structured ops can't express the edit, the LLM emits:
```json
{"kind": "free_form_code", "code": "..."}
```

`apply.py` handles it:
1. Write the code to a temp file in the project's workdir.
2. `JobLock.try_acquire('free_form_python')` — if busy, return "busy, agent is mid-edit" to the user.
3. Invoke `open-edit-sandbox --code <path> --workdir <project> --timeout 30`.
4. The sandbox runs the Python; the script imports `open_edit.ir.api as ir` and calls `ir.add_clip(...)`, etc.
5. Each `ir.*` call appends a structured op to a temp buffer (with `parent_id` = the FreeFormCodeOp's `edit_id`).
6. On sandbox exit, the buffer is read; ops are appended to the edit graph.
7. If the buffer is empty, the FreeFormCodeOp is **rejected** at apply time (the IR stays clean).
8. Same flow as 7.1 from step 6 onward.
9. `JobLock.release(...)`.

If validation fails (e.g. an asset hash doesn't exist), the sandbox run aborts and the user sees the error.

### 7.3 M3 risks during free-form runs

The agent should:
- Cap scripts at **100 lines** per emission. Multi-step edits → multiple `FreeFormCodeOp` chained by `parent_id`.
- Start every emitted script with: `# ir_api_version: 0.1; libs: {cv2: 4.8, ...}` (pinned in `open_edit/sandbox/allowed_libs.txt`).
- Include at least one `assert` per output (e.g. `assert 0.3 < mean_luma(frame) < 0.7`).
- After every free-form run, the agent extracts 3–5 preview frames to `projects/<id>/previews/` using `ir.extract_frames(...)` and includes them in the chat response as a "summary card" so the user can visually verify.

## 8. Style Memory (companion design)

Style Memory biases the agent's proposed parameters toward the user's established taste over time. The design below incorporates the improvements discussed in brainstorming.

### 8.1 Goal & non-goals

**Goal:** bias the agent's proposed parameters (and its choice among structurally equivalent options) toward the user's established taste, so repeat edit types need less correction.

**Non-goals:** full behavior cloning, storing raw timelines/footage, multi-user profiles, making the profile a decision-maker. The profile is a *prior* the agent leans on, not a rule it must follow.

**Budget:** style profile ≤ 5000 tokens stored; ~150–250 tokens injected per agent turn. Storage and per-turn cost are decoupled.

### 8.2 Architecture

```
taste_events (SQLite, append-only)
  ~/.open-edit/taste.db
       │
       │ aggregate() — rule-based, batch, every 10 ops or on project close
       ▼
style_profile.json (≤5000 tok, versioned)
  ~/.open-edit/style_profile.json
  ~/.open-edit/style_profile_vN.json.bak  (last 3 versions)
       │
       │ retrieve(op_type) — tag-gated slice
       ▼
agent turn (Phase 4 prompt, ~150-250 tokens injected)
```

`style_profile.json` is `chmod 600`. `taste.db` is disposable after rollup — the edit graph is the durable record.

### 8.3 Event schema (`taste_events` table)

| Field | Type | Notes |
|---|---|---|
| id | UUID | |
| ts | timestamp | |
| project_id | text | for future per-project weighting; v1 ignores |
| op_type | text | `AddTransition`, `AddEffect`, `SetKeyframe`, etc. |
| proposed_params | JSON | what the agent emitted |
| final_params | JSON | what was actually applied |
| action | enum | `applied_unmodified` \| `applied_modified` \| `reverted` |
| correction_note | text, optional | free-text user feedback (e.g. "too long", "wrong color") |

**Action enum reduced from the original draft.** `rejected` is dropped — `reverted` already covers the negative signal, and the form-based UI doesn't have a clean "reject before apply" path.

**`correction_note` is optional.** The form shows a 1-line text input next to the parameter sliders. If filled, the note is included in the event. If empty, the event is recorded without it. This gives the user a low-friction way to teach the system *why* a correction was made, not just *that* it was made.

### 8.4 Signal weighting

| Action | Weight | Why |
|---|---|---|
| `applied_modified` (override) | 5 | Strongest signal — user actively corrected a specific value |
| `reverted` | −3 | Negative signal against the proposed choice |
| `applied_unmodified` | **0** | Indifference is not endorsement. (Was 1 in the original draft; reduced to 0 — indifference is noise, not signal.) |

Overrides are the field that actually teaches the profile something specific; everything else mostly just confirms or denies defaults.

### 8.5 Style profile schema

```json
{
  "meta": {
    "version": 12,
    "updated_at": "2026-07-20",
    "sample_size": 143,
    "window": "90d_or_200events"
  },
  "transitions": {
    "preferred": ["luma", "cross_dissolve"],
    "avoid": ["star_wipe"],
    "default_duration_s": 0.8,
    "confidence": 0.7,
    "examples": [
      {"proposed": "1.2s dip_to_black", "final": "0.8s cross_dissolve"},
      {"proposed": "1.0s luma", "final": "0.6s luma"}
    ]
  },
  "fades": {
    "default_in_s": 0.5,
    "default_out_s": 1.8,
    "tendency": "shortens agent-proposed fades ~30%",
    "confidence": 0.65,
    "examples": [{"proposed": "2.5s", "final": "1.8s"}]
  },
  "pacing": {
    "agent_avg_clip_s": 5.2,
    "user_avg_clip_s": 3.8,
    "ratio": 0.73,
    "tendency": "user cuts agent-proposed clips by ~27%",
    "confidence": 0.6,
    "examples": []
  },
  "color": {
    "tendency": "warm, +6-8 saturation",
    "confidence": 0.4,
    "examples": []
  },
  "audio": {
    "music_preference": "low-bed under narration, ducked -12dB on voice",
    "voice_leveling": "normalizes to -16 LUFS",
    "confidence": 0.5
  },
  "text_captions": {
    "style": "bold sans, bottom-third, high contrast outline",
    "timing": "syncs to sentence boundaries, not word-by-word",
    "confidence": 0.55
  },
  "visual_treatment": {
    "recurring_effects": ["scanline_overlay_light", "chromatic_aberration_subtle"],
    "confidence": 0.5,
    "note": "applied to intros/outros more than mid-content"
  },
  "structure": {
    "intro_pattern": "cold open 3-5s before title card",
    "outro_pattern": "CTA card, 2-3s hold",
    "common_shape": "intro → 2-4 segments → outro"
  },
  "export": {
    "aspect_ratio": "16:9",
    "resolution": "1080p",
    "confidence": 0.6
  },
  "corrections": {
    "most_overridden_param": "fade_duration",
    "direction": "shorter",
    "note": "agent tends to overshoot durations across the board"
  },
  "pinned": {
    "fades.default_out_s": 1.8,
    "_doc": "manually locked values; checked before profile defaults, before LLM defaults"
  }
}
```

**Examples schema.** Each entry in a category's `examples` array is `{"proposed": dict, "final": dict, "weight": int}`. The `proposed` and `final` dicts are full parameter objects (e.g. `{"effect_type": "luma", "duration_s": 1.2}`). The `weight` is the absolute value of the `applied_modified` weight (always 5 in v1) times the magnitude of the diff. Eviction is by lowest `weight` — the most distinctive examples survive.

**Pacing corrected.** The original draft had `avg_clip_length_s: 4.2` — a descriptive stat with no clear action. The schema now stores `agent_avg_clip_s`, `user_avg_clip_s`, and `ratio` so the agent gets a direct *correction* signal: "you propose 5.2s, the user keeps it at 3.8s — correct down by 27%."

### 8.6 Aggregation algorithm (rule-based, no LLM)

Runs every **10** applied ops, or on project close (whichever comes first).

1. Pull events from `taste_events` within the rolling window: last 90 days, capped at 200 events.
2. Per category, compute weighted stats using §8.4's weights.
3. From `applied_modified` events, extract the highest-|weight| proposed→final diffs as `examples`. **Cap at 4 per category; a new entry evicts the lowest-weighted example** (not the oldest — the most distinctive examples should survive). Distinctiveness scored by diff magnitude and weight.
4. `confidence = min(weighted_sum / 50, 1.0)` — weighted, not raw count. 10 strong overrides (10 × 5 = 50) reach full confidence. Weak signals accumulate slowly.
5. **No M3 call.** The `notes` field is regenerated rule-based (e.g. "user shortens agent-proposed fades ~30%") from the stats. The optional M3 call from the original draft is **dropped for v1** — it adds a per-rollup model cost, the `notes` field is not load-bearing, and it introduces a model into the aggregation path that can be biased.
6. Serialize. If over 5000 tokens, trim in this order: lowest-confidence category's examples first, then that category's `note` field, never the core numeric defaults.
7. Increment `meta.version`, write `style_profile.json`, write `style_profile_v<prev>.json.bak` (keep last 3), delete rolled-up events from `taste_events`.

### 8.7 Pin precedence

When the user pins a value (e.g. "fades always 1.8s"), the precedence is:

**`pinned` > `user_override_in_form` > `profile_default` > `LLM_default`**

- If the LLM proposes something different from the pin, the pin wins.
- If the user *manually* overrides the pin in the form (e.g. sets a fade to 2.5s despite the pin), the override is applied **and** logged as an `applied_modified` event. If **5** overrides accumulate against a single pin key, the style profile panel shows a "Pin weakened — 5 overrides, consider unpinning?" notice. The pin itself stays in place; only the user can remove it. (v1 has no auto-removal — that's a v2 feature.)
- `pinned` values are stored in the `pinned: {}` block of `style_profile.json` and never touched by aggregation.

### 8.8 Retrieval / injection (Phase 4 hook)

A static tag map decides which profile categories are relevant to which op type:

```python
TAG_MAP = {
    "AddTransition": ["transitions", "corrections"],
    "AddEffect":      ["fades", "color", "visual_treatment", "corrections"],
    "SetKeyframe":    ["fades", "color", "corrections"],
    "AddClip":        ["pacing", "corrections"],
    "MoveClip":       ["pacing", "corrections"],
    "TrimClip":       ["pacing", "corrections"],
    "SetAudioGain":   ["audio", "corrections"],
    "NormalizeAudio": ["audio", "corrections"],
}
```

Only the matching slice(s) plus the `corrections` meta block (always included — cheap, and it's the general "agent tends to overshoot X" signal) get injected into `prior_state` for that turn. Target: 150–250 tokens per turn regardless of how large the stored profile grows.

Below `confidence < 0.2`, the category is omitted entirely from injection — avoids premature false confidence during cold start.

### 8.9 UI hooks (Phase 5)

- **Read-only Style Profile panel** — pretty-printed JSON, matches the form-based / no-canvas philosophy.
- **Reset button** — clears `style_profile.json` and `taste.db`.
- **Pin control** — for any numeric default, the user can lock it; aggregated defaults won't overwrite.
- **Override-diff log on Apply** — the form's Apply button writes a `taste_event` to `taste.db` automatically. The user doesn't need to do anything extra.
- **Optional 1-line correction note** — text input next to the parameter sliders, included in the event if filled.

### 8.10 Failure modes

| Failure | Mitigation |
|---|---|
| Cold start, no data | Below `confidence < 0.2`, category omitted from injection; agent uses its own defaults |
| One anomalous project skews the profile | Rolling window (90d) bounds exposure; `project_id` in schema for future per-project split |
| Taste drifts over time | 90-day window ages out old signal each rollup |
| Noisy/conflicting signal | Low confidence score → agent treats value as soft suggestion, not hard default |
| Profile creeping past budget | Hard trim step in aggregation (§8.6.6) |
| Bad rollup corrupts the profile | `style_profile_vN.json.bak` (last 3 versions) for manual rollback |
| Privacy of taste data | `style_profile.json` is `chmod 600`; readable only by the user |

## 9. Testing

### 9.1 Layers

| Layer | Tool | What it covers |
|---|---|---|
| Unit | `pytest open_edit/ir open_edit/storage open_edit/style` | Pydantic schema, edit graph CRUD, derivation math, commutativity, aggregation |
| Integration | `pytest open_edit/render open_edit/qc` | MLT emit, melt load, QC checks against a fixture project |
| Sandbox | `cd sandbox && cargo test` | seccomp allowlist, landlock FS jail, timeout, network blocked, hwaccel path |
| E2E (no agent) | `pytest open_edit/migration` | `kdenlive_to_ir` against the 11-clip golden file; output is a valid edit graph |
| Agent canary (manual) | `bash scripts/v1_demo.sh` | End-to-end: import + chat + structured fade + render + undo |

### 9.2 Fixtures

```
testdata/
├── raw_videos/                # 11 Arabic video files copied from the user's
│                             #   /home/ah64/Videos/edit.kdenlive/footage/ — raw, no .kdenlive
├── expected_edit_graph.json   # hand-constructed 11-clip / 10-transition graph
├── expected_timeline.json     # what derive_timeline should produce
├── expected_mlt.xml           # what emitter should produce (byte-diff, Phase 2)
├── expected_qc_report.json    # what qc.gate should produce (Phase 2)
└── sandbox_observations/
    ├── strace_melt.txt        # Phase 0 strace output (committed fixture)
    ├── strace_ffmpeg.txt
    └── strace_ffprobe.txt
```

The 11 video files in `testdata/raw_videos/` are copied from the user's actual footage (e.g. `/home/ah64/Videos/edit.kdenlive/footage/*.mp4`) and treated as **read-only** in tests. The `expected_edit_graph.json` is **hand-constructed** — it does not parse any `.kdenlive` file. This keeps the v1 critical path free of Kdenlive parsing while still exercising the IR against realistic 11-clip / 10-transition data.

**For v1 Phase 1, the test contract is:** given the 11 raw videos and the hand-constructed `expected_edit_graph.json`, `derive_timeline()` produces a Timeline that, when serialized via `apply.py`, contains the same 11 clips and 10 transitions as the hand-constructed graph (within ±0.05s tolerance for durations, ±0.1s for transition cut positions).

### 9.3 Load-bearing tests

`open_edit/ir/tests/test_apply.py`:
- **Bug A regression:** `test_add_transition_centers_on_cut_not_midpoint` — already exists in `phase2_project_engine/tests/test_ops_transitions.py`; port and extend to cover the new IR.
- **Bug B regression:** `test_add_asset_rejects_empty_paths` — already exists in `phase2_project_engine/tests/test_ops_bin.py`; port.
- `test_undo_marks_reverted` — reverted ops are no-ops in `derive_timeline`.
- `test_reorder_swaps_adjacent_ops` — commutativity predicate.
- `test_free_form_code_requires_children` — empty buffer → op rejected.
- `test_audio_track_first_class` — AddClipOp with `track_kind="audio"` is a first-class clip, not a side-effect.

`open_edit/style/tests/test_aggregate.py`:
- `test_applied_unmodified_weight_zero` — indifference is not signal.
- `test_eviction_keeps_highest_weighted` — example cap eviction is by weight, not by recency.
- `test_confidence_weighted_not_raw` — 10 strong overrides > 20 weak signals.
- `test_pin_precedence` — pin > user override > profile > LLM default.
- `test_cold_start_omits_low_confidence` — confidence < 0.2 → category omitted from injection.

`open_edit/sandbox/tests/test_jail.rs`:
- Reading `/etc/passwd` → blocked.
- Network socket creation → blocked.
- `melt` / `ffmpeg` / `ffprobe` → allowed.
- Writing outside workdir → blocked.
- `--with-hwaccel` flag → `/dev/dri` access granted.

### 9.4 Concurrency test

`open_edit/storage/tests/test_joblock.py`:
- Two concurrent `JobLock.try_acquire('free_form_python')` calls — one succeeds, one returns `None`.
- The losing call surfaces a "busy" message to the user; no silent failure.

## 10. Error handling

### Detected and recovered automatically

- Schema errors in agent emission → Pydantic rejects, agent retries (max 3).
- Referential integrity errors (unknown asset hash, unknown clip id) → rejected with `fix: <suggestion>`.
- Unknown effect type → rejected with `fix: use one of: <list>`.
- Empty paths in asset import → rejected (Bug B regression).
- MLT XML parse error in `melt` → caught, surfaced with `fix: <line>`.
- QC failure → surfaced in chat, agent retries with the QC report.
- Sandbox timeout → killed, traceback surfaced, op not applied.
- Sandbox producing no children → op rejected at apply time.
- Render cache miss / corruption → fallback to fresh render.

### Detected only by user (must step in)

| Failure | How it surfaces | Recovery |
|---|---|---|
| Catalog missing an effect the user needs | "Unknown effect type" at apply time | Add the effect to the catalog, retry |
| Imported `.kdenlive` (v2 only) has Bug A transition centering | Importer rejects with `fix:` | Re-import after the upstream tool produces correct XML, or use the importer's "fix on import" mode |
| Style profile becomes misaligned with new project type | "Profile confidence low" indicator in panel | Reset profile; or per-project profile (v2) |
| Sandbox allowlist missing a syscall a legitimate tool needs | Sandbox exits with `EPERM` | Add the syscall to the allowlist after strace verification |
| OpenCode binary version drift | `extension.ts` fails to register | Pin OpenCode version in README; update extension.ts |

## 11. Out of scope (v2 / deferred)

- **Cross-fade via `xfade` filter** (v1 supports `luma`, `dissolve`, `wipe`, `fade`, `cut` transitions only).
- **Captions / subtitles burn-in** beyond the `text_captions` taste profile.
- **Multi-tractor (nested tracks)** in MLT.
- **Music / voiceover generation** (free-form Python can do this, but no model integration yet).
- **Distributed / multi-machine render.**
- **Per-project style profiles** (schema has `project_id`; v1 ignores it).
- **Tauri desktop shell** (v1 is web UI only; Tauri is a v2 option if a native window is needed).
- **Multi-user / collaboration.**
- **Style profile `notes` field via M3 call** (dropped for v1; revisit in v2 if `notes` becomes load-bearing).
- **`rejected` event action** (dropped for v1; the form-based UI doesn't have a clean reject-before-apply path).
- **`.kdenlive` importer** (`open_edit/migration/kdenlive_to_ir.py`) — listed in §6.11 but **not in v1**; this is a v2 compatibility shim for users with existing Kdenlive projects.

## 12. Build order / Phase plan

Each phase leaves the system in a stable, working state.

### Phase 0 — Scaffold + observation (1 day)

- New `open_edit/` package next to `pyagent-kdenlive-guide/`. uv workspace. `pyproject.toml`.
- `git submodule add` or copy the reusable parts of `pyagent-kdenlive-guide/phase6_render_qc/` to `open_edit/qc/`.
- `strace -f -c melt /tmp/probe.mlt -consumer avformat:/tmp/probe.mp4 ... > open_edit/sandbox/observations/strace_melt.txt`.
- `strace -f -c ffmpeg -i /home/ah64/Videos/edit.kdenlive -t 5 ... > open_edit/sandbox/observations/strace_ffmpeg.txt`.
- `strace -f -c ffprobe -show_streams /home/ah64/Videos/edit.kdenlive > open_edit/sandbox/observations/strace_ffprobe.txt`.
- Confirm hwaccel is or isn't in scope by running the same straces with and without `-vaapi_device /dev/dri/renderD128` flags.

**Done when:** `open_edit/` exists; strace fixtures checked in; reusable parts copied.

### Phase 1 — IR + SQLite + audio (1 week)

- `open_edit/ir/types.py` — all Pydantic operation types from §6.1, including audio ops.
- `open_edit/storage/edit_graph.py` — SQLite schema with `edits`, `jobs`, `PRAGMA journal_mode = WAL`.
- `open_edit/storage/assets.py` — content-addressed store + ffprobe metadata.
- `open_edit/ir/apply.py` — wraps existing `phase2_project_engine/ops/` math. **Bug A and Bug B fixes are here.**
- `open_edit/ir/derive_timeline.py` — memoized by canonical-JSON hash.
- `open_edit/ir/validate.py` — schema + referential + effect catalog.
- `open_edit/ir/commutativity.py` — `can_swap(op_a, op_b) -> bool`.
- `open_edit/cli.py` — `create-project, add-clip, add-effect, set-keyframe, list, undo, summary`.
- `open_edit/style/taste_events.py` — schema + CRUD for the events table.
- **Catalog audit** — run through the 11-clip project's effects, ensure all are covered.
- Unit tests: schema, derivation, commutativity, Bug A + Bug B regressions, job lock, audio first-class.

**Done when:** `python -m open_edit.cli create-project --name demo` creates a project, the 11-clip project imports successfully via `kdenlive_to_ir`, undo works, all unit tests pass.

### Phase 2 — MLT emit + render + QC (1 week)

- `open_edit/render/emitter.py` — Timeline → clean MLT XML.
- `open_edit/render/profiles.py` — render profile selection.
- `open_edit/render/validators.py` — emitted XML loads in `melt -consumer xml:`.
- `open_edit/render/ingest.py` — strict, narrow parser for raw MLT fragments (Tier 3).
- `open_edit/render/orchestrator.py` — calls melt, manages render cache.
- `open_edit/render/cache.py` — canonical-JSON hash key.
- `open_edit/qc/{black_frames,silence,thumbnail,gate}.py` — ported 1:1 from `phase6_render_qc/`.
- Integration tests: emitter output byte-diffs against `testdata/expected_mlt.xml`; `melt` loads it; QC gate produces `expected_qc_report.json`.

**Done when:** `python -m open_edit.cli render <project>` produces an MP4 from a fixture project; QC gate runs all 5 checks; cache hit/miss works.

### Phase 3 — Rust sandbox (2–3 weeks)

- `sandbox/Cargo.toml` + `sandbox/src/main.rs` + `jail.rs` + `allowlist.rs`.
- Allowlist derived from Phase 0 strace fixtures, not from documentation.
- `--with-hwaccel` flag for `/dev/dri` access.
- CLI: `open-edit-sandbox --code <path> --workdir <path> --timeout 30 --mem 512M [--with-hwaccel]`.
- Sandbox tests: /etc/passwd blocked, network blocked, melt/ffmpeg/ffprobe allowed, write outside workdir blocked, hwaccel path.
- `open_edit/agent/sandbox_bridge.py` — Python wrapper that invokes the binary, parses the child's IR-API ops buffer.
- **Fallback:** if 3-week budget slips, fall back to **firejail** for v1, harden to Rust/seccomp in v1.1.

**Done when:** `cargo test` passes; `pyagent_run_python` tool can run a 50-line script that calls `ir.add_clip()` and produces a child op in the edit graph.

### Phase 4 — Tool repointing + Style Memory + form UI (1 week)

- `extension.ts` extended with one new tool: `pyagent_run_python`.
- Existing 38 `pyagent_*` tool wrappers repointed to `open_edit.ir.api.*`. Names + JSON schemas unchanged.
- `open_edit/agent/style_retrieve.py` — tag-gated retrieval per §8.8.
- `open_edit/agent/style_inject.py` — builds the `prior_state` block for the system prompt.
- `open_edit/style/aggregate.py` — rule-based rollup, every 10 ops or on project close (§8.6).
- `open_edit/style/retrieve.py` — public API for the agent loop.
- `phase4_chat_ui` form-based parameter editor: sliders/dropdowns for `AddEffectOp` / `SetKeyframeOp`, optional correction_note text input.
- `phase4_chat_ui` style profile panel: read-only JSON view, Reset button, Pin controls.
- `phase4_chat_ui` edit history list: undo/redo/supersede controls.
- Unit tests: aggregation, retrieval, pin precedence, eviction policy, confidence weighted vs. raw.

**Done when:** the agent receives a tag-gated slice of the style profile; the form's Apply writes a `taste_event`; the rollup runs on schedule; `chmod 600` on the profile.

### Phase 5 — v1 demo (1 week)

> **No `.kdenlive` in the v1 critical path.** The 9-step v1 demo runs end-to-end on raw video files.

- `scripts/v1_demo.sh` — end-to-end script:
  1. User runs `open_edit init` in a folder of raw video files (e.g. `~/Videos/myproject/*.mp4`).
  2. System scans the folder, ingests each file via `AssetStore.ingest()` (SHA-256, ffprobe).
  3. User runs `open_edit chat`; browser opens to the chat + form UI.
  4. User types "arrange the clips in alphabetical order and fade out the last 2 seconds".
  5. Agent emits `AddClipOp` (one per video, in alphabetical order) + `AddEffectOp` (volume) + `SetKeyframeOp` (linear fade from 1.0 to 0.0). All structured (Tier 1). No sandbox invoked.
  6. IR applies ops to `edit_graph.db`, derives Timeline.
  7. Render orchestrator emits MLT XML, calls `melt`, produces `preview.mp4`. QC gate runs 5 checks.
  8. User reviews the preview, clicks "undo" if needed. Timeline re-derives, re-renders.
  9. All 5 QC checks pass.
- Agent canary test: `bash scripts/v1_demo.sh` is the manual acceptance test.

**Done when:** the 9-step v1 demo passes end-to-end on a folder of raw video files. **"Round-trip without loss" means specifically:**

- The 11 test videos are ingested as 11 distinct assets (each with a unique SHA-256, ffprobe metadata).
- The hand-constructed `expected_edit_graph.json` (11 clips, 10 transitions) is applied to the IR, and `derive_timeline()` produces a Timeline with the same 11 clips and 10 transitions (positions within ±0.05s of expected).
- Bug A regression: every transition is centered on the cut, not the midpoint.
- After `ir_to_mlt` and `melt -consumer xml:` (Phase 2), the resulting XML loads without error.
- The chat-triggered fade edit produces a preview where the last 2 seconds go from full volume to silence (audio) or full brightness to black (video), verifiable in extracted frames.

**Out of Phase 5 (deferred to v2):** the `.kdenlive` importer (`open_edit/migration/kdenlive_to_ir.py`) is listed in §6.11 but is a v2 compatibility shim. It is not part of the v1 acceptance test.

## 13. Open items

1. **Per-project vs. global style profile.** v1 is global with `project_id` in the schema. If you want separate profiles per project type (e.g. educational vs. creative) from day one, say so — it changes §8.6 and §8.9.
2. **`chromatic_aberration_subtle` and other "subtle" taste descriptors** — these are imprecise. The taste profile should bias toward concrete parameter ranges (e.g. "aberration_strength ∈ [0.02, 0.05]") not aesthetic labels. May need a Phase 4.5 polish to formalize.
3. **Sandbox allowlist coverage** — Phase 0 strace will reveal what's needed. If `melt` calls `io_uring` or `bpf` syscalls (increasingly common in modern Linux), the allowlist and isolation story need more thought.
4. **M3 video input length limits** — for v1 demo (5-second fade on a small project), this is fine. For longer projects, the "extract preview frames" step in §7.3 may need to subsample.
5. **OpenCode binary version pin** — `~/.opencode/bin/opencode` should be pinned to a known version in the README. Drift in the binary's tool-calling protocol would break `extension.ts`.
6. **`.kdenlive` importer (v2)** — §6.11 documents it as a future compatibility shim. The implementation effort is roughly 1 week; defer until there's a user with an existing project to migrate.

## 14. Repo layout (target)

```
/home/ah64/apps/mlt-pipeline/
├── open_edit/                          # NEW
│   ├── pyproject.toml
│   ├── open_edit/
│   │   ├── __init__.py
│   │   ├── ir/                         # Phase 1
│   │   │   ├── types.py
│   │   │   ├── apply.py
│   │   │   ├── derive_timeline.py
│   │   │   ├── validate.py
│   │   │   ├── commutativity.py
│   │   │   └── api.py                  # in-process API for free-form Python
│   │   ├── storage/                    # Phase 1
│   │   │   ├── schema.sql
│   │   │   ├── edit_graph.py
│   │   │   ├── assets.py
│   │   │   └── job_lock.py
│   │   ├── render/                     # Phase 2
│   │   │   ├── emitter.py
│   │   │   ├── ingest.py
│   │   │   ├── profiles.py
│   │   │   ├── validators.py
│   │   │   ├── orchestrator.py
│   │   │   └── cache.py
│   │   ├── qc/                         # Phase 2 (port)
│   │   │   ├── black_frames.py
│   │   │   ├── silence.py
│   │   │   ├── thumbnail.py
│   │   │   └── gate.py
│   │   ├── sandbox/                    # Phase 3 (Rust)
│   │   │   ├── Cargo.toml
│   │   │   ├── src/
│   │   │   │   ├── main.rs
│   │   │   │   ├── jail.rs
│   │   │   │   └── allowlist.rs
│   │   │   ├── tests/
│   │   │   └── observations/           # Phase 0 strace fixtures
│   │   ├── agent/                      # Phase 4
│   │   │   ├── sandbox_bridge.py
│   │   │   ├── style_inject.py
│   │   │   └── tools/                  # thin wrappers for the 38 pyagent_* tools
│   │   ├── style/                      # Phase 4 (Style Memory)
│   │   │   ├── taste_events.py
│   │   │   ├── aggregate.py
│   │   │   └── retrieve.py
│   │   ├── migration/                  # v2 only (legacy .kdenlive import)
│   │   │   └── kdenlive_to_ir.py
│   │   └── cli.py
│   ├── tests/                          # see §9
│   └── scripts/
│       └── v1_demo.sh
├── pyagent-kdenlive-guide/             # KEEP, mostly
│   ├── phase1_knowledge_base/          # KEEP (catalog seed)
│   ├── phase2_project_engine/ops/      # WRAP (math → apply.py)
│   ├── phase3_pyagent_core/            # KEEP (extension.ts, runtime, tools, system_prompt)
│   ├── phase4_chat_ui/                 # KEEP + EXTEND (form UI, style panel, history list)
│   ├── phase5_dbus_sync/               # DROP
│   ├── phase6_render_qc/               # PORT to open_edit/qc/
│   └── phase7_real_session/            # RESHAPE (no Xvfb)
├── edit.sh                             # existing driver, may extend
├── run.sh                              # existing driver
├── docs/superpowers/specs/             # THIS FILE
└── ...
```
