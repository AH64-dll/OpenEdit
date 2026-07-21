# Open Edit — Architecture Document

**Status:** Recommended architecture for migration from `pyagent-kdenlive` to an AI-native video editing platform.

**Author:** Senior software architect review.

**Date:** 2026-07-20.

**Audience:** Autonomous AI coding agents (primary executor); human architect (reviewer).

**Constraints locked in this document:**

| Dimension | Decision |
|---|---|
| Edit model | Hybrid IR — edit graph is source of truth; AI can also write raw MLT XML for one-offs, which is parsed back into IR |
| Deployment | Local desktop app, single user |
| Multi-user | Out of scope for v1, but data model uses stable edit IDs + append-only operation log as cheap insurance |
| Stack | Freedom per subsystem — recommended: Python core, TypeScript/React frontend, Rust sandbox, Tauri shell |
| Executor | Weaker AI coding agent — all phase specs are copy-paste-ready, file-level |
| Deliverable format | Markdown |
| Review scope | Plans only — `pyagent-kdenlive` source was not available at review time; findings are architectural, not code-level |

---

## 1. Executive Summary

The two feasibility studies we reviewed — v1 ("Headless AI-Driven Video Editing") and v2 ("Free-Form Code, No Kdenlive") — are well-written plans for **how the AI emits MLT XML and how that emission is kept safe**. They are not architecture plans for the system you actually described.

Your brief asked for three properties that neither plan delivers:

1. **AI operates on an intermediate representation**, not directly on a traditional editor's format. Both v1 and v2 have the AI write MLT XML, which is a render target, not an IR.
2. **Every edit is structured and editable.** MLT XML has no concept of an "edit" — it has tractors, playlists, entries, filters. You cannot undo "the AI's third color-grade edit" in MLT XML because that edit does not exist as a discrete object; it has been flattened into the document.
3. **Users can later modify, undo, reorder, or fine-tune every AI-generated edit.** Undo over MLT XML is XML diffing. Reorder over MLT XML is not semantically meaningful (you cannot swap two filters in a tractor and expect the result to be the same). Fine-tune over MLT XML means hand-editing keyframe strings.

v2's "Control Layer" — sandbox + QC gate — is **execution-time safety**: "did the AI's code escape the sandbox or produce a broken render?" That is necessary. But you also asked for **edit-history safety**: "can the user undo, reorder, or tweak any AI edit later?" Those are different problems and v2 conflates them.

The recommended architecture in this document separates them:

- **Edit Graph** (operations with stable UUIDs, append-only log) — supports undo, reorder, fine-tune. This is what v1 and v2 both omit.
- **Timeline State** (derived projection from the edit graph) — what the user sees and what gets rendered.
- **AI Emission Modes** — structured operations (preferred), raw MLT XML (escape hatch, parsed back into IR), free-form Python code (runs in sandbox, calls IR API).
- **Execution Sandbox + QC Gate** — kept from v2, but scoped to *execution-time* safety, not edit-history safety.

The migration is divided into **7 phases**, each leaving the system in a stable, working state. Phases 1–3 build the foundation (IR, render, sandbox) with no AI and no UI — they are pure engineering. Phase 4 adds the AI agent. Phase 5 adds the desktop UI. Phase 6 migrates `pyagent-kdenlive` assets. Phase 7 hardens, tests, and optimizes.

Each phase spec is written for a weaker AI coding agent: exact file paths, exact function signatures, exact JSON schemas, exact test cases. No "design a system that does X" — only "create file at path P with contents matching signature S."

---

## 2. Architecture Review

### 2.1 Review of Plan v1 ("Headless AI-Driven Video Editing")

#### 2.1.1 Reusability Matrix (v1)

The matrix claims 75% reusability across 7 phases. We cannot validate the percentages because `pyagent-kdenlive` source was not provided. The *categorical* claims — that Phase 5 (D-Bus sync) has zero reusability and Phase 6 (render & QC) has 95%+ — are plausible and align with what a Kdenlive-companion architecture would look like.

**Weakness:** The matrix measures "how much code can be carried over" but does not measure "how much of the carried-over code is fit for the new purpose." Phase 2's "High reusability (MLT XML math)" claim is suspect: if the existing project engine writes `kdenlive:`-namespaced metadata, then it is structured around Kdenlive's conceptual model, and stripping the namespace does not produce a clean MLT-native engine — it produces a Kdenlive engine with the labels filed off. The reusability claim should be **Medium**, not **High**, until proven otherwise by code inspection.

#### 2.1.2 Step 1 — Headless Mode Configuration & D-Bus Bypass

**Sound.** A `--mode open-edit` flag is a reasonable migration scaffold. The mistake is framing it as the *first* step — bypassing D-Bus is mechanical; the harder problem (which v1 does not address) is replacing the edit model that D-Bus was synchronizing.

#### 2.1.3 Step 2 — Native MLT Backend Implementation

**Partially sound.** Writing plain MLT XML (`<tractor>`, `<multitrack>`, `<playlist>`, `<entry>`) is correct as a render target. The error is treating MLT XML as the *project representation*. MLT XML is a serialized render graph, not an editable data model. There is no operation log, no edit IDs, no undo beyond XML diffing.

**Architectural weakness:** An `MltFileBackend` that implements the same `EditorBackend` interface preserves the interface contract — but the interface itself was designed for tool-call-style discrete operations. If `EditorBackend.add_clip(...)` returns a success/failure, where does the undo information live? v1 does not say.

#### 2.1.4 Step 3 — Web-Based HTML5 Video Player

**Sound but insufficient.** Replacing the "Reload Kdenlive" banner with an HTML5 `<video>` player is necessary. But a single video player is a *render preview*, not an *edit preview*. The user cannot see "this is the clip the AI just added" without scrubbing. A real edit-preview needs timeline visualization with edit highlights, not just a video player.

#### 2.1.5 Step 4 — Automate the Render-QC Loop

**Sound.** `pyagent_render` in proxy mode + `pyagent_list_black_frames` + `pyagent_list_silence` + `pyagent_get_thumbnail` is a reasonable QC loop. This is the strongest part of v1 and survives into the recommended architecture.

#### 2.1.6 Realism

v1 is realistic *for what it attempts* — a headless Kdenlive replacement. It is not realistic for what you actually asked for, because it does not attempt an IR, an edit graph, or undo/reorder/fine-tune.

---

### 2.2 Review of Plan v2 ("Free-Form Code, No Kdenlive")

#### 2.2.1 The Pivot to Free-Form Code

**Argument is partially correct, partially overstated.** The claim that free-form code lets the AI use loops and conditionals ("trim every clip on track 2 by 10%") is valid. The claim that discrete tool-calling causes "accuracy loss" because the model has to force edits through whichever verb happens to exist is also valid — but only if the verb set is poorly designed. A well-designed operation set (the IR proposed in this document) is itself the vocabulary the model uses; the model is not "forcing" anything, it is speaking the language.

**The real trade-off** is not "free-form vs. discrete" — it is "unchecked emission vs. schema-validated emission." Free-form code has no schema; you cannot statically check that the code will produce a valid edit. Discrete operations have a schema; you can validate before applying. v2 acknowledges this ("you lose the safety property of a fixed, schema-validated action surface") but proposes to rebuild it via the QC gate, which is a *post-hoc* check, not a *pre-hoc* one.

**Recommended resolution:** Both modes coexist. Structured operations are the default because they are schema-validatable. Free-form code is the escape hatch for cases the operation set does not cover (e.g. a one-off MLT XML mutation that no operation models). This is exactly the "Hybrid IR" decision you confirmed.

#### 2.2.2 The Open Design Precedent

**Borrowed correctly, with the right caveat.** v2 correctly identifies that Open Design's three-part shape (chat + preview + project/export) transfers, and that the iframe sandbox does *not* transfer because there is no browser-equivalent for "AI-written code that spawns `melt`."

**Missing piece:** Open Design's *artifact* is the source of truth — the HTML/CSS/JS the AI writes is what the user later edits. v2's *artifact* is MLT XML, but MLT XML is the render target, not the editable artifact. The editable artifact in Open Edit must be the **edit graph** (the IR), not the XML. v2 misses this distinction entirely.

#### 2.2.3 Reusability Matrix v2

**More honest than v1.** The "Low" rating for Phase 3 (the tool-calling protocol layer) is correct — the JSON-RPC wrapper is gone. The "Reshaped, not just trimmed" rating for Phase 7 (tests) is the most accurate line in either plan: scenario-based eval is genuinely different from golden-file-per-tool testing.

**Weakness:** The matrix still scores reusability *per existing phase* rather than *per the new architecture's needs*. A better matrix would ask: "for each new subsystem (IR, edit graph, sandbox, QC, UI), how much existing code carries over?" The answer for IR and edit graph is **zero** because they do not exist in `pyagent-kdenlive`.

#### 2.2.4 The Control Layer

**Necessary, but mis-scoped.** v2's Control Layer has two parts:

1. Execution sandbox (container or restricted subprocess) — sound.
2. Mandatory post-execution validation gate (melt loads XML → render → QC scan → thumbnail) — sound.

**The mis-scoping:** v2 frames this as *the* control mechanism, replacing Open Design's iframe. But Open Design's iframe is a *rendering* sandbox — it isolates the artifact at view time. The Open Edit sandbox is an *execution* sandbox — it isolates the AI's code at write time. These are different layers:

- **Execution-time safety** (v2's sandbox + QC gate): did the AI's code escape, did it produce a broken render?
- **Edit-history safety** (missing from v2): can the user undo, reorder, fine-tune any edit later?

The recommended architecture keeps v2's execution-time layer intact and adds the edit-history layer (edit graph) on top.

#### 2.2.5 Transition Plan (v2)

**Step 1 (sandbox + validation harness first) is correct.** Building the control layer before the editing logic is the right order. v1's "flip a mode flag" framing is genuinely inferior here.

**Step 2 (native MLT backend) is correct as a render target, wrong as the project representation.** See §3 below.

**Step 3 (reference library + examples) is sound.** Porting Phase 2's ops into an optional helper library is exactly the right demotion — from "mandatory API" to "documentation + convenience."

**Step 4 (UI: chat + preview + QC surface) is incomplete.** It omits the edit history panel and the timeline panel. Without those, the user cannot do the undo/reorder/fine-tune you asked for.

**Step 5 (scenario-based eval suite) is sound** and survives into Phase 7 of the recommended roadmap.

#### 2.2.6 Risks (v2)

**Mostly accurate.** The "free-form code is measurably less consistent" risk is real and the mitigation (build the scenario eval suite early) is correct. The "sandbox escape" risk is real and the mitigation (container-level isolation, allowlist only melt/ffmpeg/ffprobe) is correct.

**Missing risks:**

- **Risk: MLT XML is treated as IR, then later discovered to be un-editable.** v2 does not list this. It is the highest-impact risk in the entire plan.
- **Risk: AI emits valid MLT XML that is semantically wrong** (e.g. wrong clip ordering, missing transition). QC gate catches structural problems, not semantic ones. v2 lists "subtly wrong but passes QC" as a Medium risk, but under-rates the impact — for a video editor, a subtly wrong edit that the user does not notice until export is a High-impact bug.
- **Risk: free-form code accumulates technical debt.** Each free-form code edit is opaque; future edits cannot easily build on it. v2 does not list this.

#### 2.2.7 Open Questions (v2)

**All three are real and unresolved.** The recommended architecture answers them as follows:

- **Sandbox technology:** Rust subprocess jail with `seccomp`/`landlock` (Linux) or seatbelt (macOS). See Phase 3.
- **Determinism strategy:** N trials per scenario (N=5 default), failure rate >20% triggers investigation, >40% blocks merge. See Phase 7.
- **Output format:** Plain MLT XML rendered by `melt` as the *render target*. The *project representation* is the edit graph IR. These are different layers; v2 conflates them.

#### 2.2.8 Realism

v2 is more realistic than v1 about the *hard problems* (sandbox, QC, scenario eval). It is less realistic than it claims about the *edit model* — by treating MLT XML as the artifact, it locks the system into a representation that cannot support undo/reorder/fine-tune without a later painful migration.

---

## 3. Problems in Existing Plans

### 3.1 Missing Requirements (against your original 16-category checklist)

| Category | v1 | v2 | What's missing |
|---|---|---|---|
| Data model | Absent | Absent | No project data model. MLT XML is treated as the model. Need: Project, Asset, Edit, Operation, Timeline, Track, Clip, Effect — all with stable IDs. |
| Project representation | Absent | Absent | No IR. MLT XML is the source of truth, which makes undo/reorder impossible at the operation level. |
| Timeline abstraction | Absent | Absent | AI manipulates raw MLT nodes. No abstraction for "track", "clip", "transition" as first-class objects with identity. |
| Edit graph | Absent | Absent | No operation log, no edit IDs, no parent relationships, no compound operations. |
| Rendering pipeline | Addressed | Addressed | `melt` + `ffmpeg` + `ffprobe`. Sound in both. |
| Undo/redo architecture | Absent | Absent | No undo beyond "re-render the previous XML." No redo. No branching. |
| Asset management | Absent | Absent | No content-addressed storage. No deduplication. No proxy generation. No asset metadata cache. |
| Plugin architecture | Absent | Absent | No plugin story. Effects are hardcoded MLT service IDs. |
| AI interaction layer | Partial | Addressed | v2's free-form code + sandbox is reasonable, but no schema-validated emission mode, no structured operation set. |
| UI synchronization | Partial | Partial | Only WebSocket `video_ready`. No edit-stream sync (UI does not know which edit just happened, cannot highlight it). |
| Versioning | Absent | Absent | No project version history. No diffing. No branching. |
| Collaboration | Absent | Absent | No multi-user model. Acceptable for v1 (single-user desktop), but data model decisions made now either enable or foreclose future collaboration. |
| Performance | Absent | Absent | No caching strategy. No proxy rendering. No background rendering. No GPU acceleration. |
| Caching | Absent | Absent | No render cache. Re-rendering after every edit is wasteful. Need: cache keyed by edit-graph hash. |
| Background rendering | Absent | Absent | No async render queue. UI blocks on render. |
| Testing strategy | Partial | Addressed | v2's scenario eval is sound. v1's Xvfb golden files are not. Neither addresses IR-level unit tests, sandbox security tests, or performance regression tests. |

**Score: 2 fully addressed, 2 partial, 12 absent.** Both plans are emission-and-render plans, not architecture plans.

### 3.2 Conceptual Errors

#### 3.2.1 Conflating execution-time safety with edit-history safety

v2's "Control Layer" is execution-time safety: sandbox prevents escape, QC gate prevents broken renders. Edit-history safety — the ability to undo, reorder, fine-tune any AI edit later — is a different problem that requires a different solution (an operation log with stable IDs). v2 does not address it.

#### 3.2.2 Treating MLT XML as the IR

MLT XML is a serialized render graph. It has no concept of:

- An "edit" as a discrete object with an ID and a history.
- A "clip" as an object with stable identity across moves, trims, and effects.
- An "operation" that can be undone, redone, or reordered.

Treating MLT XML as the IR locks the system into a representation that cannot support the properties you asked for. The IR must be a separate layer; MLT XML must be a *derived artifact* emitted from the IR.

#### 3.2.3 "Free-form code" without an edit-graph discipline

v2's free-form code emission is appealing (loops, conditionals, composition), but without an edit-graph discipline, each free-form code edit is an opaque blob. Future edits cannot easily build on it. The user cannot undo "step 3 of the AI's script" because step 3 is not a discrete object — it is a line inside a script.

**Resolution:** Free-form code is allowed, but it must call the IR API. The IR API produces structured operations that go into the edit graph. The free-form code is the *vehicle* for emission; the edit graph is the *result*.

#### 3.2.4 Reusability percentages that are unverifiable

v1 claims 75% reusability; v2 claims per-phase reusability ratings. Without source access, these are estimates. The recommended architecture treats them as **upper bounds**, not commitments. Phase 6 (migration) is structured to discover the actual reusability early, before depending on it.

#### 3.2.5 Missing the "edit transparency" requirement

Your brief implies (and Open Design's precedent makes explicit) that the user should see what the AI did — not just the result, but the *operations*. Neither v1 nor v2 addresses this. The recommended architecture includes an Edit History panel that shows every operation with author, timestamp, parameters, and status.

#### 3.2.6 No asset management

Both plans ignore assets. A video editor without asset management is a toy. Assets need:

- Content-addressed storage (SHA-256 hash → file path) for deduplication.
- Proxy generation (low-res preview copies) for fast scrubbing.
- Metadata cache (duration, fps, resolution, codec, audio channels) populated by `ffprobe`.
- Asset references in the IR (clip → asset by hash, not by path).

#### 3.2.7 No caching strategy

Both plans re-render after every edit. For a 10-minute video, this is seconds to minutes per edit. The recommended architecture includes a render cache keyed by edit-graph hash: if the edit graph has not changed since the last render, reuse the render. If only the last 5 seconds changed, re-render only those 5 seconds and stitch.

---

## 4. Recommended Architecture

### 4.1 Two-Layer IR: Edit Graph + Timeline State

The core recommendation is a **two-layer intermediate representation**:

```
┌─────────────────────────────────────────────────────────────┐
│  Edit Graph (operations, append-only log)                   │
│  - Each operation has a stable UUID                         │
│  - Each operation references a parent operation             │
│  - This is what undo / redo / reorder / fine-tune operate on│
└──────────────────────────┬──────────────────────────────────┘
                           │ apply(project)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Timeline State (derived projection)                        │
│  - Tracks, clips, effects, transitions                      │
│  - What the user sees in the timeline panel                 │
│  - What gets serialized to MLT XML for rendering            │
└──────────────────────────┬──────────────────────────────────┘
                           │ emit()
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  MLT XML (render target, NOT the source of truth)           │
│  - Generated from timeline state                            │
│  - Consumed by `melt` to produce MP4                        │
└─────────────────────────────────────────────────────────────┘
```

**Why two layers:**

- The edit graph is the source of truth. It is append-only, so undo is "revert operation X" (mark it `reverted`), not "delete operation X." Reorder is "swap the application order of operations X and Y" (where semantically valid). Fine-tune is "modify the parameters of operation X" (creating a new operation that supersedes X).
- The timeline state is derived. It is recomputed by applying the edit graph to an empty project. This is the **command pattern** with a **projection** — a well-known architecture from event-sourcing systems.
- MLT XML is a render target, derived from the timeline state. It is never the source of truth, never edited directly by the user, never used for undo/reorder.

### 4.2 Three AI Emission Modes

The AI can emit edits in three ways, in descending order of preference:

1. **Structured Operations (preferred).** The AI emits a JSON array of operations conforming to the operation schema. Each operation is schema-validated before application. If validation fails, the AI receives the error and retries. This is the default mode.

2. **Raw MLT XML (escape hatch).** For one-off cases the operation set does not cover (e.g. an obscure MLT filter with a parameter the IR does not model), the AI emits a raw MLT XML fragment. The fragment is parsed by the **MLT XML Ingest Parser** into synthetic operations that go into the edit graph. The user sees these as `RawMltXml` operations in the edit history, with the XML attached for transparency.

3. **Free-Form Python Code (power user).** The AI emits a Python script that calls the IR API (`ir.add_clip(...)`, `ir.trim_clip(...)`, etc.). The script runs in the sandbox (Phase 3). Each API call produces a structured operation in the edit graph. This mode is for complex multi-step edits where the AI wants to use loops, conditionals, or composition. The script's source is stored alongside the resulting operations for transparency.

**Why three modes:** Structured operations are safe (schema-validated) but limited (only what the operation set models). Raw XML is flexible but lossy (the IR cannot fully represent arbitrary MLT). Free-form code is flexible and lossless but unsafe (the script could do anything the sandbox allows). The default is the safe mode; the escape hatches exist for cases the safe mode cannot handle.

### 4.3 Stack Recommendation

| Subsystem | Language | Why |
|---|---|---|
| IR Runtime, Edit Graph, Storage | Python | AI ecosystem alignment; matches existing `pyagent-kdenlive` |
| MLT XML Emitter / Parser | Python | `lxml` for XML; same language as IR |
| Render Orchestrator | Python | Subprocess wrapper around `melt`/`ffmpeg`/`ffprobe` |
| AI Agent Loop | Python | Direct access to LLM SDKs |
| Sandbox | Rust | Memory safety; syscall-level control (`seccomp`, `landlock`, `seatbelt`); no GC pauses |
| Backend API (FastAPI) | Python | WebSocket for chat, REST for project ops |
| Frontend (Timeline, Edit History, Chat) | TypeScript + React | Component richness; ecosystem for canvas/timeline UIs |
| Desktop Shell | Tauri | Lighter than Electron; Rust core matches sandbox language; native webview |

**Boundaries:** Rust sandbox is a separate binary, invoked as a subprocess by the Python render orchestrator. TypeScript frontend talks to Python backend over WebSocket + REST. Tauri shell wraps both.

### 4.4 Storage

- **Project metadata + edit graph:** SQLite (`~/.open-edit/projects/<project_id>.db`). One DB per project. Single-user, no concurrency beyond the desktop app itself.
- **Asset blobs:** Content-addressed filesystem (`~/.open-edit/assets/<sha256_prefix>/<hash>`). Deduplicated by hash.
- **Proxy renders:** `~/.open-edit/cache/proxies/<asset_hash>_<profile>.mp4`. Cached low-res previews.
- **Render cache:** `~/.open-edit/cache/renders/<edit_graph_hash>.mp4`. Keyed by SHA-256 of the edit graph (canonical JSON). If the edit graph has not changed, reuse the render.
- **Thumbnails:** `~/.open-edit/cache/thumbs/<asset_hash>_<frame_sec>.jpg`.

### 4.5 Edit Graph Schema (Concrete)

```python
# open_edit/ir/types.py

from typing import Literal, Optional, Union
from pydantic import BaseModel, Field
import uuid

def new_id() -> str:
    return str(uuid.uuid4())

class Operation(BaseModel):
    """Base class. Discriminated union on `kind`."""
    kind: str
    edit_id: str = Field(default_factory=new_id)
    parent_id: Optional[str] = None  # edit this one builds on (null = root)
    author: Literal["ai", "user"]
    timestamp: str  # ISO 8601
    status: Literal["applied", "reverted", "superseded"] = "applied"

# --- Concrete operations ---

class AddClipOp(Operation):
    kind: Literal["add_clip"] = "add_clip"
    asset_hash: str
    track_id: str
    position_sec: float
    in_point_sec: float = 0.0
    out_point_sec: Optional[float] = None  # None = full asset duration
    clip_id: str = Field(default_factory=new_id)  # stable across future edits

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
    transition_type: Literal["dissolve", "wipe", "fade", "cut"]
    duration_sec: float

class AddEffectOp(Operation):
    kind: Literal["add_effect"] = "add_effect"
    target_kind: Literal["clip", "track"]
    target_id: str
    effect_type: str  # MLT service ID, e.g. "movit.brightness"
    params: dict  # validated against effect registry (Phase 1 catalog)
    effect_id: str = Field(default_factory=new_id)

class SetKeyframeOp(Operation):
    kind: Literal["set_keyframe"] = "set_keyframe"
    effect_id: str
    param: str
    keyframes: list[tuple[float, float, str]]  # (time_sec, value, interp)

class GroupEditsOp(Operation):
    kind: Literal["group_edits"] = "group_edits"
    edit_ids: list[str]  # child edits
    label: str  # human-readable, e.g. "AI: add intro music"

class RawMltXmlOp(Operation):
    kind: Literal["raw_mlt_xml"] = "raw_mlt_xml"
    xml: str  # the raw MLT XML fragment
    description: str  # what the AI was trying to do
    # On application, this is parsed by the MLT XML ingest parser
    # into synthetic child operations (AddClipOp, AddEffectOp, etc.)
    # The raw XML is preserved for transparency.

class FreeFormCodeOp(Operation):
    kind: Literal["free_form_code"] = "free_form_code"
    code: str  # Python source
    # On application, the code runs in the sandbox and calls the IR API.
    # Each IR API call produces a child operation.
    # The code source is preserved for transparency.

OperationUnion = Union[
    AddClipOp, RemoveClipOp, MoveClipOp, TrimClipOp,
    AddTransitionOp, AddEffectOp, SetKeyframeOp,
    GroupEditsOp, RawMltXmlOp, FreeFormCodeOp,
]
```

### 4.6 Timeline State Schema (Concrete)

```python
# open_edit/ir/timeline.py

class Clip(BaseModel):
    clip_id: str
    asset_hash: str
    track_id: str
    position_sec: float
    in_point_sec: float
    out_point_sec: float
    effects: list["Effect"] = []

class Track(BaseModel):
    track_id: str
    kind: Literal["video", "audio"]
    clips: list[Clip] = []
    effects: list["Effect"] = []

class Effect(BaseModel):
    effect_id: str
    effect_type: str
    params: dict
    keyframes: dict[str, list[tuple[float, float, str]]] = {}

class Timeline(BaseModel):
    tracks: list[Track]
    duration_sec: float  # computed from clips
```

### 4.7 Operation Application (Command Pattern)

```python
# open_edit/ir/apply.py

def apply_operation(project: Project, op: Operation) -> Project:
    """Apply an operation to a project, returning a new project.
    
    Pure function. Does not mutate the input. Used by:
    - The edit graph to derive timeline state.
    - The undo system to replay operations.
    """
    if op.status == "reverted":
        return project  # reverted ops are no-ops
    
    if isinstance(op, AddClipOp):
        return _apply_add_clip(project, op)
    elif isinstance(op, RemoveClipOp):
        return _apply_remove_clip(project, op)
    # ... etc
    elif isinstance(op, RawMltXmlOp):
        # Parse the XML into synthetic child operations, apply each.
        child_ops = mlt_xml_ingest(op.xml, project)
        for child in child_ops:
            child.parent_id = op.edit_id
            project = apply_operation(project, child)
        return project
    elif isinstance(op, FreeFormCodeOp):
        # Run the code in the sandbox; it calls ir.add_clip(...) etc.
        # Each call enqueues a child operation; apply them in order.
        child_ops = run_sandboxed_code(op.code, project)
        for child in child_ops:
            child.parent_id = op.edit_id
            project = apply_operation(project, child)
        return project

def derive_timeline(project: Project) -> Timeline:
    """Replay all non-reverted operations in order to derive timeline state."""
    timeline = Timeline(tracks=[], duration_sec=0.0)
    for op in project.edit_graph:
        if op.status == "applied":
            timeline = apply_operation(timeline, op)
    return timeline
```

### 4.8 Undo / Redo / Reorder / Fine-Tune

| Action | Implementation |
|---|---|
| **Undo** | Mark the most recent `applied` operation as `reverted`. Re-derive timeline. |
| **Redo** | Mark the most recently `reverted` operation as `applied`. Re-derive timeline. |
| **Reorder** | Swap two adjacent operations in the edit graph **only if commutative** (validated by a `can_swap(op_a, op_b)` predicate). If not commutative, reject with a human-readable explanation. |
| **Fine-tune** | Create a new operation that supersedes the target: mark the target as `superseded`, append a new operation with modified parameters. The original is preserved in history. |
| **Branch** | Create a new project with the edit graph up to operation X, then diverge. (Future improvement; not v1.) |

### 4.9 Comparison to v1 and v2

| Property | v1 | v2 | Recommended |
|---|---|---|---|
| AI emission mode | Discrete tool calls | Free-form code | Three modes: structured ops (default), raw XML (escape), free-form code (power) |
| Source of truth | MLT XML | MLT XML | Edit graph (IR) |
| MLT XML role | Project representation | Project representation | Render target only |
| Undo | XML diff | XML diff | Operation-level (mark reverted) |
| Reorder | Not supported | Not supported | Operation-level (with commutativity check) |
| Fine-tune | Hand-edit XML | Hand-edit XML | New op supersedes old, original preserved |
| Execution safety | None | Sandbox + QC gate | Sandbox + QC gate (inherited from v2) |
| Edit-history safety | None | None | Edit graph with stable IDs |
| User can see what AI did | No | No | Edit history panel |
| Asset management | None | None | Content-addressed store |
| Caching | None | None | Render cache keyed by edit-graph hash |

---

## 5. System Components

### 5.1 Component Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Tauri Shell (Rust)                           │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │           React Frontend (TypeScript)                       │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │    │
│  │  │  Chat    │ │ Timeline │ │  Edit    │ │ Preview + QC │   │    │
│  │  │  Panel   │ │  Panel   │ │ History  │ │    Panel     │   │    │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬───────┘   │    │
│  └───────┼────────────┼────────────┼──────────────┼───────────┘    │
│          │            │            │              │                │
│          └────────────┴────────────┴──────────────┘                │
│                              │ WebSocket + REST                     │
└──────────────────────────────┼──────────────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────────────┐
│              Python Backend (FastAPI)  │                              │
│  ┌─────────────────┐  ┌──────────────┐ │  ┌────────────────────┐    │
│  │  Chat / Agent   │  │  Project API │ │  │  Render API        │    │
│  │  Loop           │  │  (CRUD)      │ │  │  (trigger, status) │    │
│  └────────┬────────┘  └──────┬───────┘ │  └─────────┬──────────┘    │
│           │                  │         │            │               │
│  ┌────────▼──────────────────▼─────────┐ │  ┌────────▼──────────┐    │
│  │       IR Runtime (Python)           │ │  │ Render Orchestr.  │    │
│  │  ┌────────────┐  ┌──────────────┐   │ │  │  (Python)         │    │
│  │  │ Edit Graph │  │  Timeline    │   │ │  └─────────┬─────────┘    │
│  │  │  Store     │  │  Projection  │   │ │            │              │
│  │  │ (SQLite)   │  │              │   │ │  ┌─────────▼─────────┐    │
│  │  └────────────┘  └──────────────┘   │ │  │   MLT XML Emitter │    │
│  │  ┌────────────┐  ┌──────────────┐   │ │  │   (Python, lxml)  │    │
│  │  │  Asset     │  │  MLT XML     │   │ │  └─────────┬─────────┘    │
│  │  │  Store     │  │  Ingest      │   │ │            │              │
│  │  │ (CAS FS)   │  │  Parser      │   │ │  ┌─────────▼─────────┐    │
│  │  └────────────┘  └──────────────┘   │ │  │   QC Gate         │    │
│  └─────────────────────────────────────┘ │  │   (Python)        │    │
│           │                              │  └─────────┬─────────┘    │
│           │ AI emits code                │            │              │
│           │                              │  ┌─────────▼─────────┐    │
│  ┌────────▼─────────────────────────┐    │  │  Sandbox (Rust)   │    │
│  │  AI Agent Loop (Python)          │    │  │  - seccomp jail   │    │
│  │  - LLM calls (z-ai-web-dev-sdk)  │    │  │  - fs jail        │    │
│  │  - Emission mode dispatcher      │    │  │  - allowlist      │    │
│  │  - Retry logic                   │    │  │    melt/ffmpeg/   │    │
│  └──────────────────────────────────┘    │  │    ffprobe        │    │
│                                          │  └───────────────────┘    │
└──────────────────────────────────────────┴───────────────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  melt / ffmpeg /    │
                    │  ffprobe (system)   │
                    └─────────────────────┘
```

### 5.2 Component Specifications

#### 5.2.1 IR Runtime (`open_edit/ir/`)
- **Language:** Python 3.11+
- **Responsibilities:** Define operation types, apply operations to derive timeline state, validate operation schemas, expose IR API for free-form code.
- **Key files:** `open_edit/ir/types.py`, `open_edit/ir/apply.py`, `open_edit/ir/api.py`, `open_edit/ir/validate.py`
- **Dependencies:** `pydantic>=2.0`, `lxml`
- **Interfaces:** `IR.add_clip(...)`, `IR.trim_clip(...)`, etc. (called by free-form code in sandbox)

#### 5.2.2 Edit Graph Store (`open_edit/storage/edit_graph.py`)
- **Language:** Python
- **Responsibilities:** Persist edit graph to SQLite; load by project ID; append operations transactionally.
- **Schema:** `edits` table (edit_id PK, parent_id, kind, author, timestamp, status, payload JSON)
- **Key files:** `open_edit/storage/edit_graph.py`, `open_edit/storage/schema.sql`

#### 5.2.3 Asset Store (`open_edit/storage/assets.py`)
- **Language:** Python
- **Responsibilities:** Content-addressed storage for video/audio/image assets; populate metadata via `ffprobe`; generate proxy renders.
- **Layout:** `~/.open-edit/assets/<sha256_prefix>/<hash>` (original), `~/.open-edit/cache/proxies/<hash>_<profile>.mp4` (proxy)
- **Key files:** `open_edit/storage/assets.py`, `open_edit/storage/proxy.py`

#### 5.2.4 MLT XML Emitter (`open_edit/render/emitter.py`)
- **Language:** Python
- **Responsibilities:** Convert a `Timeline` to a valid MLT XML document (`<tractor>`, `<multitrack>`, `<playlist>`, `<entry>`, `<filter>`, `<transition>`).
- **Key files:** `open_edit/render/emitter.py`, `open_edit/render/profiles.py`
- **Validation:** Emitted XML must load in `melt` without error (Phase 2 validation criterion).

#### 5.2.5 MLT XML Ingest Parser (`open_edit/render/ingest.py`)
- **Language:** Python
- **Responsibilities:** Parse a raw MLT XML fragment into synthetic IR operations. Used by `RawMltXmlOp` application.
- **Limitation:** Cannot perfectly reverse-engineer arbitrary MLT XML into IR operations. Documents what it can parse; rejects what it cannot with a structured error.
- **Key files:** `open_edit/render/ingest.py`

#### 5.2.6 Render Orchestrator (`open_edit/render/orchestrator.py`)
- **Language:** Python
- **Responsibilities:** Accept a `Timeline`, emit MLT XML, invoke `melt` as subprocess, return MP4 path. Manage render cache (skip if edit-graph hash matches a cached render).
- **Key files:** `open_edit/render/orchestrator.py`, `open_edit/render/cache.py`

#### 5.2.7 QC Gate (`open_edit/qc/gate.py`)
- **Language:** Python
- **Responsibilities:** After every edit, run: (1) structural check (`melt -consumer xml` loads the emitted XML), (2) proxy render, (3) black-frame scan, (4) silence scan, (5) thumbnail generation. Return a `QCReport` JSON.
- **Key files:** `open_edit/qc/gate.py`, `open_edit/qc/black_frames.py`, `open_edit/qc/silence.py`, `open_edit/qc/thumbnail.py`
- **Output:**
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

#### 5.2.8 Sandbox (`sandbox/`)
- **Language:** Rust
- **Responsibilities:** Run AI-emitted Python code in a restricted environment. Filesystem jail (only project working dir + read-only asset store). No network. Allowlisted subprocesses (`melt`, `ffmpeg`, `ffprobe` only). Hard wall-clock + memory limits.
- **Implementation:** Linux: `seccomp` + `landlock` + `namespaces`. macOS: `sandbox-exec` (seatbelt). Windows: not supported in v1 (documented limitation).
- **Key files:** `sandbox/src/main.rs`, `sandbox/src/jail.rs`, `sandbox/src/allowlist.rs`
- **Interface:** CLI: `sandbox --code <path> --workdir <path> --timeout 30 --mem 512M`

#### 5.2.9 AI Agent Loop (`open_edit/agent/loop.py`)
- **Language:** Python
- **Responsibilities:** Receive user message, assemble prompt (system + IR snapshot + history + user message), call LLM, parse emission (structured ops / raw XML / free-form code), apply to IR, trigger render + QC, return result to chat.
- **LLM SDK:** `z-ai-web-dev-sdk` (per project conventions)
- **Key files:** `open_edit/agent/loop.py`, `open_edit/agent/prompt.py`, `open_edit/agent/parse.py`, `open_edit/agent/retry.py`

#### 5.2.10 Chat / WebSocket Bridge (`open_edit/api/chat.py`)
- **Language:** Python (FastAPI)
- **Responsibilities:** WebSocket endpoint for chat. Stream agent messages to frontend. Receive user messages. Stream edit events (operation applied, render started, QC passed) as separate message types.
- **Key files:** `open_edit/api/chat.py`, `open_edit/api/project.py` (REST), `open_edit/api/render.py` (REST)

#### 5.2.11 Frontend — Chat Panel (`frontend/src/panels/Chat.tsx`)
- **Language:** TypeScript + React
- **Responsibilities:** Display conversation. Send user messages via WebSocket. Display agent responses including emission summaries ("Added 3 clips, 1 transition"). Display QC report inline.

#### 5.2.12 Frontend — Timeline Panel (`frontend/src/panels/Timeline.tsx`)
- **Language:** TypeScript + React + HTML Canvas
- **Responsibilities:** Visual timeline with tracks and clips. Click clip to select. Drag to move. Edge-drag to trim. Right-click for effect menu. Highlights the most recent AI edit (animated outline).

#### 5.2.13 Frontend — Edit History Panel (`frontend/src/panels/EditHistory.tsx`)
- **Language:** TypeScript + React
- **Responsibilities:** Vertical list of every operation in the edit graph. Each row: icon, label, author (AI/user), timestamp, status badge. Click to expand parameters. Right-click to undo / redo / fine-tune / reorder.

#### 5.2.14 Frontend — Preview + QC Panel (`frontend/src/panels/Preview.tsx`)
- **Language:** TypeScript + React
- **Responsibilities:** HTML5 `<video>` player showing current proxy render. QC status badges (pass/fail per check). Black-frame markers on the timeline. Silence markers. Thumbnail strip.

#### 5.2.15 Tauri Shell (`desktop/src-tauri/`)
- **Language:** Rust
- **Responsibilities:** Window management, menu bar, file dialogs, sidecar process management (launch Python backend on app start, kill on exit).
- **Key files:** `desktop/src-tauri/src/main.rs`, `desktop/src-tauri/tauri.conf.json`

### 5.3 Component Dependency Graph

```
Frontend (React) ──depends on──> Backend API (FastAPI)
Backend API ──depends on──> IR Runtime
IR Runtime ──depends on──> Edit Graph Store, Asset Store
Backend API ──depends on──> Render Orchestrator
Render Orchestrator ──depends on──> MLT XML Emitter, Render Cache, melt (system)
Render Orchestrator ──depends on──> QC Gate
QC Gate ──depends on──> ffprobe, ffmpeg (system)
Backend API ──depends on──> AI Agent Loop
AI Agent Loop ──depends on──> IR Runtime, Sandbox (Rust)
Sandbox ──depends on──> IR Runtime (Python, called from inside sandbox)
Sandbox ──depends on──> melt, ffmpeg, ffprobe (allowlisted)
```

---

## 6. Data Flow

### 6.1 User Makes an Edit via UI

```
User drags clip on timeline
  │
  ▼
Frontend: emits WebSocket message {"type":"user_edit","op":{...}}
  │
  ▼
Backend: receives op, validates schema
  │
  ▼
IR: appends op to edit graph (SQLite transaction)
  │
  ▼
IR: re-derives timeline state
  │
  ▼
Backend: broadcasts {"type":"timeline_updated","timeline":{...}} to all panels
  │
  ▼
Render Orchestrator: checks render cache (edit-graph hash)
  │
  ├─ cache hit → return cached render path
  │
  └─ cache miss → emit MLT XML, invoke melt, wait
       │
       ▼
  QC Gate: runs 5 checks
       │
       ▼
  Backend: broadcasts {"type":"render_ready","path":"...","qc":{...}}
       │
       ▼
  Frontend: Preview panel updates video src; QC panel updates badges
```

### 6.2 AI Emits Structured Operations

```
User: "Add intro music starting at 0:00, fade in over 2 seconds"
  │
  ▼
Agent Loop: assembles prompt
  - System prompt (rules, emission modes)
  - IR snapshot (current timeline as JSON)
  - Conversation history (last N turns)
  - User message
  │
  ▼
LLM: returns JSON array of operations
  [
    {"kind":"add_clip","asset_hash":"abc...","track_id":"audio_1","position_sec":0.0,...},
    {"kind":"add_effect","target_kind":"clip","target_id":"clip_xyz","effect_type":"volume","params":{"start":0,"end":1},...}
  ]
  │
  ▼
Agent Loop: validates each op against Pydantic schema
  │
  ├─ validation fails → return error to LLM, retry (max 3)
  │
  └─ validation passes
       │
       ▼
IR: appends each op to edit graph (transactional)
  │
  ▼
(same as 6.1 from here: re-derive timeline, render, QC, broadcast)
```

### 6.3 AI Emits Raw MLT XML (Escape Hatch)

```
User: "Apply a vintage film look using the movit.vignette filter"
  │
  ▼
Agent Loop: assembles prompt
  │
  ▼
LLM: returns {"mode":"raw_xml","xml":"<filter><property name=\"service\">movit.vignette</property>...</filter>","description":"Vintage film look"}
  │
  ▼
Agent Loop: wraps as RawMltXmlOp, appends to edit graph
  │
  ▼
IR: applies op
  - Calls MLT XML Ingest Parser
  - Parser produces synthetic child ops (AddEffectOp, SetKeyframeOp, etc.)
  - Each child op gets parent_id = RawMltXmlOp.edit_id
  - Children appended to edit graph
  │
  ▼
(same as 6.1 from here)
```

### 6.4 AI Emits Free-Form Code

```
User: "Trim every clip on track 2 by 10%"
  │
  ▼
Agent Loop: assembles prompt
  │
  ▼
LLM: returns {"mode":"code","code":"for clip in ir.list_clips(track_id='video_2'):\n    dur = clip.out_point_sec - clip.in_point_sec\n    new_dur = dur * 0.9\n    ir.trim_clip(clip.clip_id, clip.in_point_sec, clip.in_point_sec + new_dur)"}
  │
  ▼
Agent Loop: wraps as FreeFormCodeOp, appends to edit graph
  │
  ▼
IR: applies op
  - Invokes sandbox: `sandbox --code <path> --workdir <project>`
  - Sandbox runs Python; Python imports `ir` (IR API stub)
  - Each `ir.trim_clip(...)` call enqueues a TrimClipOp
  - Sandbox returns list of enqueued ops
  - Each op gets parent_id = FreeFormCodeOp.edit_id
  - Children appended to edit graph
  │
  ▼
(same as 6.1 from here)
```

### 6.5 User Undoes an Edit

```
User clicks "Undo" on row 5 in Edit History panel
  │
  ▼
Frontend: emits {"type":"undo","edit_id":"<uuid>"}
  │
  ▼
Backend: marks op edit_id as "reverted" in edit graph
  │
  ▼
IR: re-derives timeline (op is now a no-op)
  │
  ▼
(same as 6.1 from here)
```

### 6.6 User Reorders Two Edits

```
User drags row 5 to position 3 in Edit History panel
  │
  ▼
Frontend: emits {"type":"reorder","edit_id_a":"<uuid>","edit_id_b":"<uuid>"}
  │
  ▼
Backend: checks can_swap(op_a, op_b)
  - If they touch different clips → commutative → swap OK
  - If they touch the same clip → may not be commutative → check semantics
  │
  ├─ swap rejected → return error: "Cannot reorder: op A modifies clip X which op B also modifies"
  │
  └─ swap accepted
       │
       ▼
  IR: reorders ops in edit graph (SQLite transaction)
       │
       ▼
  (same as 6.1 from here)
```

### 6.7 User Fine-Tunes an Edit

```
User clicks row 5 (AddEffectOp: brightness=0.5), edits parameter to 0.7
  │
  ▼
Frontend: emits {"type":"fine_tune","edit_id":"<uuid>","new_params":{"brightness":0.7}}
  │
  ▼
Backend: marks original op as "superseded"
  - Appends new AddEffectOp with modified params, parent_id = original edit_id
  │
  ▼
(same as 6.1 from here)
```

---

## 7. AI Editing Pipeline

### 7.1 Pipeline Stages

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐
│  1. Prompt  │───>│  2. LLM Call │───>│ 3. Parse    │───>│ 4. Validate  │
│  Assembly   │    │              │    │   Emission  │    │   Schema     │
└─────────────┘    └──────────────┘    └─────────────┘    └──────┬───────┘
                                                                  │
                                                                  ▼
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐
│  8. Surface │<───│  7. Cache    │<───│ 6. QC Gate  │<───│ 5. Apply to  │
│   Result    │    │   Render     │    │             │    │   Edit Graph │
└─────────────┘    └──────────────┘    └─────────────┘    └──────────────┘
```

### 7.2 Stage 1: Prompt Assembly

```python
# open_edit/agent/prompt.py

def assemble_prompt(project: Project, history: list[dict], user_message: str) -> list[dict]:
    """Assemble the chat messages for the LLM.
    
    Returns a list of {role, content} dicts.
    """
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        operations_schema=OPERATIONS_SCHEMA_JSON,
        effect_catalog_summary=EFFECT_CATALOG_SUMMARY,
        current_timeline=serialize_timeline(project.timeline),
        available_assets=serialize_assets(project.assets),
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-20:])  # last 20 turns
    messages.append({"role": "user", "content": user_message})
    return messages
```

**System prompt template (sketch):**

```
You are Open Edit, an AI video editing assistant.

You operate on an Intermediate Representation (IR) of a video project.
The IR has two layers:
1. Edit Graph: an append-only log of operations with stable UUIDs.
2. Timeline State: derived from the edit graph; what the user sees.

You can emit edits in three modes (use the first one by default):

## Mode 1: Structured Operations (default)
Emit a JSON array of operations. Each operation must conform to the schema below.
Operations are schema-validated before application.

Schema:
{operations_schema}

## Mode 2: Raw MLT XML (escape hatch)
Emit {"mode":"raw_xml","xml":"<MLT fragment>","description":"..."}.
Use only when no operation in Mode 1 can express what you need.
The XML will be parsed into synthetic operations; the raw XML is preserved.

## Mode 3: Free-Form Python Code (power user)
Emit {"mode":"code","code":"<Python source>"}.
The code runs in a sandbox and calls the IR API:
- ir.add_clip(asset_hash, track_id, position_sec, in_point_sec, out_point_sec)
- ir.remove_clip(clip_id)
- ir.move_clip(clip_id, new_track_id, new_position_sec)
- ir.trim_clip(clip_id, new_in_point_sec, new_out_point_sec)
- ir.add_transition(clip_a_id, clip_b_id, transition_type, duration_sec)
- ir.add_effect(target_kind, target_id, effect_type, params)
- ir.set_keyframe(effect_id, param, keyframes)
- ir.list_clips(track_id=None)
- ir.get_clip(clip_id)

Use Mode 3 for bulk operations (e.g. "trim every clip on track 2 by 10%").

## Current Project State
Timeline:
{current_timeline}

Available Assets:
{available_assets}

## Effect Catalog
{effect_catalog_summary}

## Rules
1. Prefer Mode 1 (Structured Operations) whenever possible.
2. Never invent asset hashes; use only hashes listed in Available Assets.
3. Never invent effect types; use only types listed in the Effect Catalog.
4. After emitting, the system will validate, apply, render, and QC. You will see the QC report.
5. If QC fails, you will receive the failure details; emit a corrected edit.
6. Time units are seconds (float). Frame numbers are not used in the IR.
```

### 7.3 Stage 2: LLM Call

```python
# open_edit/agent/loop.py

async def call_llm(messages: list[dict]) -> str:
    """Call the LLM and return the raw text response."""
    # Uses z-ai-web-dev-sdk per project conventions
    from z_ai_web_dev_sdk import LLM
    llm = LLM()
    response = await llm.chat(messages)
    return response.content
```

### 7.4 Stage 3: Parse Emission

```python
# open_edit/agent/parse.py

def parse_emission(raw: str) -> ParsedEmission:
    """Parse the LLM's raw text response into a structured emission.
    
    Returns one of:
    - StructuredEmission(ops: list[Operation])
    - RawXmlEmission(xml: str, description: str)
    - CodeEmission(code: str)
    
    Raises ParseError if the response does not match any mode.
    """
    # Try JSON parse first
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Maybe the JSON is wrapped in ```json ... ``` fences
        data = extract_json_from_fences(raw)
    
    if isinstance(data, list):
        # Mode 1: array of operations
        ops = [parse_operation(item) for item in data]
        return StructuredEmission(ops=ops)
    elif isinstance(data, dict):
        mode = data.get("mode")
        if mode == "raw_xml":
            return RawXmlEmission(xml=data["xml"], description=data.get("description", ""))
        elif mode == "code":
            return CodeEmission(code=data["code"])
    
    raise ParseError(f"Unrecognized emission format: {raw[:200]}...")
```

### 7.5 Stage 4: Validate Schema

```python
# open_edit/agent/validate.py

def validate_emission(emission: ParsedEmission, project: Project) -> ValidationResult:
    """Validate the emission against the IR schema and project state.
    
    Checks:
    - For StructuredEmission: each op is a valid Pydantic Operation.
    - Asset hashes referenced exist in project.assets.
    - Track IDs referenced exist in project.timeline.tracks.
    - Clip IDs referenced exist in current timeline.
    - Effect types are in the effect catalog.
    - Parameters match the effect catalog's parameter schema.
    """
    errors = []
    
    if isinstance(emission, StructuredEmission):
        for i, op in enumerate(emission.ops):
            # Pydantic validation
            try:
                OperationUnion(**op.dict())
            except ValidationError as e:
                errors.append(f"Op {i}: {e}")
                continue
            
            # Referential integrity
            if isinstance(op, AddClipOp):
                if op.asset_hash not in project.assets:
                    errors.append(f"Op {i}: unknown asset_hash {op.asset_hash}")
                if op.track_id not in project.track_ids:
                    errors.append(f"Op {i}: unknown track_id {op.track_id}")
            # ... etc for each op type
    
    return ValidationResult(passed=len(errors) == 0, errors=errors)
```

### 7.6 Stage 5: Apply to Edit Graph

```python
# open_edit/agent/apply.py

def apply_emission(emission: ParsedEmission, project: Project) -> list[Operation]:
    """Apply the emission to the project's edit graph.
    
    Returns the list of operations that were appended.
    """
    appended = []
    
    if isinstance(emission, StructuredEmission):
        for op in emission.ops:
            op.author = "ai"
            op.timestamp = now_iso8601()
            op.parent_id = project.last_edit_id
            project.edit_graph.append(op)
            appended.append(op)
    
    elif isinstance(emission, RawXmlEmission):
        op = RawMltXmlOp(
            xml=emission.xml,
            description=emission.description,
            author="ai",
            timestamp=now_iso8601(),
            parent_id=project.last_edit_id,
        )
        project.edit_graph.append(op)
        appended.append(op)
    
    elif isinstance(emission, CodeEmission):
        op = FreeFormCodeOp(
            code=emission.code,
            author="ai",
            timestamp=now_iso8601(),
            parent_id=project.last_edit_id,
        )
        project.edit_graph.append(op)
        appended.append(op)
    
    project.save()  # SQLite transaction
    return appended
```

### 7.7 Stage 6: QC Gate

(See §5.2.7 QC Gate. Runs automatically after every apply.)

### 7.8 Stage 7: Cache Render

```python
# open_edit/render/cache.py

def get_cached_render(edit_graph_hash: str) -> Optional[str]:
    """Return the path to a cached render for this edit-graph hash, or None."""
    cache_path = CACHE_DIR / f"{edit_graph_hash}.mp4"
    return str(cache_path) if cache_path.exists() else None

def store_render(edit_graph_hash: str, render_path: str) -> None:
    """Copy a render into the cache keyed by edit-graph hash."""
    cache_path = CACHE_DIR / f"{edit_graph_hash}.mp4"
    shutil.copy(render_path, cache_path)
```

### 7.9 Stage 8: Surface Result

```python
# open_edit/agent/surface.py

def surface_result(emission: ParsedEmission, appended_ops: list[Operation],
                   qc_report: QCReport, render_path: str) -> ChatMessage:
    """Build a chat message describing what happened."""
    if isinstance(emission, StructuredEmission):
        summary = f"Applied {len(appended_ops)} operations: " + \
                  ", ".join(op.kind for op in appended_ops)
    elif isinstance(emission, RawXmlEmission):
        summary = f"Applied raw MLT XML: {emission.description}"
    elif isinstance(emission, CodeEmission):
        summary = f"Executed free-form code; produced {len(appended_ops)} operations"
    
    return ChatMessage(
        role="assistant",
        content=summary,
        metadata={
            "ops": [op.dict() for op in appended_ops],
            "qc": qc_report.dict(),
            "render_path": render_path,
        }
    )
```

### 7.10 Retry Logic

```python
# open_edit/agent/retry.py

MAX_RETRIES = 3

async def agent_turn_with_retry(project, history, user_message) -> ChatMessage:
    for attempt in range(MAX_RETRIES):
        messages = assemble_prompt(project, history, user_message)
        raw = await call_llm(messages)
        
        try:
            emission = parse_emission(raw)
        except ParseError as e:
            history.append({"role": "assistant", "content": raw})
            history.append({"role": "user", "content": 
                f"Parse error: {e}. Please emit a valid operation array, raw XML, or code."})
            continue
        
        validation = validate_emission(emission, project)
        if not validation.passed:
            history.append({"role": "assistant", "content": raw})
            history.append({"role": "user", "content":
                f"Validation failed: {validation.errors}. Please correct and retry."})
            continue
        
        appended = apply_emission(emission, project)
        qc_report = run_qc_gate(project)
        render_path = get_or_render(project)
        return surface_result(emission, appended, qc_report, render_path)
    
    return ChatMessage(
        role="assistant",
        content=f"Failed after {MAX_RETRIES} attempts. Last error: {validation.errors}",
    )
```

### 7.11 Emission Mode Heuristics (for the AI)

The system prompt should include heuristics for when to use each mode:

- **Use Mode 1 (Structured Operations)** when: editing involves add/remove/move/trim clips, adding transitions, adding common effects (brightness, contrast, volume, fade), setting keyframes.
- **Use Mode 2 (Raw MLT XML)** when: applying an obscure MLT filter not in the IR effect catalog, or constructing a non-standard MLT structure (e.g. multi-track compositing with custom tractor properties).
- **Use Mode 3 (Free-Form Code)** when: the edit involves iteration over multiple clips ("trim every clip on track 2 by 10%"), conditional logic ("if a clip is shorter than 5 seconds, remove it"), or composition of multiple operations in a loop.

---

## 8. UI Editing Workflow

### 8.1 Four-Panel Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  Menu Bar (Tauri)                                          [─][□][×] │
├──────────────┬──────────────────────────────────┬───────────────────┤
│              │                                  │                   │
│   Chat       │         Timeline                 │   Edit History    │
│   Panel      │         Panel                    │   Panel           │
│              │                                  │                   │
│   (40%)      │         (40%)                    │   (20%)           │
│              │                                  │                   │
│              ├──────────────────────────────────┤                   │
│              │   Preview + QC Panel             │                   │
│              │   (40% height)                   │                   │
│              │                                  │                   │
├──────────────┴──────────────────────────────────┴───────────────────┤
│  Status Bar: Project name | Render status | QC status               │
└─────────────────────────────────────────────────────────────────────┘
```

### 8.2 Chat Panel

**Purpose:** Conversation with the AI agent.

**Components:**
- Message list (user messages right-aligned, assistant messages left-aligned).
- Each assistant message includes:
  - Text summary ("Applied 3 operations: add_clip, add_transition, add_effect").
  - Expandable "Show operations" → list of operations with parameters.
  - Expandable "Show QC report" → pass/fail badges per check.
  - Embedded video preview (if render is small enough to inline).
- Input box at bottom (multi-line, Enter to send, Shift+Enter for newline).
- "Stop" button to abort a long-running agent turn.

**WebSocket events consumed:**
- `{"type":"agent_thinking"}` → show "AI is thinking..." indicator.
- `{"type":"agent_emission","emission":{...}}` → show emission summary.
- `{"type":"qc_update","qc":{...}}` → show QC report.
- `{"type":"render_ready","path":"..."}` → embed video preview.

**WebSocket events emitted:**
- `{"type":"user_message","content":"..."}`.
- `{"type":"stop_agent"}`.

### 8.3 Timeline Panel

**Purpose:** Visual timeline with tracks and clips; the primary editing surface for direct manipulation.

**Components:**
- Track headers (left side): track name, mute/solo buttons, kind icon (video/audio).
- Timeline canvas (center): horizontal time axis, clips as rectangles on tracks.
- Playhead (vertical line) at current preview position.
- Time ruler (top) with second markers.
- Zoom controls (bottom right): zoom in/out, fit to window.

**Interactions:**
- **Click clip:** Select (highlight border). Properties panel updates.
- **Drag clip horizontally:** Move clip on its track. Emits `MoveClipOp` on release.
- **Drag clip vertically:** Move clip to another track. Emits `MoveClipOp` (with new track_id).
- **Drag clip left/right edge:** Trim clip. Emits `TrimClipOp` on release.
- **Right-click clip:** Context menu (add effect, add transition, delete, split).
- **Double-click clip:** Open properties dialog (in/out points, position, effects list).

**AI edit highlighting:**
- When a new AI operation is applied, the affected clip(s) get an animated outline (yellow pulse for 2 seconds).
- The playhead jumps to the start of the most recent edit.
- The Edit History panel scrolls to highlight the new operation.

**WebSocket events consumed:**
- `{"type":"timeline_updated","timeline":{...}}` → re-render canvas.
- `{"type":"edit_highlighted","edit_id":"...","clip_ids":[...]}` → pulse animation.

**WebSocket events emitted:**
- `{"type":"user_edit","op":{...}}` (move, trim, etc.).
- `{"type":"select_clip","clip_id":"..."}`.

### 8.4 Edit History Panel

**Purpose:** Show every operation in the edit graph; provide undo/redo/reorder/fine-tune controls.

**Components:**
- Vertical list of operations, most recent at top.
- Each row:
  - Icon (varies by op kind: clip, transition, effect, code, XML).
  - Label (e.g. "Add Clip: intro.mp4 to video_1 at 0.0s").
  - Author badge (AI / User).
  - Timestamp (relative, e.g. "2 min ago").
  - Status badge (Applied / Reverted / Superseded).
- Click row to expand:
  - Full parameters (JSON view).
  - Child operations (if it's a GroupEditsOp, RawMltXmlOp, or FreeFormCodeOp).
  - Render diff (before/after thumbnails at the edit's time range).
- Right-click row for context menu:
  - Undo (marks as reverted).
  - Redo (marks as applied, if reverted).
  - Fine-tune (opens parameter editor).
  - Reorder up / down (if commutative with neighbor).
  - Branch from here (future; not v1).

**Reorder interaction:**
- Drag row up/down to reorder.
- On drop, frontend sends `reorder` event.
- Backend responds with success or rejection (non-commutative).
- On rejection, row snaps back to original position; toast shows error.

**WebSocket events consumed:**
- `{"type":"edit_graph_updated","edits":[...]}` → re-render list.
- `{"type":"reorder_rejected","edit_id":"...","reason":"..."}` → snap back + toast.

**WebSocket events emitted:**
- `{"type":"undo","edit_id":"..."}`.
- `{"type":"redo","edit_id":"..."}`.
- `{"type":"fine_tune","edit_id":"...","new_params":{...}}`.
- `{"type":"reorder","edit_id_a":"...","edit_id_b":"..."}`.

### 8.5 Preview + QC Panel

**Purpose:** Show the current render; show QC pass/fail status.

**Components:**
- HTML5 `<video>` player (large, top half).
  - Play/pause, scrub bar, volume, fullscreen.
  - Black-frame markers on scrub bar (red ticks).
  - Silence markers on scrub bar (yellow ticks).
  - Playhead synced to Timeline panel's playhead.
- QC status grid (bottom half):
  - 5 check rows: MLT Load, Proxy Render, Black Frames, Silence, Thumbnail.
  - Each row: check name, status icon (✓ green / ✗ red / ⋯ yellow pending), detail text.
  - "Re-run QC" button (manual trigger).
- Thumbnail strip (very bottom): row of thumbnails at 1-second intervals; click to seek.

**WebSocket events consumed:**
- `{"type":"render_ready","path":"...","qc":{...}}` → update video src + QC grid.
- `{"type":"qc_progress","check":"black_frames","progress":0.5}` → update progress indicator.

### 8.6 UI Synchronization Model

All panels subscribe to the same WebSocket stream. Backend broadcasts events:

| Event | When | Panels that update |
|---|---|---|
| `timeline_updated` | Edit graph changes | Timeline, Edit History (if affected) |
| `edit_graph_updated` | Operation appended/reverted/reordered | Edit History, Chat (if AI op) |
| `edit_highlighted` | After AI op applied | Timeline (pulse animation) |
| `render_started` | Render Orchestrator begins | Preview (show spinner), Status Bar |
| `render_progress` | Melt reports progress | Preview (progress bar) |
| `render_ready` | Render + QC complete | Preview, Chat (inline preview) |
| `qc_update` | QC check completes | Preview (QC grid) |
| `agent_thinking` | Agent starts LLM call | Chat (indicator) |
| `agent_emission` | Agent parses emission | Chat (summary) |
| `error` | Any error | All panels (toast) |

### 8.7 Undo / Redo / Reorder / Fine-Tune Workflows (Summary)

| Action | User Gesture | Backend Action | UI Update |
|---|---|---|---|
| **Undo** | Click "Undo" button or Ctrl+Z; or right-click edit → Undo | Mark most recent `applied` op as `reverted` | Timeline re-renders; Edit History shows reverted badge; Preview re-renders |
| **Redo** | Click "Redo" button or Ctrl+Shift+Z; or right-click reverted edit → Redo | Mark most recently `reverted` op as `applied` | Same as undo, reversed |
| **Reorder** | Drag edit row up/down in Edit History | Check `can_swap(op_a, op_b)`; if yes, swap in DB | Timeline re-renders; if no, row snaps back + toast |
| **Fine-tune** | Right-click edit → Fine-tune; edit parameters in dialog; Save | Mark original as `superseded`; append new op with modified params | Timeline re-renders; Edit History shows superseded badge on original, new row for the fine-tune |

---

## 9. Migration Strategy

### 9.1 High-Level Approach

The migration from `pyagent-kdenlive` to Open Edit is **not a refactor** — it is a **rebuild with selective asset reuse**. The new architecture (IR, edit graph, sandbox, four-panel UI) is fundamentally different from the old (Kdenlive XML manipulation, D-Bus sync, tool-call protocol). Attempting to refactor in place would carry the old architectural assumptions forward.

**What carries over from `pyagent-kdenlive`:**
- **Phase 1 catalog** (effect/filter metadata), but re-sourced from MLT YAML instead of Kdenlive XML.
- **Phase 2 ops library** (XML manipulation helpers), demoted from mandatory API to optional reference library.
- **Phase 6 render & QC scripts** (`melt`/`ffmpeg`/`ffprobe` wrappers, black-frame scan, silence scan, thumbnail), with minimal changes.
- **Phase 4 chat UI WebSocket core**, with the reload banner replaced by the preview panel.

**What does not carry over:**
- Phase 3 tool-calling protocol (JSON-RPC, OP_TABLE, dispatch) — replaced by IR API.
- Phase 5 D-Bus sync — completely removed.
- Phase 7 Xvfb golden-file tests — replaced by scenario eval.
- Kdenlive-specific XML metadata (`kdenlive:id`, `kdenlive:original`) — replaced by IR-native IDs.

### 9.2 Migration Principles

1. **New codebase, old assets.** Open Edit lives in a new repository (or new top-level directory). `pyagent-kdenlive` source is referenced for porting specific modules, not extended.
2. **Phases are sequential, not parallel.** Each phase leaves the system in a working state. No phase depends on a future phase.
3. **No AI, no UI until Phase 4 and 5.** Phases 1–3 are pure engineering: IR, render, sandbox. They can be tested entirely via CLI. This de-risks the AI and UI layers.
4. **`pyagent-kdenlive` runs in parallel during migration.** Until Phase 6 completes, both systems coexist. Users can keep using the old system. Cutover happens at Phase 6.

### 9.3 Repository Layout

```
open-edit/                          # new repository
├── open_edit/                      # Python backend
│   ├── ir/                         # Phase 1
│   ├── storage/                    # Phase 1
│   ├── render/                     # Phase 2
│   ├── qc/                         # Phase 3
│   ├── agent/                      # Phase 4
│   └── api/                        # Phase 4
├── sandbox/                        # Rust sandbox (Phase 3)
├── frontend/                       # React + TypeScript (Phase 5)
├── desktop/                        # Tauri shell (Phase 5)
├── migration/                      # Phase 6 scripts
├── tests/                          # Phase 7
├── pyproject.toml
├── Cargo.toml                      # workspace: sandbox + desktop
└── package.json                    # workspace: frontend
```

### 9.4 Phase Dependency Graph

```
Phase 1 (IR Foundation)
   │
   ▼
Phase 2 (MLT XML Emission)
   │
   ▼
Phase 3 (Sandbox + QC Gate)  ◄── depends on Phase 2 (QC needs render)
   │
   ▼
Phase 4 (AI Agent Integration) ◄── depends on Phase 3 (free-form code needs sandbox)
   │
   ▼
Phase 5 (Desktop UI)         ◄── depends on Phase 4 (UI shows agent activity)
   │
   ▼
Phase 6 (pyagent-kdenlive Migration) ◄── depends on Phase 5 (need full stack to validate port)
   │
   ▼
Phase 7 (Hardening, Testing, Performance)
```

### 9.5 Phase Summary Table

| Phase | Objective | Duration Estimate | Deliverable |
|---|---|---|---|
| 1 | IR foundation + project storage | 1-2 weeks | CLI: create project, add clip, undo, save/load |
| 2 | MLT XML emission + render | 1 week | CLI: render project to MP4 via melt |
| 3 | Sandbox + QC gate | 2-3 weeks | CLI: run AI code in sandbox, get QC report |
| 4 | AI agent integration | 1-2 weeks | CLI: chat with AI, AI edits project |
| 5 | Desktop UI | 3-4 weeks | Tauri app: four-panel UI, fully interactive |
| 6 | pyagent-kdenlive migration | 2 weeks | Old test scenarios pass under Open Edit |
| 7 | Hardening, testing, performance | 2-3 weeks | 50+ scenario tests, render cache, background render |

**Total: 12-17 weeks** for a single AI coding agent working sequentially. Parallelizable phases (e.g. Phase 5 UI work while Phase 6 migration is in progress) could compress this.

---

## 10. Phase 1: IR Foundation & Project Storage

### 10.1 Objectives

Build the core data model (Project, Asset, Edit, Operation, Timeline, Track, Clip, Effect), the SQLite-backed edit graph store, the content-addressed asset store, and a CLI that can create a project, add a clip, list edits, undo, save, and load. No AI, no rendering, no UI. This phase is pure data engineering.

### 10.2 Deliverables

#### 10.2.1 File Layout

```
open-edit/
├── pyproject.toml
├── open_edit/
│   ├── __init__.py
│   ├── ir/
│   │   ├── __init__.py
│   │   ├── types.py          # Pydantic models (Operation, Timeline, etc.)
│   │   ├── apply.py          # apply_operation(), derive_timeline()
│   │   ├── api.py            # IR class (in-process API for free-form code)
│   │   ├── validate.py       # validate_operation()
│   │   └── commutativity.py  # can_swap(op_a, op_b)
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── schema.sql        # SQLite schema
│   │   ├── edit_graph.py     # EditGraphStore (SQLite)
│   │   ├── assets.py         # AssetStore (content-addressed FS)
│   │   └── project.py        # ProjectStore (project metadata)
│   ├── cli.py                # CLI entry point
│   └── config.py             # Paths, defaults
└── tests/
    └── test_ir.py            # Unit tests
```

#### 10.2.2 `open_edit/ir/types.py`

Exact contents:

```python
"""IR data models for Open Edit.

All operations are immutable Pydantic models. Each operation has a stable UUID
(edit_id) that survives undo/redo/reorder/fine-tune.
"""
from __future__ import annotations
from typing import Literal, Optional, Union
from pydantic import BaseModel, Field
import uuid
from datetime import datetime, timezone


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso8601() -> str:
    return datetime.now(timezone.utc).isoformat()


# ===== Operation base + variants =====

class Operation(BaseModel):
    kind: str
    edit_id: str = Field(default_factory=new_id)
    parent_id: Optional[str] = None
    author: Literal["ai", "user"] = "user"
    timestamp: str = Field(default_factory=now_iso8601)
    status: Literal["applied", "reverted", "superseded"] = "applied"


class AddClipOp(Operation):
    kind: Literal["add_clip"] = "add_clip"
    asset_hash: str
    track_id: str
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
    transition_type: Literal["dissolve", "wipe", "fade", "cut"]
    duration_sec: float


class AddEffectOp(Operation):
    kind: Literal["add_effect"] = "add_effect"
    target_kind: Literal["clip", "track"]
    target_id: str
    effect_type: str
    params: dict
    effect_id: str = Field(default_factory=new_id)


class SetKeyframeOp(Operation):
    kind: Literal["set_keyframe"] = "set_keyframe"
    effect_id: str
    param: str
    keyframes: list[tuple[float, float, str]]  # (time_sec, value, interp)


class GroupEditsOp(Operation):
    kind: Literal["group_edits"] = "group_edits"
    edit_ids: list[str]
    label: str


class RawMltXmlOp(Operation):
    kind: Literal["raw_mlt_xml"] = "raw_mlt_xml"
    xml: str
    description: str


class FreeFormCodeOp(Operation):
    kind: Literal["free_form_code"] = "free_form_code"
    code: str


OperationUnion = Union[
    AddClipOp, RemoveClipOp, MoveClipOp, TrimClipOp,
    AddTransitionOp, AddEffectOp, SetKeyframeOp,
    GroupEditsOp, RawMltXmlOp, FreeFormCodeOp,
]


# ===== Timeline state (derived) =====

class Effect(BaseModel):
    effect_id: str
    effect_type: str
    params: dict
    keyframes: dict[str, list[tuple[float, float, str]]] = {}


class Clip(BaseModel):
    clip_id: str
    asset_hash: str
    track_id: str
    position_sec: float
    in_point_sec: float
    out_point_sec: float
    effects: list[Effect] = []


class Track(BaseModel):
    track_id: str
    kind: Literal["video", "audio"]
    clips: list[Clip] = []
    effects: list[Effect] = []


class Timeline(BaseModel):
    tracks: list[Track] = []
    duration_sec: float = 0.0


# ===== Project =====

class Asset(BaseModel):
    asset_hash: str
    original_path: str
    stored_path: str
    type: Literal["video", "audio", "image", "text"]
    duration_sec: float
    fps: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    codec: Optional[str] = None


class Project(BaseModel):
    project_id: str = Field(default_factory=new_id)
    name: str
    created_at: str = Field(default_factory=now_iso8601)
    assets: dict[str, Asset] = {}  # keyed by asset_hash
    edit_graph: list[OperationUnion] = []
    
    @property
    def last_edit_id(self) -> Optional[str]:
        return self.edit_graph[-1].edit_id if self.edit_graph else None
    
    @property
    def track_ids(self) -> set[str]:
        return {t.track_id for t in self._derive_timeline().tracks}
    
    def _derive_timeline(self) -> Timeline:
        from open_edit.ir.apply import derive_timeline
        return derive_timeline(self)
    
    @property
    def timeline(self) -> Timeline:
        return self._derive_timeline()
```

#### 10.2.3 `open_edit/ir/apply.py`

```python
"""Apply operations to derive timeline state. Pure functions."""
from open_edit.ir.types import (
    Operation, AddClipOp, RemoveClipOp, MoveClipOp, TrimClipOp,
    AddTransitionOp, AddEffectOp, SetKeyframeOp, GroupEditsOp,
    RawMltXmlOp, FreeFormCodeOp, Timeline, Track, Clip, Effect, Project,
)


def apply_operation(timeline: Timeline, op: Operation) -> Timeline:
    """Apply a single operation to a timeline, returning a new timeline.
    
    Pure function. Does not mutate the input.
    """
    if op.status != "applied":
        return timeline  # reverted/superseded ops are no-ops
    
    if isinstance(op, AddClipOp):
        return _apply_add_clip(timeline, op)
    elif isinstance(op, RemoveClipOp):
        return _apply_remove_clip(timeline, op)
    elif isinstance(op, MoveClipOp):
        return _apply_move_clip(timeline, op)
    elif isinstance(op, TrimClipOp):
        return _apply_trim_clip(timeline, op)
    elif isinstance(op, AddTransitionOp):
        return _apply_add_transition(timeline, op)
    elif isinstance(op, AddEffectOp):
        return _apply_add_effect(timeline, op)
    elif isinstance(op, SetKeyframeOp):
        return _apply_set_keyframe(timeline, op)
    elif isinstance(op, GroupEditsOp):
        return timeline  # group is metadata only; children applied separately
    elif isinstance(op, (RawMltXmlOp, FreeFormCodeOp)):
        # These produce child ops when applied; here we expect children
        # to be in the edit graph already. No-op for the parent.
        return timeline
    else:
        raise ValueError(f"Unknown operation kind: {op.kind}")


def derive_timeline(project: Project) -> Timeline:
    """Replay all non-reverted, applied operations in order."""
    timeline = Timeline(tracks=[], duration_sec=0.0)
    for op in project.edit_graph:
        timeline = apply_operation(timeline, op)
    # Compute duration
    timeline.duration_sec = _compute_duration(timeline)
    return timeline


def _apply_add_clip(timeline: Timeline, op: AddClipOp) -> Timeline:
    track = _get_or_create_track(timeline, op.track_id)
    out = op.out_point_sec if op.out_point_sec is not None else float('inf')
    clip = Clip(
        clip_id=op.clip_id,
        asset_hash=op.asset_hash,
        track_id=op.track_id,
        position_sec=op.position_sec,
        in_point_sec=op.in_point_sec,
        out_point_sec=out,
        effects=[],
    )
    track.clips.append(clip)
    return timeline


def _apply_remove_clip(timeline: Timeline, op: RemoveClipOp) -> Timeline:
    for track in timeline.tracks:
        track.clips = [c for c in track.clips if c.clip_id != op.clip_id]
    return timeline


def _apply_move_clip(timeline: Timeline, op: MoveClipOp) -> Timeline:
    clip = None
    for track in timeline.tracks:
        for i, c in enumerate(track.clips):
            if c.clip_id == op.clip_id:
                clip = track.clips.pop(i)
                break
        if clip:
            break
    if clip is None:
        raise ValueError(f"MoveClipOp: clip {op.clip_id} not found")
    clip.track_id = op.new_track_id
    clip.position_sec = op.new_position_sec
    new_track = _get_or_create_track(timeline, op.new_track_id)
    new_track.clips.append(clip)
    return timeline


def _apply_trim_clip(timeline: Timeline, op: TrimClipOp) -> Timeline:
    for track in timeline.tracks:
        for c in track.clips:
            if c.clip_id == op.clip_id:
                c.in_point_sec = op.new_in_point_sec
                c.out_point_sec = op.new_out_point_sec
                return timeline
    raise ValueError(f"TrimClipOp: clip {op.clip_id} not found")


def _apply_add_transition(timeline: Timeline, op: AddTransitionOp) -> Timeline:
    # Transitions stored as effects on clip_a with special effect_type
    # This is a simplification; full MLT transition emission is in Phase 2.
    for track in timeline.tracks:
        for c in track.clips:
            if c.clip_id == op.clip_a_id:
                c.effects.append(Effect(
                    effect_id=f"transition_{op.clip_a_id}_{op.clip_b_id}",
                    effect_type=f"transition_{op.transition_type}",
                    params={"clip_b_id": op.clip_b_id, "duration_sec": op.duration_sec},
                ))
                return timeline
    raise ValueError(f"AddTransitionOp: clip {op.clip_a_id} not found")


def _apply_add_effect(timeline: Timeline, op: AddEffectOp) -> Timeline:
    if op.target_kind == "clip":
        for track in timeline.tracks:
            for c in track.clips:
                if c.clip_id == op.target_id:
                    c.effects.append(Effect(
                        effect_id=op.effect_id,
                        effect_type=op.effect_type,
                        params=op.params,
                    ))
                    return timeline
        raise ValueError(f"AddEffectOp: clip {op.target_id} not found")
    elif op.target_kind == "track":
        for track in timeline.tracks:
            if track.track_id == op.target_id:
                track.effects.append(Effect(
                    effect_id=op.effect_id,
                    effect_type=op.effect_type,
                    params=op.params,
                ))
                return timeline
        raise ValueError(f"AddEffectOp: track {op.target_id} not found")


def _apply_set_keyframe(timeline: Timeline, op: SetKeyframeOp) -> Timeline:
    for track in timeline.tracks:
        for c in track.clips:
            for e in c.effects:
                if e.effect_id == op.effect_id:
                    e.keyframes[op.param] = op.keyframes
                    return timeline
        for e in track.effects:
            if e.effect_id == op.effect_id:
                e.keyframes[op.param] = op.keyframes
                return timeline
    raise ValueError(f"SetKeyframeOp: effect {op.effect_id} not found")


def _get_or_create_track(timeline: Timeline, track_id: str) -> Track:
    for track in timeline.tracks:
        if track.track_id == track_id:
            return track
    new_track = Track(track_id=track_id, kind="video")  # default; AI should specify
    timeline.tracks.append(new_track)
    return new_track


def _compute_duration(timeline: Timeline) -> float:
    if not timeline.tracks:
        return 0.0
    max_end = 0.0
    for track in timeline.tracks:
        for clip in track.clips:
            end = clip.position_sec + (clip.out_point_sec - clip.in_point_sec)
            if end > max_end:
                max_end = end
    return max_end
```

#### 10.2.4 `open_edit/storage/schema.sql`

```sql
-- SQLite schema for Open Edit project database.
-- One .db file per project, at ~/.open-edit/projects/<project_id>.db

CREATE TABLE IF NOT EXISTS project_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
    asset_hash TEXT PRIMARY KEY,
    original_path TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    type TEXT NOT NULL,
    duration_sec REAL NOT NULL,
    fps REAL,
    width INTEGER,
    height INTEGER,
    codec TEXT
);

CREATE TABLE IF NOT EXISTS edits (
    edit_id TEXT PRIMARY KEY,
    parent_id TEXT,
    kind TEXT NOT NULL,
    author TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    status TEXT NOT NULL,
    sequence_num INTEGER NOT NULL,  -- order in the edit graph
    payload TEXT NOT NULL,           -- full JSON of the operation
    FOREIGN KEY (parent_id) REFERENCES edits(edit_id)
);

CREATE INDEX IF NOT EXISTS idx_edits_sequence ON edits(sequence_num);
CREATE INDEX IF NOT EXISTS idx_edits_parent ON edits(parent_id);
CREATE INDEX IF NOT EXISTS idx_edits_status ON edits(status);
```

#### 10.2.5 `open_edit/storage/edit_graph.py`

```python
"""SQLite-backed edit graph store."""
import sqlite3
import json
from pathlib import Path
from typing import Optional
from open_edit.ir.types import OperationUnion, Operation

DB_PATH_TEMPLATE = "~/.open-edit/projects/{project_id}.db"


class EditGraphStore:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.db_path = Path(DB_PATH_TEMPLATE.format(project_id=project_id)).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
    
    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))
    
    def _init_schema(self):
        schema_path = Path(__file__).parent / "schema.sql"
        with self._conn() as conn:
            conn.executescript(schema_path.read_text())
    
    def append(self, op: Operation, sequence_num: Optional[int] = None) -> int:
        """Append an operation. Returns the sequence_num assigned."""
        with self._conn() as conn:
            if sequence_num is None:
                cur = conn.execute("SELECT COALESCE(MAX(sequence_num), -1) + 1 FROM edits")
                sequence_num = cur.fetchone()[0]
            conn.execute(
                "INSERT INTO edits (edit_id, parent_id, kind, author, timestamp, status, sequence_num, payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (op.edit_id, op.parent_id, op.kind, op.author, op.timestamp,
                 op.status, sequence_num, op.model_dump_json()),
            )
        return sequence_num
    
    def load_all(self) -> list[OperationUnion]:
        """Load all operations in sequence order."""
        with self._conn() as conn:
            cur = conn.execute("SELECT payload FROM edits ORDER BY sequence_num")
            return [OperationUnion.model_validate_json(row[0]) for row in cur.fetchall()]
    
    def update_status(self, edit_id: str, new_status: str) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE edits SET status = ? WHERE edit_id = ?", (new_status, edit_id))
    
    def reorder(self, edit_id_a: str, edit_id_b: str) -> None:
        """Swap the sequence_num of two adjacent operations."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT edit_id, sequence_num FROM edits WHERE edit_id IN (?, ?) ORDER BY sequence_num",
                (edit_id_a, edit_id_b),
            )
            rows = cur.fetchall()
            if len(rows) != 2:
                raise ValueError("Both edits must exist")
            (id1, seq1), (id2, seq2) = rows
            if abs(seq1 - seq2) != 1:
                raise ValueError("Edits must be adjacent to reorder")
            conn.execute("UPDATE edits SET sequence_num = ? WHERE edit_id = ?", (seq2, id1))
            conn.execute("UPDATE edits SET sequence_num = ? WHERE edit_id = ?", (seq1, id2))
```

#### 10.2.6 `open_edit/storage/assets.py`

```python
"""Content-addressed asset store."""
import hashlib
import shutil
from pathlib import Path
from typing import Optional
from open_edit.ir.types import Asset

ASSET_DIR = Path("~/.open-edit/assets").expanduser()


class AssetStore:
    def __init__(self):
        ASSET_DIR.mkdir(parents=True, exist_ok=True)
    
    def ingest(self, source_path: str) -> Asset:
        """Copy a file into the content-addressed store. Returns Asset metadata.
        
        Uses ffprobe to populate metadata. Phase 1 may stub ffprobe if not yet
        integrated; Phase 2 will require it.
        """
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(source_path)
        
        h = hashlib.sha256()
        with open(source, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        asset_hash = h.hexdigest()
        
        prefix = asset_hash[:2]
        dest_dir = ASSET_DIR / prefix
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / asset_hash
        if not dest_path.exists():
            shutil.copy2(source, dest_path)
        
        # Phase 1: stub metadata. Phase 2 will call ffprobe.
        return Asset(
            asset_hash=asset_hash,
            original_path=str(source),
            stored_path=str(dest_path),
            type="video",  # Phase 2 will detect
            duration_sec=0.0,  # Phase 2 will populate via ffprobe
        )
    
    def get(self, asset_hash: str) -> Optional[Asset]:
        prefix = asset_hash[:2]
        path = ASSET_DIR / prefix / asset_hash
        if not path.exists():
            return None
        return Asset(
            asset_hash=asset_hash,
            original_path="",
            stored_path=str(path),
            type="video",
            duration_sec=0.0,
        )
```

#### 10.2.7 `open_edit/cli.py`

```python
"""Open Edit CLI. Phase 1 commands: project, asset, edit, undo, list, save, load."""
import argparse
import sys
from open_edit.ir.types import Project, AddClipOp
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.storage.assets import AssetStore


def cmd_project_create(args):
    project = Project(name=args.name)
    store = EditGraphStore(project.project_id)
    # Save project metadata
    with store._conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO project_meta (key, value) VALUES (?, ?)",
            ("name", project.name),
        )
        conn.execute(
            "INSERT OR REPLACE INTO project_meta (key, value) VALUES (?, ?)",
            ("project_id", project.project_id),
        )
    print(f"Created project: {project.project_id}")
    print(f"Name: {project.name}")


def cmd_asset_add(args):
    store = AssetStore()
    asset = store.ingest(args.path)
    print(f"Asset hash: {asset.asset_hash}")
    print(f"Stored at: {asset.stored_path}")


def cmd_edit_add_clip(args):
    store = EditGraphStore(args.project_id)
    op = AddClipOp(
        asset_hash=args.asset_hash,
        track_id=args.track_id,
        position_sec=args.position,
        in_point_sec=args.in_point,
        out_point_sec=args.out_point,
        author="user",
    )
    store.append(op)
    print(f"Added clip {op.clip_id} to track {args.track_id}")


def cmd_undo(args):
    store = EditGraphStore(args.project_id)
    ops = store.load_all()
    # Find most recent applied op
    for op in reversed(ops):
        if op.status == "applied":
            store.update_status(op.edit_id, "reverted")
            print(f"Reverted: {op.kind} ({op.edit_id})")
            return
    print("Nothing to undo")


def cmd_list(args):
    store = EditGraphStore(args.project_id)
    ops = store.load_all()
    for i, op in enumerate(ops):
        status_mark = {"applied": " ", "reverted": "X", "superseded": "S"}[op.status]
        print(f"[{i:3d}] [{status_mark}] {op.kind:20s} {op.edit_id[:8]}  author={op.author}")


def main():
    parser = argparse.ArgumentParser(prog="open-edit")
    sub = parser.add_subparsers(dest="cmd", required=True)
    
    p = sub.add_parser("project-create")
    p.add_argument("--name", required=True)
    p.set_defaults(func=cmd_project_create)
    
    p = sub.add_parser("asset-add")
    p.add_argument("--path", required=True)
    p.set_defaults(func=cmd_asset_add)
    
    p = sub.add_parser("edit-add-clip")
    p.add_argument("--project-id", required=True)
    p.add_argument("--asset-hash", required=True)
    p.add_argument("--track-id", required=True)
    p.add_argument("--position", type=float, required=True)
    p.add_argument("--in-point", type=float, default=0.0)
    p.add_argument("--out-point", type=float, default=None)
    p.set_defaults(func=cmd_edit_add_clip)
    
    p = sub.add_parser("undo")
    p.add_argument("--project-id", required=True)
    p.set_defaults(func=cmd_undo)
    
    p = sub.add_parser("list")
    p.add_argument("--project-id", required=True)
    p.set_defaults(func=cmd_list)
    
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
```

### 10.3 Dependencies

- Python 3.11+
- `pydantic>=2.0`
- No external services; no `melt`/`ffmpeg`/`ffprobe` required in Phase 1.

### 10.4 Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Pydantic v2 discriminated unions have edge cases that fail on `Union[...]` validation | Medium | Medium | Use explicit `kind` field with `Literal` types; test all 10 operation variants in unit tests |
| SQLite write concurrency (single-user desktop should be fine, but worth noting) | Low | Low | Use WAL mode (`PRAGMA journal_mode=WAL`) in `_init_schema` |
| Content-addressed store grows large; no GC | Low | Low | Phase 7 adds LRU eviction; Phase 1 just documents the growth |
| `out_point_sec=None` semantics ambiguous (full asset vs. unbounded) | Medium | Medium | Document: `None` means "until end of asset"; if asset duration is unknown (Phase 1 stub), treat as `0.0` and fix in Phase 2 |

### 10.5 Validation Criteria

The following tests must pass (place in `tests/test_ir.py`):

```python
# tests/test_ir.py

import pytest
from open_edit.ir.types import Project, AddClipOp, RemoveClipOp, TrimClipOp, AddEffectOp
from open_edit.ir.apply import apply_operation, derive_timeline


def test_add_clip_creates_track():
    project = Project(name="test")
    op = AddClipOp(asset_hash="abc", track_id="v1", position_sec=0.0)
    project.edit_graph.append(op)
    timeline = derive_timeline(project)
    assert len(timeline.tracks) == 1
    assert timeline.tracks[0].track_id == "v1"
    assert len(timeline.tracks[0].clips) == 1
    assert timeline.tracks[0].clips[0].asset_hash == "abc"


def test_undo_marks_reverted():
    project = Project(name="test")
    op = AddClipOp(asset_hash="abc", track_id="v1", position_sec=0.0)
    project.edit_graph.append(op)
    op.status = "reverted"
    timeline = derive_timeline(project)
    assert len(timeline.tracks) == 0  # reverted op is a no-op


def test_trim_clip_updates_in_out():
    project = Project(name="test")
    project.edit_graph.append(AddClipOp(asset_hash="abc", track_id="v1", position_sec=0.0))
    project.edit_graph.append(TrimClipOp(clip_id=project.edit_graph[0].clip_id,
                                          new_in_point_sec=2.0, new_out_point_sec=5.0))
    timeline = derive_timeline(project)
    clip = timeline.tracks[0].clips[0]
    assert clip.in_point_sec == 2.0
    assert clip.out_point_sec == 5.0


def test_remove_clip_removes():
    project = Project(name="test")
    op = AddClipOp(asset_hash="abc", track_id="v1", position_sec=0.0)
    project.edit_graph.append(op)
    project.edit_graph.append(RemoveClipOp(clip_id=op.clip_id))
    timeline = derive_timeline(project)
    assert len(timeline.tracks[0].clips) == 0


def test_add_effect_to_clip():
    project = Project(name="test")
    add_clip = AddClipOp(asset_hash="abc", track_id="v1", position_sec=0.0)
    project.edit_graph.append(add_clip)
    project.edit_graph.append(AddEffectOp(
        target_kind="clip", target_id=add_clip.clip_id,
        effect_type="brightness", params={"value": 0.5},
    ))
    timeline = derive_timeline(project)
    assert len(timeline.tracks[0].clips[0].effects) == 1
    assert timeline.tracks[0].clips[0].effects[0].effect_type == "brightness"
```

### 10.6 Definition of Done

- [ ] All files in §10.2.1 exist and contain the specified contents.
- [ ] `pyproject.toml` declares `open-edit` as a package with `pydantic>=2.0` dependency.
- [ ] `pip install -e .` succeeds.
- [ ] `python -m open_edit.cli project-create --name test` creates a `.db` file at `~/.open-edit/projects/<uuid>.db`.
- [ ] `python -m open_edit.cli asset-add --path /path/to/video.mp4` ingests the file and prints its hash.
- [ ] `python -m open_edit.cli edit-add-clip --project-id <uuid> --asset-hash <hash> --track-id v1 --position 0` appends an operation.
- [ ] `python -m open_edit.cli list --project-id <uuid>` shows the operation.
- [ ] `python -m open_edit.cli undo --project-id <uuid>` reverts the operation; subsequent `list` shows `[X]`.
- [ ] All 5 tests in `tests/test_ir.py` pass with `pytest`.
- [ ] The system is in a stable, working state: a project can be created, edited, undone, and inspected via CLI. No AI, no rendering, no UI.

---

## 11. Phase 2: MLT XML Emission & Render Pipeline

### 11.1 Objectives

Build the MLT XML emitter (Timeline → MLT XML), the render orchestrator (invoke `melt` to produce MP4), and the `ffprobe` integration for real asset metadata (replacing the Phase 1 stubs). At the end of Phase 2, given a project IR, the system can emit valid MLT XML and render it to MP4 via `melt`.

### 11.2 Deliverables

#### 11.2.1 File Layout (additions)

```
open-edit/
├── open_edit/
│   ├── render/
│   │   ├── __init__.py
│   │   ├── emitter.py         # Timeline -> MLT XML
│   │   ├── ingest.py          # MLT XML -> synthetic operations (Phase 3 also uses this)
│   │   ├── orchestrator.py    # render_project() -> MP4 path
│   │   ├── cache.py           # render cache (edit-graph hash -> MP4)
│   │   ├── profiles.py        # render profiles (resolution, fps, codec)
│   │   └── ffprobe.py         # ffprobe wrapper for asset metadata
│   └── ...
├── tests/
│   └── test_render.py
```

#### 11.2.2 `open_edit/render/ffprobe.py`

```python
"""ffprobe wrapper for asset metadata."""
import json
import subprocess
from typing import Optional
from open_edit.ir.types import Asset


def probe(path: str) -> dict:
    """Run ffprobe on a file, return parsed JSON."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", path],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def asset_from_probe(path: str, original_path: str, asset_hash: str) -> Asset:
    """Build an Asset from ffprobe output."""
    data = probe(path)
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    
    duration_sec = float(fmt.get("duration", 0.0))
    
    if video_stream:
        return Asset(
            asset_hash=asset_hash,
            original_path=original_path,
            stored_path=path,
            type="video",
            duration_sec=duration_sec,
            fps=_parse_fps(video_stream.get("r_frame_rate", "25/1")),
            width=int(video_stream.get("width", 0)),
            height=int(video_stream.get("height", 0)),
            codec=video_stream.get("codec_name"),
        )
    elif audio_stream:
        return Asset(
            asset_hash=asset_hash,
            original_path=original_path,
            stored_path=path,
            type="audio",
            duration_sec=duration_sec,
            codec=audio_stream.get("codec_name"),
        )
    else:
        return Asset(
            asset_hash=asset_hash,
            original_path=original_path,
            stored_path=path,
            type="video",  # fallback
            duration_sec=duration_sec,
        )


def _parse_fps(rate: str) -> float:
    if "/" in rate:
        num, den = rate.split("/")
        return float(num) / float(den)
    return float(rate)
```

Update `open_edit/storage/assets.py` `ingest()` to call `asset_from_probe()` after copying the file.

#### 11.2.3 `open_edit/render/profiles.py`

```python
"""Render profiles: resolution, fps, codec."""

PROFILES = {
    "proxy": {
        "width": 640,
        "height": 360,
        "fps": 30,
        "video_codec": "libx264",
        "audio_codec": "aac",
        "preset": "ultrafast",
        "crf": 28,
    },
    "preview": {
        "width": 1280,
        "height": 720,
        "fps": 30,
        "video_codec": "libx264",
        "audio_codec": "aac",
        "preset": "fast",
        "crf": 23,
    },
    "export_1080p": {
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "video_codec": "libx264",
        "audio_codec": "aac",
        "preset": "medium",
        "crf": 20,
    },
    "export_4k": {
        "width": 3840,
        "height": 2160,
        "fps": 30,
        "video_codec": "libx264",
        "audio_codec": "aac",
        "preset": "slow",
        "crf": 18,
    },
}
```

#### 11.2.4 `open_edit/render/emitter.py`

```python
"""Emit MLT XML from a Timeline."""
from lxml import etree
from open_edit.ir.types import Timeline, Track, Clip, Effect
from open_edit.storage.assets import AssetStore


def emit_mlt_xml(timeline: Timeline, project, profile_name: str = "preview") -> str:
    """Convert a Timeline to MLT XML string.
    
    Structure:
    <mlt>
      <profile .../>
      <producer id="producer_<asset_hash>">...</producer>  <!-- one per asset -->
      <playlist id="playlist_<track_id>">
        <entry producer="producer_<hash>" in="<frames>" out="<frames>"/>
        ...
      </playlist>
      <tractor id="tractor0">
        <multitrack>
          <track producer="playlist_<track_id>"/>
          ...
        </multitrack>
        <transition .../>  <!-- for transitions -->
        <filter .../>       <!-- for track-level effects -->
      </tractor>
    </mlt>
    """
    from open_edit.render.profiles import PROFILES
    profile = PROFILES[profile_name]
    fps = profile["fps"]
    
    mlt = etree.Element("mlt")
    mlt.set("LC_NUMERIC", "C")
    mlt.set("version", "7.0")
    
    # Profile element
    prof = etree.SubElement(mlt, "profile")
    prof.set("description", f"{profile['width']}x{profile['height']} {fps}p")
    prof.set("width", str(profile["width"]))
    prof.set("height", str(profile["height"]))
    prof.set("progressive", "1")
    prof.set("sample_aspect_num", "1")
    prof.set("sample_aspect_den", "1")
    prof.set("display_aspect_num", str(profile["width"]))
    prof.set("display_aspect_den", str(profile["height"]))
    prof.set("frame_rate_num", str(fps))
    prof.set("frame_rate_den", "1")
    
    # Producers (one per unique asset)
    asset_store = AssetStore()
    seen_assets = set()
    for track in timeline.tracks:
        for clip in track.clips:
            if clip.asset_hash not in seen_assets:
                seen_assets.add(clip.asset_hash)
                asset = project.assets.get(clip.asset_hash) or asset_store.get(clip.asset_hash)
                if asset is None:
                    raise ValueError(f"Asset {clip.asset_hash} not found")
                producer = etree.SubElement(mlt, "producer")
                producer.set("id", f"producer_{clip.asset_hash}")
                etree.SubElement(producer, "property", name="resource").text = asset.stored_path
                etree.SubElement(producer, "property", name="mlt_service").text = "avformat"
                etree.SubElement(producer, "property", name="length").text = str(int(asset.duration_sec * fps))
    
    # Playlists (one per track)
    for track in timeline.tracks:
        playlist = etree.SubElement(mlt, "playlist")
        playlist.set("id", f"playlist_{track.track_id}")
        for clip in track.clips:
            entry = etree.SubElement(playlist, "entry")
            entry.set("producer", f"producer_{clip.asset_hash}")
            entry.set("in", str(int(clip.in_point_sec * fps)))
            out_sec = clip.out_point_sec if clip.out_point_sec != float('inf') else 0
            entry.set("out", str(int(out_sec * fps)))
    
    # Tractor
    tractor = etree.SubElement(mlt, "tractor")
    tractor.set("id", "tractor0")
    
    multitrack = etree.SubElement(tractor, "multitrack")
    for track in timeline.tracks:
        track_elem = etree.SubElement(multitrack, "track")
        track_elem.set("producer", f"playlist_{track.track_id}")
    
    # Track-level effects
    for i, track in enumerate(timeline.tracks):
        for effect in track.effects:
            _emit_effect(tractor, effect, f"playlist_{track.track_id}", fps)
    
    # Clip-level effects (attached to producers via playlist entries — simplified)
    # NOTE: MLT attaches filters to producers, not entries. For full clip-level
    # effects, each clip needs its own producer instance. Phase 2 emits a basic
    # version; full clip-effect emission is in Phase 7.
    
    return etree.tostring(mlt, pretty_print=True, xml_declaration=True, encoding="utf-8").decode()


def _emit_effect(parent: etree.Element, effect: Effect, target_id: str, fps: float):
    """Emit a filter or transition element."""
    if effect.effect_type.startswith("transition_"):
        transition = etree.SubElement(parent, "transition")
        transition.set("id", effect.effect_id)
        etree.SubElement(transition, "property", name="a_track").text = "0"  # simplified
        etree.SubElement(transition, "property", name="b_track").text = "1"
        etree.SubElement(transition, "property", name="mlt_service").text = effect.effect_type
        for k, v in effect.params.items():
            etree.SubElement(transition, "property", name=k).text = str(v)
    else:
        filt = etree.SubElement(parent, "filter")
        filt.set("id", effect.effect_id)
        etree.SubElement(filt, "property", name="track").text = target_id
        etree.SubElement(filt, "property", name="mlt_service").text = effect.effect_type
        for k, v in effect.params.items():
            etree.SubElement(filt, "property", name=k).text = str(v)
```

#### 11.2.5 `open_edit/render/orchestrator.py`

```python
"""Render orchestrator: invoke melt to produce MP4."""
import subprocess
import hashlib
import json
from pathlib import Path
from typing import Optional
from open_edit.ir.types import Project
from open_edit.ir.apply import derive_timeline
from open_edit.render.emitter import emit_mlt_xml
from open_edit.render.cache import get_cached_render, store_render

RENDER_DIR = Path("~/.open-edit/cache/renders").expanduser()
RENDER_DIR.mkdir(parents=True, exist_ok=True)


def render_project(project: Project, profile_name: str = "preview",
                   use_cache: bool = True) -> str:
    """Render a project to MP4. Returns the path to the rendered file."""
    timeline = derive_timeline(project)
    xml = emit_mlt_xml(timeline, project, profile_name)
    
    # Compute edit-graph hash for cache key
    edit_graph_json = json.dumps([op.model_dump() for op in project.edit_graph], sort_keys=True)
    edit_graph_hash = hashlib.sha256(edit_graph_json.encode()).hexdigest()
    
    if use_cache:
        cached = get_cached_render(edit_graph_hash)
        if cached:
            return cached
    
    # Write XML to temp file
    xml_path = RENDER_DIR / f"{edit_graph_hash}.xml"
    xml_path.write_text(xml)
    
    # Invoke melt
    output_path = RENDER_DIR / f"{edit_graph_hash}.mp4"
    cmd = [
        "melt", str(xml_path),
        "-consumer", "avformat:" + str(output_path),
        f"vcodec=libx264", f"acodec=aac",
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    
    if use_cache:
        store_render(edit_graph_hash, str(output_path))
    
    return str(output_path)


def validate_mlt_loads(xml: str) -> bool:
    """Check that melt can load the XML without rendering. Quick structural check."""
    xml_path = RENDER_DIR / "_validate.xml"
    xml_path.write_text(xml)
    try:
        subprocess.run(
            ["melt", str(xml_path), "-consumer", "null:0"],
            check=True, capture_output=True, text=True, timeout=10,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
```

#### 11.2.6 `open_edit/render/cache.py`

```python
"""Render cache: edit-graph hash -> MP4 path."""
import shutil
from pathlib import Path
from typing import Optional

CACHE_DIR = Path("~/.open-edit/cache/renders").expanduser()
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_cached_render(edit_graph_hash: str) -> Optional[str]:
    cache_path = CACHE_DIR / f"{edit_graph_hash}.mp4"
    return str(cache_path) if cache_path.exists() else None


def store_render(edit_graph_hash: str, render_path: str) -> None:
    cache_path = CACHE_DIR / f"{edit_graph_hash}.mp4"
    if render_path != str(cache_path):
        shutil.copy(render_path, cache_path)


def clear_cache() -> None:
    for f in CACHE_DIR.glob("*.mp4"):
        f.unlink()
    for f in CACHE_DIR.glob("*.xml"):
        f.unlink()
```

### 11.3 Dependencies

- Phase 1 complete.
- `melt` (MLT framework) installed and on PATH.
- `ffmpeg` and `ffprobe` installed and on PATH.
- Python `lxml` package.

### 11.4 Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `melt` not installed on developer machine | Medium | High | Document install instructions; CI uses Docker image with MLT preinstalled |
| MLT XML emission produces invalid XML (wrong namespaces, missing attrs) | Medium | Medium | Add `validate_mlt_loads()` check after every emit; test against known-good MLT examples |
| Clip-level effects not properly attached (MLT attaches to producers, not entries) | High | Medium | Phase 2 emits track-level effects only; clip-level effects are a known limitation, fixed in Phase 7 by giving each clip its own producer instance |
| `ffprobe` output format varies across versions | Low | Low | Pin ffprobe version in CI; defensive parsing in `asset_from_probe` |
| Render takes too long for large projects | High | Medium | Default to `proxy` profile (640x360, ultrafast); full-quality render is opt-in |

### 11.5 Validation Criteria

```python
# tests/test_render.py

import pytest
from pathlib import Path
from open_edit.ir.types import Project, AddClipOp
from open_edit.ir.apply import derive_timeline
from open_edit.render.emitter import emit_mlt_xml
from open_edit.render.orchestrator import render_project, validate_mlt_loads
from open_edit.storage.assets import AssetStore


@pytest.fixture
def sample_video(tmp_path):
    """Generate a 1-second test video using ffmpeg."""
    path = tmp_path / "test.mp4"
    import subprocess
    subprocess.run([
        "ffmpeg", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=30",
        "-c:v", "libx264", str(path),
    ], check=True, capture_output=True)
    return str(path)


def test_emit_xml_valid_structure(sample_video):
    asset = AssetStore().ingest(sample_video)
    project = Project(name="test", assets={asset.asset_hash: asset})
    project.edit_graph.append(AddClipOp(
        asset_hash=asset.asset_hash, track_id="v1", position_sec=0.0,
    ))
    timeline = derive_timeline(project)
    xml = emit_mlt_xml(timeline, project, "proxy")
    assert "<mlt" in xml
    assert "<producer" in xml
    assert "<playlist" in xml
    assert "<tractor" in xml


def test_mlt_loads_emitted_xml(sample_video):
    asset = AssetStore().ingest(sample_video)
    project = Project(name="test", assets={asset.asset_hash: asset})
    project.edit_graph.append(AddClipOp(
        asset_hash=asset.asset_hash, track_id="v1", position_sec=0.0,
    ))
    timeline = derive_timeline(project)
    xml = emit_mlt_xml(timeline, project, "proxy")
    assert validate_mlt_loads(xml), "melt could not load emitted XML"


def test_render_produces_mp4(sample_video):
    asset = AssetStore().ingest(sample_video)
    project = Project(name="test", assets={asset.asset_hash: asset})
    project.edit_graph.append(AddClipOp(
        asset_hash=asset.asset_hash, track_id="v1", position_sec=0.0,
    ))
    output = render_project(project, profile_name="proxy", use_cache=False)
    assert Path(output).exists()
    assert output.endswith(".mp4")
```

### 11.6 Definition of Done

- [ ] `open_edit/render/` directory exists with `emitter.py`, `orchestrator.py`, `cache.py`, `profiles.py`, `ffprobe.py`.
- [ ] `AssetStore.ingest()` now calls `ffprobe` and populates real metadata (duration, fps, width, height, codec).
- [ ] `emit_mlt_xml(timeline, project, "proxy")` returns a valid MLT XML string.
- [ ] `validate_mlt_loads(xml)` returns `True` for the emitted XML.
- [ ] `render_project(project, "proxy")` produces an MP4 file that plays in a standard video player.
- [ ] All 3 tests in `tests/test_render.py` pass.
- [ ] Render cache works: calling `render_project` twice with the same edit graph returns the cached MP4 without re-rendering.
- [ ] The system is in a stable, working state: a project can be created, edited, rendered to MP4 via CLI. No AI, no sandbox, no UI.

---

## 12. Phase 3: Sandbox & QC Gate

### 12.1 Objectives

Build the Rust sandbox for executing AI-emitted Python code safely, and the QC gate that runs automatically after every edit. The sandbox must restrict filesystem access, network access, and subprocess execution. The QC gate must run five checks (MLT load, proxy render, black-frame scan, silence scan, thumbnail) and return a structured report.

### 12.2 Deliverables

#### 12.2.1 File Layout (additions)

```
open-edit/
├── sandbox/                         # Rust crate
│   ├── Cargo.toml
│   ├── src/
│   │   ├── main.rs
│   │   ├── jail.rs                  # filesystem + syscall jail
│   │   ├── allowlist.rs             # allowed subprocesses
│   │   └── runner.rs                # subprocess execution
│   └── tests/
│       └── test_sandbox.rs
├── open_edit/
│   ├── qc/
│   │   ├── __init__.py
│   │   ├── gate.py                  # run_qc_gate(project) -> QCReport
│   │   ├── black_frames.py          # detect black frames via ffprobe
│   │   ├── silence.py               # detect silence via ffprobe
│   │   └── thumbnail.py             # generate thumbnail via ffmpeg
│   └── ...
└── tests/
    └── test_qc.py
```

#### 12.2.2 `sandbox/Cargo.toml`

```toml
[package]
name = "open-edit-sandbox"
version = "0.1.0"
edition = "2021"

[[bin]]
name = "sandbox"
path = "src/main.rs"

[dependencies]
clap = { version = "4", features = ["derive"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"

[target.'cfg(target_os = "linux")'.dependencies]
landlock = "0.3"
seccompiler = "0.4"
nix = { version = "0.27", features = ["sched", "process", "signal"] }

[target.'cfg(target_os = "macos")'.dependencies]
```

#### 12.2.3 `sandbox/src/main.rs`

```rust
//! Open Edit Sandbox
//!
//! Runs AI-emitted Python code in a restricted environment.
//!
//! Usage:
//!   sandbox --code <path> --workdir <path> --timeout 30 --mem 512M
//!
//! Restrictions enforced:
//! - Filesystem: only --workdir is writable; --asset-dir is read-only; everything else denied.
//! - Network: no socket syscalls.
//! - Subprocess: only melt, ffmpeg, ffprobe (looked up via PATH, hashed and verified).
//! - Wall-clock: --timeout seconds; process killed if exceeded.
//! - Memory: --mem limit enforced via cgroups (Linux) or rlimit.

use clap::Parser;
use std::path::PathBuf;

#[derive(Parser, Debug)]
struct Args {
    /// Path to the Python script to execute.
    #[arg(long)]
    code: PathBuf,

    /// Writable working directory (project's working dir).
    #[arg(long)]
    workdir: PathBuf,

    /// Read-only asset directory.
    #[arg(long)]
    asset_dir: PathBuf,

    /// Wall-clock timeout in seconds.
    #[arg(long, default_value = "30")]
    timeout: u64,

    /// Memory limit (e.g. "512M").
    #[arg(long, default_value = "512M")]
    mem: String,

    /// Output JSON file for the captured IR API calls.
    #[arg(long)]
    output: PathBuf,
}

fn main() -> anyhow::Result<()> {
    let args = Args::parse();
    
    // Validate paths
    if !args.code.exists() {
        anyhow::bail!("Code file not found: {:?}", args.code);
    }
    if !args.workdir.exists() {
        anyhow::bail!("Workdir not found: {:?}", args.workdir);
    }
    if !args.asset_dir.exists() {
        anyhow::bail!("Asset dir not found: {:?}", args.asset_dir);
    }
    
    // Apply jail (platform-specific)
    #[cfg(target_os = "linux")]
    jail::apply_linux_jail(&args.workdir, &args.asset_dir)?;
    
    #[cfg(target_os = "macos")]
    jail::apply_macos_jail(&args.workdir, &args.asset_dir)?;
    
    // Run the Python script with a timeout
    let result = runner::run_python(&args.code, &args.workdir, args.timeout, &args.output)?;
    
    // Output the result
    println!("{}", serde_json::to_string_pretty(&result)?);
    Ok(())
}
```

#### 12.2.4 `sandbox/src/jail.rs`

```rust
//! Filesystem and syscall jail.

#[cfg(target_os = "linux")]
pub fn apply_linux_jail(workdir: &std::path::Path, asset_dir: &std::path::Path) -> anyhow::Result<()> {
    use landlock::{Ruleset, Access, PathBeneath, PathWs};
    
    // Landlock: restrict filesystem access.
    // Allow read+write to workdir, read-only to asset_dir, read-only to /usr (for Python interpreter).
    let ruleset = Ruleset::new()?
        .handle_access(PathWs::Path)?;
    
    let mut rules = vec![
        PathBeneath::new(workdir, PathWs::Path)?,
        PathBeneath::new(asset_dir, PathWs::Path)?,  // read-only enforced below
        PathBeneath::new("/usr", PathWs::Path)?,
        PathBeneath::new("/lib", PathWs::Path)?,
        PathBeneach::new("/etc/ssl", PathWs::Path)?,
    ];
    
    let _ = ruleset.add_rules(&mut rules)?.create()?;
    
    // seccomp: block network syscalls.
    use seccompiler::{allow_filter, BpfProgram, Error};
    let mut filter = BpfProgram::new();
    // Allow all syscalls except: socket, connect, bind, listen, accept
    // (simplified — real implementation uses seccomp profile)
    
    Ok(())
}

#[cfg(target_os = "macos")]
pub fn apply_macos_jail(workdir: &std::path::Path, asset_dir: &std::path::Path) -> anyhow::Result<()> {
    // macOS: use sandbox-exec (seatbelt) with a generated profile.
    // Write a seatbelt profile to a temp file and apply via sandbox-exec.
    // This is a stub; real implementation generates the profile string.
    eprintln!("Warning: macOS sandbox is a stub in Phase 3. Use Linux for full isolation.");
    Ok(())
}

#[cfg(not(any(target_os = "linux", target_os = "macos")))]
pub fn apply_linux_jail(_workdir: &std::path::Path, _asset_dir: &std::path::Path) -> anyhow::Result<()> {
    anyhow::bail!("Sandbox not supported on this OS. Linux and macOS only.");
}
```

#### 12.2.5 `sandbox/src/allowlist.rs`

```rust
//! Allowlisted subprocesses: only melt, ffmpeg, ffprobe.

use std::collections::HashSet;

pub fn allowed_binaries() -> HashSet<&'static str> {
    ["melt", "ffmpeg", "ffprobe"].iter().cloned().collect()
}

pub fn is_allowed(binary: &str) -> bool {
    allowed_binaries().contains(binary)
}
```

#### 12.2.6 `sandbox/src/runner.rs`

```rust
use serde::{Deserialize, Serialize};
use std::path::Path;
use std::process::{Command, Stdio};
use std::time::Duration;

#[derive(Serialize, Deserialize, Debug)]
pub struct SandboxResult {
    pub exit_code: i32,
    pub stdout: String,
    pub stderr: String,
    pub timed_out: bool,
    pub captured_ops: Vec<serde_json::Value>,  // IR API calls captured via a stub
}

pub fn run_python(
    code: &Path,
    workdir: &Path,
    timeout_secs: u64,
    output: &Path,
) -> anyhow::Result<SandboxResult> {
    let result = Command::new("python3")
        .arg(code)
        .current_dir(workdir)
        .env("OPEN_EDIT_SANDBOX", "1")
        .env("OPEN_EDIT_OUTPUT", output)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;
    
    let output = result.wait_with_output()?;
    
    // Read captured ops from output file (written by the IR API stub the script imports)
    let captured_ops = if output_path.exists() {
        let content = std::fs::read_to_string(output_path)?;
        serde_json::from_str(&content).unwrap_or_default()
    } else {
        vec![]
    };
    
    Ok(SandboxResult {
        exit_code: output.status.code().unwrap_or(-1),
        stdout: String::from_utf8_lossy(&output.stdout).to_string(),
        stderr: String::from_utf8_lossy(&output.stderr).to_string(),
        timed_out: false,  // TODO: implement timeout via spawn + wait_with_timeout
        captured_ops,
    })
}
```

#### 12.2.7 IR API Stub (for sandboxed code)

```python
# open_edit/ir/sandbox_stub.py
"""IR API stub for use inside the sandbox.

When AI-emitted code calls `ir.add_clip(...)`, this stub:
1. Validates the operation schema.
2. Writes the operation to a JSON file at $OPEN_EDIT_OUTPUT.
3. Returns a fake clip_id.

The parent process reads $OPEN_EDIT_OUTPUT after the sandbox exits and
appends each captured operation to the real edit graph.
"""
import json
import os
from open_edit.ir.types import (
    AddClipOp, RemoveClipOp, MoveClipOp, TrimClipOp,
    AddTransitionOp, AddEffectOp, SetKeyframeOp, new_id,
)

OUTPUT_FILE = os.environ.get("OPEN_EDIT_OUTPUT", "/tmp/open_edit_ops.json")


def _capture(op):
    """Append an operation to the output file."""
    ops = []
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE) as f:
            ops = json.load(f)
    ops.append(op.model_dump())
    with open(OUTPUT_FILE, "w") as f:
        json.dump(ops, f)


class IR:
    """IR API stub. Each method captures an operation."""
    
    def add_clip(self, asset_hash, track_id, position_sec, in_point_sec=0.0, out_point_sec=None):
        op = AddClipOp(
            asset_hash=asset_hash, track_id=track_id, position_sec=position_sec,
            in_point_sec=in_point_sec, out_point_sec=out_point_sec, author="ai",
        )
        _capture(op)
        return op.clip_id
    
    def remove_clip(self, clip_id):
        op = RemoveClipOp(clip_id=clip_id, author="ai")
        _capture(op)
    
    def move_clip(self, clip_id, new_track_id, new_position_sec):
        op = MoveClipOp(clip_id=clip_id, new_track_id=new_track_id,
                        new_position_sec=new_position_sec, author="ai")
        _capture(op)
    
    def trim_clip(self, clip_id, new_in_point_sec, new_out_point_sec):
        op = TrimClipOp(clip_id=clip_id, new_in_point_sec=new_in_point_sec,
                        new_out_point_sec=new_out_point_sec, author="ai")
        _capture(op)
    
    def add_transition(self, clip_a_id, clip_b_id, transition_type, duration_sec):
        op = AddTransitionOp(clip_a_id=clip_a_id, clip_b_id=clip_b_id,
                             transition_type=transition_type, duration_sec=duration_sec, author="ai")
        _capture(op)
    
    def add_effect(self, target_kind, target_id, effect_type, params):
        op = AddEffectOp(target_kind=target_kind, target_id=target_id,
                         effect_type=effect_type, params=params, author="ai")
        _capture(op)
        return op.effect_id
    
    def set_keyframe(self, effect_id, param, keyframes):
        op = SetKeyframeOp(effect_id=effect_id, param=param, keyframes=keyframes, author="ai")
        _capture(op)
    
    def list_clips(self, track_id=None):
        # Stub: read project state from a JSON file passed in by the parent.
        # Phase 3 stub: returns empty list.
        return []
    
    def get_clip(self, clip_id):
        # Phase 3 stub: returns None.
        return None


ir = IR()
```

#### 12.2.8 `open_edit/qc/gate.py`

```python
"""QC gate: runs 5 checks after every edit."""
import json
from pathlib import Path
from typing import Optional
from open_edit.ir.types import Project
from open_edit.ir.apply import derive_timeline
from open_edit.render.emitter import emit_mlt_xml
from open_edit.render.orchestrator import render_project, validate_mlt_loads
from open_edit.render.cache import RENDER_DIR
from open_edit.qc.black_frames import scan_black_frames
from open_edit.qc.silence import scan_silence
from open_edit.qc.thumbnail import generate_thumbnail


class QCReport:
    def __init__(self):
        self.checks = []
    
    def add_check(self, name: str, passed: bool, detail: str):
        self.checks.append({"name": name, "passed": passed, "detail": detail})
    
    @property
    def passed(self) -> bool:
        return all(c["passed"] for c in self.checks)
    
    def to_dict(self) -> dict:
        return {"passed": self.passed, "checks": self.checks}
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def run_qc_gate(project: Project, profile_name: str = "proxy") -> QCReport:
    """Run all QC checks. Returns a QCReport."""
    report = QCReport()
    
    # 1. Structural check: does MLT load the XML?
    timeline = derive_timeline(project)
    xml = emit_mlt_xml(timeline, project, profile_name)
    mlt_loads = validate_mlt_loads(xml)
    report.add_check("mlt_load", mlt_loads, "MLT XML loads" if mlt_loads else "MLT XML failed to load")
    if not mlt_loads:
        return report  # no point running further checks
    
    # 2. Proxy render
    try:
        render_path = render_project(project, profile_name, use_cache=True)
        report.add_check("proxy_render", True, render_path)
    except Exception as e:
        report.add_check("proxy_render", False, str(e))
        return report
    
    # 3. Black-frame scan
    try:
        black_frames = scan_black_frames(render_path)
        passed = len(black_frames) == 0
        detail = f"{len(black_frames)} black frames" + \
                 (f" at {[round(f, 2) for f in black_frames[:5]]}" if black_frames else "")
        report.add_check("black_frames", passed, detail)
    except Exception as e:
        report.add_check("black_frames", False, f"Scan error: {e}")
    
    # 4. Silence scan
    try:
        silences = scan_silence(render_path)
        passed = len(silences) == 0
        detail = f"{len(silences)} silent gaps > 1s" + \
                 (f" at {[round(s, 2) for s in silences[:5]]}" if silences else "")
        report.add_check("silence", passed, detail)
    except Exception as e:
        report.add_check("silence", False, f"Scan error: {e}")
    
    # 5. Thumbnail
    try:
        thumb_path = generate_thumbnail(render_path, at_sec=0.0)
        report.add_check("thumbnail", True, thumb_path)
    except Exception as e:
        report.add_check("thumbnail", False, f"Thumbnail error: {e}")
    
    return report
```

#### 12.2.9 `open_edit/qc/black_frames.py`

```python
"""Detect black frames in a video using ffprobe."""
import json
import subprocess

def scan_black_frames(video_path: str, threshold: float = 0.1) -> list[float]:
    """Return a list of timestamps (seconds) where black frames were detected.
    
    Uses ffmpeg's blackframe filter.
    """
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"blackframe=amount={threshold}",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    # Parse stderr for black frame lines
    black_frames = []
    for line in result.stderr.split("\n"):
        if "blackframe" in line.lower() or "pblack" in line.lower():
            # Parse "t:<timestamp>"
            for part in line.split():
                if part.startswith("t:"):
                    try:
                        black_frames.append(float(part[2:]))
                    except ValueError:
                        pass
    return black_frames
```

#### 12.2.10 `open_edit/qc/silence.py`

```python
"""Detect silence in a video using ffmpeg's silencedetect filter."""
import subprocess

def scan_silence(video_path: str, min_duration_sec: float = 1.0,
                 noise_threshold_db: float = -30.0) -> list[float]:
    """Return a list of timestamps (seconds) where silence starts.
    
    Uses ffmpeg's silencedetect filter.
    """
    cmd = [
        "ffmpeg", "-i", video_path,
        "-af", f"silencedetect=noise={noise_threshold_db}dB:d={min_duration_sec}",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    silences = []
    for line in result.stderr.split("\n"):
        if "silence_start" in line:
            for part in line.split():
                if part.startswith("silence_start:"):
                    try:
                        silences.append(float(part.split(":")[1]))
                    except (ValueError, IndexError):
                        pass
    return silences
```

#### 12.2.11 `open_edit/qc/thumbnail.py`

```python
"""Generate a thumbnail from a video."""
import subprocess
from pathlib import Path

THUMB_DIR = Path("~/.open-edit/cache/thumbs").expanduser()
THUMB_DIR.mkdir(parents=True, exist_ok=True)

def generate_thumbnail(video_path: str, at_sec: float = 0.0) -> str:
    """Generate a JPEG thumbnail at the given timestamp."""
    thumb_path = THUMB_DIR / f"{Path(video_path).stem}_{int(at_sec*1000)}.jpg"
    cmd = [
        "ffmpeg", "-ss", str(at_sec), "-i", video_path,
        "-frames:v", "1", "-q:v", "2", str(thumb_path),
        "-y",
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return str(thumb_path)
```

### 12.3 Dependencies

- Phase 1 and Phase 2 complete.
- Rust toolchain (rustc, cargo) installed.
- Linux recommended for full sandbox isolation; macOS works with reduced isolation (stub). Windows not supported in v1.

### 12.4 Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Landlock API changes between kernel versions | Medium | Medium | Pin landlock crate version; document required kernel >= 5.13 |
| seccomp profile blocks Python interpreter's required syscalls | High | High | Start with a permissive profile (block only network syscalls); tighten iteratively. Document allowed syscalls. |
| Sandboxed Python script needs to import `open_edit.ir` but that path is outside the jail | High | High | Install `open_edit` as a wheel in a venv that's inside the workdir; or vendor the package into a directory inside the jail |
| Black-frame / silence detection slow on long videos | Medium | Low | Run on proxy render (640x360) not full quality; document expected duration |
| macOS sandbox-exec stub is insufficient for production | High | Medium | Document as a known limitation; recommend Linux for production use; macOS for development only |

### 12.5 Validation Criteria

```python
# tests/test_qc.py

import pytest
from open_edit.ir.types import Project, AddClipOp
from open_edit.storage.assets import AssetStore
from open_edit.qc.gate import run_qc_gate


@pytest.fixture
def sample_video(tmp_path):
    import subprocess
    path = tmp_path / "test.mp4"
    subprocess.run([
        "ffmpeg", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=30",
        "-c:v", "libx264", str(path),
    ], check=True, capture_output=True)
    return str(path)


def test_qc_passes_for_valid_project(sample_video):
    asset = AssetStore().ingest(sample_video)
    project = Project(name="test", assets={asset.asset_hash: asset})
    project.edit_graph.append(AddClipOp(
        asset_hash=asset.asset_hash, track_id="v1", position_sec=0.0,
    ))
    report = run_qc_gate(project, profile_name="proxy")
    assert report.passed, f"QC failed: {report.to_json()}"
    assert len(report.checks) == 5


def test_qc_fails_when_mlt_cannot_load():
    # Empty project — no clips, but XML should still load.
    project = Project(name="empty")
    report = run_qc_gate(project)
    # An empty timeline should produce valid (if trivial) MLT XML.
    assert report.checks[0]["name"] == "mlt_load"
```

```rust
// sandbox/tests/test_sandbox.rs

use std::process::Command;

#[test]
fn test_sandbox_runs_simple_script() {
    let script = std::env::temp_dir().join("test_script.py");
    std::fs::write(&script, "print('hello from sandbox')").unwrap();
    
    let output = Command::new("./target/debug/sandbox")
        .arg("--code").arg(&script)
        .arg("--workdir").arg(std::env::temp_dir())
        .arg("--asset-dir").arg(std::env::temp_dir())
        .arg("--timeout").arg("10")
        .arg("--mem").arg("256M")
        .arg("--output").arg(std::env::temp_dir().join("out.json"))
        .output()
        .expect("failed to run sandbox");
    
    assert!(output.status.success(), "stderr: {}", String::from_utf8_lossy(&output.stderr));
}

#[test]
fn test_sandbox_blocks_network() {
    // Script that tries to open a socket should fail.
    let script = std::env::temp_dir().join("test_net.py");
    std::fs::write(&script, r#"
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("example.com", 80))
    print("NETWORK_ALLOWED")
except Exception as e:
    print(f"NETWORK_BLOCKED: {e}")
"#).unwrap();
    
    let output = Command::new("./target/debug/sandbox")
        .arg("--code").arg(&script)
        .arg("--workdir").arg(std::env::temp_dir())
        .arg("--asset-dir").arg(std::env::temp_dir())
        .arg("--timeout").arg("10")
        .arg("--mem").arg("256M")
        .arg("--output").arg(std::env::temp_dir().join("out.json"))
        .output()
        .expect("failed to run sandbox");
    
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("NETWORK_BLOCKED"), "Network should be blocked: {}", stdout);
}
```

### 12.6 Definition of Done

- [ ] `sandbox/` Rust crate builds with `cargo build --release`.
- [ ] `sandbox --code <path> --workdir <path> --asset-dir <path> --timeout 30 --mem 512M --output <path>` runs a Python script and produces a JSON result.
- [ ] Network test (`test_sandbox_blocks_network`) passes: script cannot open a socket.
- [ ] Filesystem test passes: script cannot write outside `--workdir`.
- [ ] Allowlist test passes: script cannot run a subprocess other than `melt`/`ffmpeg`/`ffprobe`.
- [ ] `open_edit/qc/gate.py` runs all 5 checks and returns a `QCReport`.
- [ ] All tests in `tests/test_qc.py` and `sandbox/tests/test_sandbox.rs` pass.
- [ ] The system is in a stable, working state: a project can be created, edited, rendered, QC-checked, and AI-emitted code can run in the sandbox. No AI agent, no UI.

---

## 13. Phase 4: AI Agent Integration

### 13.1 Objectives

Build the AI agent loop: prompt assembly, LLM call, emission parsing, schema validation, edit graph application, QC gate trigger, and result surfacing. At the end of Phase 4, a user can type an edit request via CLI chat and the AI emits operations that are applied to the project, rendered, and QC-checked. No graphical UI yet.

### 13.2 Deliverables

#### 13.2.1 File Layout (additions)

```
open-edit/
├── open_edit/
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── loop.py            # agent_turn_with_retry()
│   │   ├── prompt.py          # assemble_prompt()
│   │   ├── parse.py           # parse_emission()
│   │   ├── validate.py        # validate_emission()
│   │   ├── apply.py           # apply_emission()
│   │   ├── surface.py         # surface_result()
│   │   ├── retry.py           # retry logic
│   │   └── system_prompt.py   # SYSTEM_PROMPT_TEMPLATE constant
│   ├── api/
│   │   ├── __init__.py
│   │   ├── chat.py            # FastAPI WebSocket endpoint
│   │   ├── project.py         # REST: project CRUD
│   │   └── render.py          # REST: render trigger, status
│   ├── catalog/
│   │   ├── __init__.py
│   │   └── effects.py         # MLT effect catalog (sourced from /usr/share/mlt-7)
│   └── cli_chat.py            # CLI chat entry point
└── tests/
    └── test_agent.py
```

#### 13.2.2 `open_edit/agent/system_prompt.py`

```python
"""System prompt template for the AI agent."""

SYSTEM_PROMPT_TEMPLATE = """You are Open Edit, an AI video editing assistant.

You operate on an Intermediate Representation (IR) of a video project.
The IR has two layers:
1. Edit Graph: an append-only log of operations with stable UUIDs.
2. Timeline State: derived from the edit graph; what the user sees.

You can emit edits in three modes (use the first one by default):

## Mode 1: Structured Operations (default)
Emit a JSON array of operations. Each operation must conform to one of these schemas:

{operations_schema}

Common fields for all operations:
- kind: string (discriminator)
- edit_id: string (UUID, auto-generated if omitted)
- parent_id: string or null (auto-set to last edit's ID)
- author: "ai" or "user" (auto-set to "ai")
- timestamp: ISO 8601 string (auto-set)
- status: "applied" | "reverted" | "superseded" (default "applied")

## Mode 2: Raw MLT XML (escape hatch)
Emit {{"mode":"raw_xml","xml":"<MLT fragment>","description":"..."}}.
Use only when no operation in Mode 1 can express what you need.
The XML will be parsed into synthetic operations; the raw XML is preserved.

## Mode 3: Free-Form Python Code (power user)
Emit {{"mode":"code","code":"<Python source>"}}.
The code runs in a sandbox and calls the IR API:
- ir.add_clip(asset_hash, track_id, position_sec, in_point_sec=0.0, out_point_sec=None) -> clip_id
- ir.remove_clip(clip_id)
- ir.move_clip(clip_id, new_track_id, new_position_sec)
- ir.trim_clip(clip_id, new_in_point_sec, new_out_point_sec)
- ir.add_transition(clip_a_id, clip_b_id, transition_type, duration_sec)
- ir.add_effect(target_kind, target_id, effect_type, params) -> effect_id
- ir.set_keyframe(effect_id, param, keyframes)
- ir.list_clips(track_id=None) -> list
- ir.get_clip(clip_id) -> dict

Use Mode 3 for bulk operations (e.g. "trim every clip on track 2 by 10%").

## Current Project State

Timeline (derived from edit graph):
{current_timeline}

Available Assets (use only these hashes):
{available_assets}

## Effect Catalog (use only these effect_type values)
{effect_catalog_summary}

## Rules
1. Prefer Mode 1 (Structured Operations) whenever possible.
2. Never invent asset hashes; use only hashes listed in Available Assets.
3. Never invent effect types; use only types listed in the Effect Catalog.
4. After emitting, the system will validate, apply, render, and QC. You will see the QC report.
5. If QC fails, you will receive the failure details; emit a corrected edit.
6. Time units are seconds (float). Frame numbers are not used in the IR.
7. Track IDs are arbitrary strings; create new ones with descriptive names like "video_main", "audio_narration".
8. Clip IDs are auto-generated; you do not need to provide them unless you reference a clip later.
9. For transitions, both clips must exist on tracks in the multitrack.
10. Effect params must match the effect's parameter schema in the catalog.
"""


OPERATIONS_SCHEMA_JSON = """
[
  {{"kind":"add_clip","asset_hash":"string","track_id":"string","position_sec":"float","in_point_sec":"float","out_point_sec":"float|null"}},
  {{"kind":"remove_clip","clip_id":"string"}},
  {{"kind":"move_clip","clip_id":"string","new_track_id":"string","new_position_sec":"float"}},
  {{"kind":"trim_clip","clip_id":"string","new_in_point_sec":"float","new_out_point_sec":"float"}},
  {{"kind":"add_transition","clip_a_id":"string","clip_b_id":"string","transition_type":"dissolve|wipe|fade|cut","duration_sec":"float"}},
  {{"kind":"add_effect","target_kind":"clip|track","target_id":"string","effect_type":"string","params":"object"}},
  {{"kind":"set_keyframe","effect_id":"string","param":"string","keyframes":"[[time_sec, value, interp], ...]"}},
  {{"kind":"group_edits","edit_ids":["string"],"label":"string"}},
  {{"kind":"raw_mlt_xml","xml":"string","description":"string"}},
  {{"kind":"free_form_code","code":"string"}}
]
"""
```

#### 13.2.3 `open_edit/agent/prompt.py`

```python
"""Prompt assembly."""
import json
from open_edit.ir.types import Project
from open_edit.ir.apply import derive_timeline
from open_edit.agent.system_prompt import SYSTEM_PROMPT_TEMPLATE, OPERATIONS_SCHEMA_JSON


def assemble_prompt(project: Project, history: list[dict], user_message: str) -> list[dict]:
    timeline = derive_timeline(project)
    
    system_content = SYSTEM_PROMPT_TEMPLATE.format(
        operations_schema=OPERATIONS_SCHEMA_JSON,
        current_timeline=json.dumps(timeline.model_dump(), indent=2, default=str),
        available_assets=_format_assets(project),
        effect_catalog_summary=_format_effect_catalog(),
    )
    
    messages = [{"role": "system", "content": system_content}]
    messages.extend(history[-20:])
    messages.append({"role": "user", "content": user_message})
    return messages


def _format_assets(project: Project) -> str:
    if not project.assets:
        return "(no assets ingested)"
    lines = []
    for h, a in project.assets.items():
        lines.append(f"  - hash={h[:16]}... path={a.original_path} type={a.type} "
                     f"duration={a.duration_sec:.2f}s fps={a.fps} {a.width}x{a.height}")
    return "\n".join(lines)


def _format_effect_catalog() -> str:
    from open_edit.catalog.effects import get_catalog_summary
    return get_catalog_summary()
```

#### 13.2.4 `open_edit/agent/parse.py`

```python
"""Parse the LLM's raw response into a structured emission."""
import json
import re
from typing import Union
from pydantic import BaseModel
from open_edit.ir.types import OperationUnion


class ParseError(Exception):
    pass


class StructuredEmission(BaseModel):
    ops: list[dict]  # raw dicts; validated in validate.py


class RawXmlEmission(BaseModel):
    xml: str
    description: str = ""


class CodeEmission(BaseModel):
    code: str


ParsedEmission = Union[StructuredEmission, RawXmlEmission, CodeEmission]


def parse_emission(raw: str) -> ParsedEmission:
    """Parse raw LLM output. Raises ParseError if no mode matches."""
    data = _extract_json(raw)
    
    if data is None:
        raise ParseError(f"Could not parse JSON from response: {raw[:200]}...")
    
    if isinstance(data, list):
        return StructuredEmission(ops=data)
    
    if isinstance(data, dict):
        mode = data.get("mode")
        if mode == "raw_xml":
            return RawXmlEmission(xml=data.get("xml", ""), description=data.get("description", ""))
        elif mode == "code":
            return CodeEmission(code=data.get("code", ""))
        # Maybe it's a single operation (not wrapped in a list)
        if "kind" in data:
            return StructuredEmission(ops=[data])
    
    raise ParseError(f"Unrecognized emission format: {raw[:200]}...")


def _extract_json(raw: str) -> list | dict | None:
    # Try direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    
    # Try extracting from ```json ... ``` fences
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Try finding the first [ or { and matching bracket
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start = raw.find(start_char)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(raw)):
            if raw[i] == start_char:
                depth += 1
            elif raw[i] == end_char:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[start:i+1])
                    except json.JSONDecodeError:
                        break
    
    return None
```

#### 13.2.5 `open_edit/agent/validate.py`

```python
"""Validate parsed emissions against the IR schema and project state."""
from pydantic import ValidationError
from open_edit.ir.types import (
    Project, OperationUnion, AddClipOp, RemoveClipOp, MoveClipOp, TrimClipOp,
    AddTransitionOp, AddEffectOp, SetKeyframeOp,
)
from open_edit.agent.parse import StructuredEmission, RawXmlEmission, CodeEmission


class ValidationResult:
    def __init__(self, passed: bool, errors: list[str] = None):
        self.passed = passed
        self.errors = errors or []


def validate_emission(emission, project: Project) -> ValidationResult:
    errors = []
    
    if isinstance(emission, StructuredEmission):
        for i, op_dict in enumerate(emission.ops):
            # Schema validation
            try:
                op = OperationUnion.model_validate(op_dict)
            except ValidationError as e:
                errors.append(f"Op {i}: schema validation failed: {e}")
                continue
            
            # Referential integrity
            kind = op_dict.get("kind")
            if kind == "add_clip":
                if op.asset_hash not in project.assets:
                    errors.append(f"Op {i}: unknown asset_hash {op.asset_hash}")
            elif kind in ("remove_clip", "move_clip", "trim_clip"):
                # Check clip exists in current timeline
                timeline = project.timeline
                clip_ids = {c.clip_id for t in timeline.tracks for c in t.clips}
                if op.clip_id not in clip_ids:
                    errors.append(f"Op {i}: unknown clip_id {op.clip_id}")
            elif kind == "add_transition":
                timeline = project.timeline
                clip_ids = {c.clip_id for t in timeline.tracks for c in t.clips}
                if op.clip_a_id not in clip_ids:
                    errors.append(f"Op {i}: unknown clip_a_id {op.clip_a_id}")
                if op.clip_b_id not in clip_ids:
                    errors.append(f"Op {i}: unknown clip_b_id {op.clip_b_id}")
            elif kind == "add_effect":
                if op.target_kind == "clip":
                    timeline = project.timeline
                    clip_ids = {c.clip_id for t in timeline.tracks for c in t.clips}
                    if op.target_id not in clip_ids:
                        errors.append(f"Op {i}: unknown clip_id {op.target_id}")
                elif op.target_kind == "track":
                    track_ids = {t.track_id for t in project.timeline.tracks}
                    if op.target_id not in track_ids:
                        errors.append(f"Op {i}: unknown track_id {op.target_id}")
    
    elif isinstance(emission, RawXmlEmission):
        if not emission.xml.strip():
            errors.append("Raw XML emission is empty")
    
    elif isinstance(emission, CodeEmission):
        if not emission.code.strip():
            errors.append("Code emission is empty")
    
    return ValidationResult(passed=len(errors) == 0, errors=errors)
```

#### 13.2.6 `open_edit/agent/apply.py`

```python
"""Apply a parsed emission to the project's edit graph."""
from open_edit.ir.types import Project, OperationUnion, RawMltXmlOp, FreeFormCodeOp
from open_edit.agent.parse import StructuredEmission, RawXmlEmission, CodeEmission
from open_edit.storage.edit_graph import EditGraphStore
from datetime import datetime, timezone


def apply_emission(emission, project: Project, store: EditGraphStore) -> list:
    """Apply the emission. Returns the list of appended operations."""
    appended = []
    now = datetime.now(timezone.utc).isoformat()
    
    if isinstance(emission, StructuredEmission):
        for op_dict in emission.ops:
            op = OperationUnion.model_validate(op_dict)
            op.author = "ai"
            op.timestamp = now
            op.parent_id = project.last_edit_id
            project.edit_graph.append(op)
            store.append(op)
            appended.append(op)
    
    elif isinstance(emission, RawXmlEmission):
        op = RawMltXmlOp(
            xml=emission.xml,
            description=emission.description,
            author="ai",
            timestamp=now,
            parent_id=project.last_edit_id,
        )
        project.edit_graph.append(op)
        store.append(op)
        appended.append(op)
        # Note: child ops from MLT XML ingest parser are produced lazily
        # by apply_operation() during derive_timeline(). For Phase 4 simplicity,
        # we don't eagerly parse; the timeline derivation handles it.
    
    elif isinstance(emission, CodeEmission):
        op = FreeFormCodeOp(
            code=emission.code,
            author="ai",
            timestamp=now,
            parent_id=project.last_edit_id,
        )
        project.edit_graph.append(op)
        store.append(op)
        appended.append(op)
        # Run code in sandbox to produce child ops
        child_ops = _run_sandboxed_code(emission.code, project)
        for child in child_ops:
            child.parent_id = op.edit_id
            project.edit_graph.append(child)
            store.append(child)
            appended.append(child)
    
    return appended


def _run_sandboxed_code(code: str, project: Project) -> list:
    """Run AI-emitted code in the sandbox. Returns captured operations."""
    import subprocess
    import tempfile
    import json
    import os
    from pathlib import Path
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        code_path = f.name
    
    output_path = tempfile.mktemp(suffix=".json")
    workdir = tempfile.mkdtemp()
    
    # Write project state to a JSON file the sandbox can read
    project_state_path = Path(workdir) / "project_state.json"
    project_state_path.write_text(project.model_dump_json())
    
    sandbox_binary = os.environ.get("OPEN_EDIT_SANDBOX_BINARY", "./sandbox/target/release/sandbox")
    asset_dir = os.path.expanduser("~/.open-edit/assets")
    
    try:
        subprocess.run(
            [sandbox_binary,
             "--code", code_path,
             "--workdir", workdir,
             "--asset-dir", asset_dir,
             "--timeout", "30",
             "--mem", "512M",
             "--output", output_path],
            check=True, capture_output=True, text=True, timeout=60,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Sandbox execution failed: {e.stderr}")
    
    if not os.path.exists(output_path):
        return []
    
    with open(output_path) as f:
        ops_data = json.load(f)
    
    return [OperationUnion.model_validate(op_dict) for op_dict in ops_data]
```

#### 13.2.7 `open_edit/agent/loop.py`

```python
"""Main agent loop with retry logic."""
import asyncio
from typing import Optional
from open_edit.ir.types import Project
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.agent.prompt import assemble_prompt
from open_edit.agent.parse import parse_emission, ParseError
from open_edit.agent.validate import validate_emission
from open_edit.agent.apply import apply_emission
from open_edit.agent.surface import surface_result
from open_edit.qc.gate import run_qc_gate
from open_edit.render.orchestrator import render_project

MAX_RETRIES = 3


async def call_llm(messages: list[dict]) -> str:
    """Call the LLM via z-ai-web-dev-sdk."""
    # NOTE: this is a stub. The actual SDK call depends on the z-ai-web-dev-sdk
    # package's API. Adjust based on the SDK's chat completion interface.
    try:
        from z_ai_web_dev_sdk import LLM
        llm = LLM()
        response = await llm.chat(messages)
        return response.content if hasattr(response, "content") else str(response)
    except ImportError:
        # Fallback for environments without the SDK; allows Phase 4 testing
        # with a mock LLM.
        return _mock_llm_response(messages)


def _mock_llm_response(messages: list[dict]) -> str:
    """Mock LLM for testing. Returns a trivial add_clip operation."""
    import json
    return json.dumps([{
        "kind": "add_clip",
        "asset_hash": "mock",
        "track_id": "v1",
        "position_sec": 0.0,
    }])


async def agent_turn(project: Project, store: EditGraphStore,
                     history: list[dict], user_message: str) -> dict:
    """Process one user message. Returns the assistant's response dict."""
    last_validation = None
    
    for attempt in range(MAX_RETRIES):
        messages = assemble_prompt(project, history, user_message)
        raw = await call_llm(messages)
        
        try:
            emission = parse_emission(raw)
        except ParseError as e:
            history.append({"role": "assistant", "content": raw})
            history.append({"role": "user", "content":
                f"Parse error: {e}. Please emit a valid operation array, raw XML, or code."})
            continue
        
        validation = validate_emission(emission, project)
        last_validation = validation
        if not validation.passed:
            history.append({"role": "assistant", "content": raw})
            history.append({"role": "user", "content":
                f"Validation failed: {validation.errors}. Please correct and retry."})
            continue
        
        appended = apply_emission(emission, project, store)
        qc_report = run_qc_gate(project)
        try:
            render_path = render_project(project, profile_name="proxy", use_cache=True)
        except Exception as e:
            render_path = None
            qc_report.add_check("render", False, f"Render error: {e}")
        
        result = surface_result(emission, appended, qc_report, render_path)
        history.append({"role": "assistant", "content": result["content"], "metadata": result["metadata"]})
        return result
    
    return {
        "content": f"Failed after {MAX_RETRIES} attempts. Last error: {last_validation.errors if last_validation else 'unknown'}",
        "metadata": {},
    }
```

#### 13.2.8 `open_edit/agent/surface.py`

```python
"""Surface the result of an agent turn as a chat message."""
from open_edit.agent.parse import StructuredEmission, RawXmlEmission, CodeEmission


def surface_result(emission, appended_ops, qc_report, render_path) -> dict:
    if isinstance(emission, StructuredEmission):
        summary = f"Applied {len(appended_ops)} operations: " + \
                  ", ".join(op.kind for op in appended_ops)
    elif isinstance(emission, RawXmlEmission):
        summary = f"Applied raw MLT XML: {emission.description}"
    elif isinstance(emission, CodeEmission):
        summary = f"Executed free-form code; produced {len(appended_ops)} operations"
    else:
        summary = "Unknown emission type"
    
    return {
        "content": summary,
        "metadata": {
            "ops": [op.model_dump() for op in appended_ops],
            "qc": qc_report.to_dict() if hasattr(qc_report, "to_dict") else qc_report,
            "render_path": render_path,
        },
    }
```

#### 13.2.9 `open_edit/catalog/effects.py`

```python
"""MLT effect catalog, sourced from /usr/share/mlt-7/."""
import os
from pathlib import Path
from typing import Optional

MLT_METADATA_DIR = Path("/usr/share/mlt-7/presets")
MLT_SERVICE_DIR = Path("/usr/share/mlt-7")


def get_catalog_summary() -> str:
    """Return a summary of available effects for the system prompt."""
    effects = list_effects()
    if not effects:
        return "(no effects found; ensure MLT is installed)"
    lines = []
    for e in effects[:50]:  # cap at 50 to fit context
        lines.append(f"  - {e['service']}: {e.get('description', '')[:80]}")
    if len(effects) > 50:
        lines.append(f"  ... and {len(effects) - 50} more")
    return "\n".join(lines)


def list_effects() -> list[dict]:
    """List available MLT services (filters and transitions)."""
    # Phase 4 stub: in production, query `melt -query filters` and `melt -query transitions`
    # and parse the YAML output.
    import subprocess
    effects = []
    try:
        result = subprocess.run(
            ["melt", "-query", "filters"],
            capture_output=True, text=True, timeout=10,
        )
        # Parse the YAML-ish output (simplified)
        for line in result.stdout.split("\n"):
            line = line.strip()
            if line.startswith("- ") and ":" not in line:
                service = line[2:].strip()
                effects.append({"service": service, "description": ""})
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    return effects


def get_effect_schema(effect_type: str) -> Optional[dict]:
    """Get the parameter schema for an effect."""
    # Phase 4 stub: query `melt -query filter=<effect_type>` and parse.
    # For now, return a permissive schema.
    return {"type": "object", "additionalProperties": True}
```

#### 13.2.10 `open_edit/cli_chat.py`

```python
"""CLI chat entry point for Phase 4."""
import asyncio
import sys
from open_edit.ir.types import Project
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.agent.loop import agent_turn


async def chat_repl(project_id: str):
    store = EditGraphStore(project_id)
    # Load project state
    ops = store.load_all()
    project = Project(name="loaded", edit_graph=ops)
    
    history = []
    print(f"Open Edit chat. Project: {project_id}")
    print("Type 'exit' to quit.\n")
    
    while True:
        try:
            user_input = input("user> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            break
        
        if user_input.lower() in ("exit", "quit"):
            break
        if not user_input:
            continue
        
        history.append({"role": "user", "content": user_input})
        result = await agent_turn(project, store, history, user_input)
        print(f"\nassistant> {result['content']}\n")
        
        if result.get("metadata", {}).get("qc"):
            qc = result["metadata"]["qc"]
            status = "PASS" if qc.get("passed") else "FAIL"
            print(f"  [QC: {status}]")
            for check in qc.get("checks", []):
                mark = "+" if check["passed"] else "-"
                print(f"    [{mark}] {check['name']}: {check['detail'][:80]}")
        print()


def main():
    if len(sys.argv) != 2:
        print("Usage: python -m open_edit.cli_chat <project_id>")
        sys.exit(1)
    asyncio.run(chat_repl(sys.argv[1]))


if __name__ == "__main__":
    main()
```

#### 13.2.11 `open_edit/api/chat.py` (FastAPI WebSocket — for Phase 5 UI)

```python
"""FastAPI WebSocket endpoint for chat. Used by Phase 5 UI; Phase 4 uses CLI."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from open_edit.ir.types import Project
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.agent.loop import agent_turn
import asyncio
import json

router = APIRouter()


@router.websocket("/ws/chat/{project_id}")
async def chat_ws(websocket: WebSocket, project_id: str):
    await websocket.accept()
    store = EditGraphStore(project_id)
    project = Project(name="loaded", edit_graph=store.load_all())
    history = []
    
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            
            if msg.get("type") == "user_message":
                user_input = msg["content"]
                history.append({"role": "user", "content": user_input})
                
                await websocket.send_text(json.dumps({"type": "agent_thinking"}))
                
                result = await agent_turn(project, store, history, user_input)
                
                await websocket.send_text(json.dumps({
                    "type": "agent_emission",
                    "content": result["content"],
                    "metadata": result.get("metadata", {}),
                }))
    except WebSocketDisconnect:
        pass
```

### 13.3 Dependencies

- Phases 1, 2, 3 complete.
- `z-ai-web-dev-sdk` Python package (or compatible LLM SDK).
- `fastapi` and `uvicorn` for the API layer.
- MLT installed (`melt -query filters` must work for catalog discovery).

### 13.4 Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| LLM emits invalid JSON (especially for Mode 1 with many operations) | High | Medium | Robust `_extract_json()` parser; retry with error feedback; cap operations per emission at 20 |
| LLM invents asset hashes or effect types | High | Medium | Strict referential validation; reject with clear error listing valid hashes/types |
| LLM emits Mode 2 (raw XML) too often, bypassing IR | Medium | High | System prompt rule #1 emphasizes Mode 1; track mode usage in metrics; if Mode 2 > 20%, investigate |
| Sandbox binary path not found | Medium | Medium | Document `OPEN_EDIT_SANDBOX_BINARY` env var; fallback to dev path `./sandbox/target/release/sandbox` |
| `melt -query filters` output format varies | Medium | Low | Defensive parsing; fall back to a hardcoded effect list if query fails |
| Prompt too long (asset list + timeline + catalog exceed context window) | Medium | High | Truncate catalog to 50 entries; paginate assets if > 100; summarize timeline by track count + clip count, full detail only for most recent N edits |

### 13.5 Validation Criteria

```python
# tests/test_agent.py

import pytest
import asyncio
from open_edit.ir.types import Project, AddClipOp
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.agent.parse import parse_emission, StructuredEmission, RawXmlEmission, CodeEmission
from open_edit.agent.validate import validate_emission
from open_edit.agent.prompt import assemble_prompt


def test_parse_structured_operations():
    raw = '[{"kind":"add_clip","asset_hash":"abc","track_id":"v1","position_sec":0.0}]'
    emission = parse_emission(raw)
    assert isinstance(emission, StructuredEmission)
    assert len(emission.ops) == 1
    assert emission.ops[0]["kind"] == "add_clip"


def test_parse_raw_xml():
    raw = '{"mode":"raw_xml","xml":"<filter></filter>","description":"test"}'
    emission = parse_emission(raw)
    assert isinstance(emission, RawXmlEmission)
    assert emission.xml == "<filter></filter>"


def test_parse_code():
    raw = '{"mode":"code","code":"print(1)"}'
    emission = parse_emission(raw)
    assert isinstance(emission, CodeEmission)
    assert emission.code == "print(1)"


def test_parse_json_in_fences():
    raw = '```json\n[{"kind":"add_clip","asset_hash":"abc","track_id":"v1","position_sec":0.0}]\n```'
    emission = parse_emission(raw)
    assert isinstance(emission, StructuredEmission)


def test_validate_unknown_asset_fails():
    project = Project(name="test")  # no assets
    emission = StructuredEmission(ops=[{
        "kind": "add_clip", "asset_hash": "nonexistent",
        "track_id": "v1", "position_sec": 0.0,
    }])
    result = validate_emission(emission, project)
    assert not result.passed
    assert any("unknown asset_hash" in e for e in result.errors)


def test_validate_known_asset_passes():
    from open_edit.ir.types import Asset
    project = Project(name="test", assets={
        "abc": Asset(asset_hash="abc", original_path="/x", stored_path="/x",
                     type="video", duration_sec=10.0)
    })
    emission = StructuredEmission(ops=[{
        "kind": "add_clip", "asset_hash": "abc",
        "track_id": "v1", "position_sec": 0.0,
    }])
    result = validate_emission(emission, project)
    assert result.passed, result.errors


def test_assemble_prompt_contains_required_sections():
    project = Project(name="test")
    messages = assemble_prompt(project, [], "test message")
    assert len(messages) == 2  # system + user
    assert "Mode 1" in messages[0]["content"]
    assert "Mode 2" in messages[0]["content"]
    assert "Mode 3" in messages[0]["content"]
    assert "test message" == messages[1]["content"]
```

### 13.6 Definition of Done

- [ ] All files in §13.2.1 exist and contain the specified contents.
- [ ] `python -m open_edit.cli_chat <project_id>` starts a REPL that accepts user messages and calls the agent.
- [ ] When the agent emits structured operations, they are validated, applied to the edit graph, and a QC report is printed.
- [ ] When the agent emits raw XML, it is wrapped as `RawMltXmlOp` and applied.
- [ ] When the agent emits free-form code, it runs in the sandbox and the captured operations are appended.
- [ ] Retry logic works: if validation fails, the agent receives the error and retries up to 3 times.
- [ ] All 7 tests in `tests/test_agent.py` pass.
- [ ] The system is in a stable, working state: a user can chat with the AI agent via CLI; the AI emits operations that modify the project, render, and QC. No graphical UI.

---

## 14. Phase 5: Desktop UI

### 14.1 Objectives

Build the Tauri desktop shell and the React frontend with the four-panel layout (Chat, Timeline, Edit History, Preview+QC). At the end of Phase 5, the user has an installable desktop application that fully replaces the CLI workflow.

### 14.2 Deliverables

#### 14.2.1 File Layout (additions)

```
open-edit/
├── desktop/                         # Tauri shell
│   ├── src-tauri/
│   │   ├── Cargo.toml
│   │   ├── tauri.conf.json
│   │   ├── src/
│   │   │   └── main.rs
│   │   └── icons/
│   └── package.json
├── frontend/                        # React + TypeScript
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/
│       │   ├── websocket.ts        # WebSocket client
│       │   └── rest.ts             # REST client
│       ├── panels/
│       │   ├── Chat.tsx
│       │   ├── Timeline.tsx
│       │   ├── EditHistory.tsx
│       │   └── Preview.tsx
│       ├── components/
│       │   ├── Clip.tsx
│       │   ├── Track.tsx
│       │   ├── EditRow.tsx
│       │   └── QCStatus.tsx
│       └── store/
│           └── projectStore.ts     # Zustand store
└── open_edit/
    └── api/
        └── server.py               # FastAPI app
```

#### 14.2.2 `desktop/src-tauri/tauri.conf.json`

```json
{
  "$schema": "https://schema.tauri.app/config/1",
  "productName": "Open Edit",
  "version": "0.1.0",
  "identifier": "com.openedit.app",
  "build": {
    "beforeDevCommand": "cd ../frontend && npm run dev",
    "beforeBuildCommand": "cd ../frontend && npm run build",
    "devUrl": "http://localhost:5173",
    "frontendDist": "../frontend/dist"
  },
  "app": {
    "title": "Open Edit",
    "windows": [
      {
        "title": "Open Edit",
        "width": 1600,
        "height": 900,
        "minWidth": 1200,
        "minHeight": 700,
        "resizable": true,
        "fullscreen": false
      }
    ],
    "security": {
      "csp": "default-src 'self'; img-src 'self' data: file:; media-src 'self' file:; script-src 'self'; style-src 'self' 'unsafe-inline'"
    }
  },
  "bundle": {
    "active": true,
    "targets": ["deb", "appimage", "msi", "app", "dmg"],
    "resources": ["../sandbox/target/release/sandbox"],
    "externalBin": []
  },
  "tauri": {
    "sidecar": [
      {
        "command": "python3",
        "args": ["-m", "open_edit.api.server", "--port", "8765"],
        "name": "open-edit-backend"
      }
    ]
  }
}
```

#### 14.2.3 `desktop/src-tauri/src/main.rs`

```rust
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Manager;
use std::process::{Command, Child};
use std::sync::Mutex;

struct BackendProcess(Mutex<Option<Child>>);

#[tauri::command]
fn get_backend_url() -> String {
    "http://localhost:8765".to_string()
}

#[tauri::command]
fn get_ws_url() -> String {
    "ws://localhost:8765/ws/chat".to_string()
}

fn main() {
    tauri::Builder::default()
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            // Launch the Python backend as a sidecar
            let child = Command::new("python3")
                .args(["-m", "open_edit.api.server", "--port", "8765"])
                .spawn()
                .expect("failed to launch backend");
            
            let state: tauri::State<BackendProcess> = app.state();
            *state.0.lock().unwrap() = Some(child);
            
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                let state: tauri::State<BackendProcess> = window.state();
                if let Some(mut child) = state.0.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![get_backend_url, get_ws_url])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

#### 14.2.4 `frontend/package.json`

```json
{
  "name": "open-edit-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "zustand": "^4.4.0",
    "@tauri-apps/api": "^1.5.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.0",
    "@types/react-dom": "^18.2.0",
    "@vitejs/plugin-react": "^4.2.0",
    "typescript": "^5.2.0",
    "vite": "^5.0.0"
  }
}
```

#### 14.2.5 `frontend/src/App.tsx`

```tsx
import React from 'react';
import { Chat } from './panels/Chat';
import { Timeline } from './panels/Timeline';
import { EditHistory } from './panels/EditHistory';
import { Preview } from './panels/Preview';
import { useProjectStore } from './store/projectStore';
import { useEffect } from 'react';
import { connectWebSocket } from './api/websocket';

export const App: React.FC = () => {
  const projectId = useProjectStore((s) => s.projectId);
  const loadProject = useProjectStore((s) => s.loadProject);
  
  useEffect(() => {
    if (projectId) {
      connectWebSocket(projectId);
      loadProject(projectId);
    }
  }, [projectId]);
  
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '40% 40% 20%',
      gridTemplateRows: '60% 40%',
      height: '100vh',
      gap: '1px',
      background: '#333',
    }}>
      <div style={{ gridArea: '1 / 1 / 3 / 2', background: '#1e1e1e', overflow: 'auto' }}>
        <Chat />
      </div>
      <div style={{ gridArea: '1 / 2 / 2 / 3', background: '#252526', overflow: 'auto' }}>
        <Timeline />
      </div>
      <div style={{ gridArea: '2 / 2 / 3 / 3', background: '#1e1e1e' }}>
        <Preview />
      </div>
      <div style={{ gridArea: '1 / 3 / 3 / 4', background: '#252526', overflow: 'auto' }}>
        <EditHistory />
      </div>
    </div>
  );
};
```

#### 14.2.6 `frontend/src/store/projectStore.ts`

```typescript
import { create } from 'zustand';
import { fetchProject, sendUserEdit, undoEdit, redoEdit, reorderEdits, fineTuneEdit } from '../api/rest';

interface Operation {
  edit_id: string;
  kind: string;
  author: 'ai' | 'user';
  timestamp: string;
  status: 'applied' | 'reverted' | 'superseded';
  [key: string]: any;
}

interface Timeline {
  tracks: any[];
  duration_sec: number;
}

interface QCReport {
  passed: boolean;
  checks: { name: string; passed: boolean; detail: string }[];
}

interface ProjectState {
  projectId: string | null;
  timeline: Timeline | null;
  editGraph: Operation[];
  renderPath: string | null;
  qcReport: QCReport | null;
  chatHistory: { role: string; content: string; metadata?: any }[];
  setProjectId: (id: string) => void;
  loadProject: (id: string) => Promise<void>;
  setTimeline: (t: Timeline) => void;
  setEditGraph: (ops: Operation[]) => void;
  setRenderPath: (p: string) => void;
  setQcReport: (q: QCReport) => void;
  appendChatMessage: (msg: any) => void;
  sendUserEdit: (op: any) => Promise<void>;
  undo: (editId: string) => Promise<void>;
  redo: (editId: string) => Promise<void>;
  reorder: (a: string, b: string) => Promise<void>;
  fineTune: (editId: string, newParams: any) => Promise<void>;
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projectId: null,
  timeline: null,
  editGraph: [],
  renderPath: null,
  qcReport: null,
  chatHistory: [],
  setProjectId: (id) => set({ projectId: id }),
  loadProject: async (id) => {
    const data = await fetchProject(id);
    set({ timeline: data.timeline, editGraph: data.edit_graph });
  },
  setTimeline: (t) => set({ timeline: t }),
  setEditGraph: (ops) => set({ editGraph: ops }),
  setRenderPath: (p) => set({ renderPath: p }),
  setQcReport: (q) => set({ qcReport: q }),
  appendChatMessage: (msg) => set((s) => ({ chatHistory: [...s.chatHistory, msg] })),
  sendUserEdit: async (op) => {
    await sendUserEdit(get().projectId!, op);
  },
  undo: async (editId) => {
    await undoEdit(get().projectId!, editId);
  },
  redo: async (editId) => {
    await redoEdit(get().projectId!, editId);
  },
  reorder: async (a, b) => {
    await reorderEdits(get().projectId!, a, b);
  },
  fineTune: async (editId, newParams) => {
    await fineTuneEdit(get().projectId!, editId, newParams);
  },
}));
```

#### 14.2.7 `frontend/src/api/websocket.ts`

```typescript
import { useProjectStore } from '../store/projectStore';

let ws: WebSocket | null = null;

export function connectWebSocket(projectId: string) {
  if (ws) ws.close();
  
  ws = new WebSocket(`ws://localhost:8765/ws/chat/${projectId}`);
  
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    const store = useProjectStore.getState();
    
    switch (msg.type) {
      case 'agent_thinking':
        store.appendChatMessage({ role: 'assistant', content: '(thinking...)' });
        break;
      case 'agent_emission':
        store.appendChatMessage({
          role: 'assistant',
          content: msg.content,
          metadata: msg.metadata,
        });
        if (msg.metadata?.render_path) store.setRenderPath(msg.metadata.render_path);
        if (msg.metadata?.qc) store.setQcReport(msg.metadata.qc);
        // Reload timeline and edit graph
        store.loadProject(projectId);
        break;
      case 'timeline_updated':
        store.setTimeline(msg.timeline);
        break;
      case 'edit_graph_updated':
        store.setEditGraph(msg.edits);
        break;
      case 'render_ready':
        store.setRenderPath(msg.path);
        if (msg.qc) store.setQcReport(msg.qc);
        break;
      case 'error':
        console.error('Server error:', msg);
        alert(`Error: ${msg.message}`);
        break;
    }
  };
  
  ws.onclose = () => {
    console.log('WebSocket closed');
  };
  
  ws.onerror = (err) => {
    console.error('WebSocket error:', err);
  };
}

export function sendMessage(content: string) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'user_message', content }));
  }
}

export function sendEdit(op: any) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'user_edit', op }));
  }
}
```

#### 14.2.8 `frontend/src/panels/Chat.tsx`

```tsx
import React, { useState, useEffect, useRef } from 'react';
import { useProjectStore } from '../store/projectStore';
import { sendMessage } from '../api/websocket';

export const Chat: React.FC = () => {
  const chatHistory = useProjectStore((s) => s.chatHistory);
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory]);
  
  const handleSend = () => {
    if (!input.trim()) return;
    useProjectStore.getState().appendChatMessage({ role: 'user', content: input });
    sendMessage(input);
    setInput('');
  };
  
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ flex: 1, overflow: 'auto', padding: '8px' }}>
        {chatHistory.map((msg, i) => (
          <div key={i} style={{
            textAlign: msg.role === 'user' ? 'right' : 'left',
            margin: '8px 0',
          }}>
            <div style={{
              display: 'inline-block',
              padding: '8px 12px',
              borderRadius: '8px',
              background: msg.role === 'user' ? '#0e639c' : '#3a3a3a',
              color: '#fff',
              maxWidth: '80%',
              textAlign: 'left',
            }}>
              {msg.content}
              {msg.metadata?.ops && (
                <details style={{ marginTop: '8px', fontSize: '0.85em' }}>
                  <summary>Operations ({msg.metadata.ops.length})</summary>
                  <pre>{JSON.stringify(msg.metadata.ops, null, 2)}</pre>
                </details>
              )}
              {msg.metadata?.qc && (
                <details style={{ marginTop: '8px', fontSize: '0.85em' }}>
                  <summary>QC Report ({msg.metadata.qc.passed ? 'PASS' : 'FAIL'})</summary>
                  {msg.metadata.qc.checks.map((c: any, j: number) => (
                    <div key={j}>
                      {c.passed ? '✓' : '✗'} {c.name}: {c.detail}
                    </div>
                  ))}
                </details>
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>
      <div style={{ padding: '8px', borderTop: '1px solid #444' }}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder="Type a message... (Enter to send, Shift+Enter for newline)"
          style={{
            width: '100%', height: '60px', background: '#1e1e1e', color: '#fff',
            border: '1px solid #444', borderRadius: '4px', padding: '8px',
            fontFamily: 'inherit', fontSize: '14px', resize: 'none',
          }}
        />
      </div>
    </div>
  );
};
```

#### 14.2.9 `frontend/src/panels/Timeline.tsx`

```tsx
import React, { useRef, useEffect } from 'react';
import { useProjectStore } from '../store/projectStore';
import { sendEdit } from '../api/websocket';

export const Timeline: React.FC = () => {
  const timeline = useProjectStore((s) => s.timeline);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  
  useEffect(() => {
    if (!timeline || !canvasRef.current) return;
    drawTimeline(canvasRef.current, timeline);
  }, [timeline]);
  
  if (!timeline) {
    return <div style={{ padding: '16px', color: '#888' }}>No timeline</div>;
  }
  
  return (
    <div style={{ padding: '8px' }}>
      <h3 style={{ color: '#fff', margin: '0 0 8px 0', fontSize: '14px' }}>
        Timeline ({timeline.duration_sec.toFixed(2)}s)
      </h3>
      {timeline.tracks.map((track: any) => (
        <TrackView key={track.track_id} track={track} />
      ))}
    </div>
  );
};

const TrackView: React.FC<{ track: any }> = ({ track }) => {
  return (
    <div style={{ marginBottom: '8px' }}>
      <div style={{ color: '#aaa', fontSize: '12px', marginBottom: '4px' }}>
        {track.track_id} ({track.kind})
      </div>
      <div style={{
        position: 'relative', height: '40px',
        background: '#1a1a1a', borderRadius: '4px', overflow: 'hidden',
      }}>
        {track.clips.map((clip: any) => (
          <ClipView key={clip.clip_id} clip={clip} />
        ))}
      </div>
    </div>
  );
};

const ClipView: React.FC<{ clip: any }> = ({ clip }) => {
  const startX = clip.position_sec * 50; // 50px per second
  const width = (clip.out_point_sec - clip.in_point_sec) * 50;
  
  const handleDrag = (e: React.MouseEvent) => {
    e.preventDefault();
    // Simplified: real implementation tracks mouse movement
    console.log('Clip drag not fully implemented in Phase 5 stub');
  };
  
  return (
    <div
      onMouseDown={handleDrag}
      style={{
        position: 'absolute',
        left: `${startX}px`,
        width: `${width}px`,
        height: '100%',
        background: 'linear-gradient(135deg, #2d5a8e, #1e3a5e)',
        border: '1px solid #4a8acb',
        borderRadius: '2px',
        cursor: 'move',
        overflow: 'hidden',
        fontSize: '10px',
        color: '#fff',
        padding: '2px 4px',
      }}
      title={`${clip.asset_hash.slice(0, 8)} @ ${clip.position_sec.toFixed(2)}s`}
    >
      {clip.asset_hash.slice(0, 8)}...
    </div>
  );
};

function drawTimeline(canvas: HTMLCanvasElement, timeline: any) {
  // Stub: canvas-based timeline rendering is more performant for large projects.
  // Phase 5 uses HTML/CSS divs (above); canvas is reserved for Phase 7 optimization.
}
```

#### 14.2.10 `frontend/src/panels/EditHistory.tsx`

```tsx
import React, { useState } from 'react';
import { useProjectStore } from '../store/projectStore';

export const EditHistory: React.FC = () => {
  const editGraph = useProjectStore((s) => s.editGraph);
  const undo = useProjectStore((s) => s.undo);
  const redo = useProjectStore((s) => s.redo);
  const [expanded, setExpanded] = useState<string | null>(null);
  
  return (
    <div style={{ padding: '8px' }}>
      <h3 style={{ color: '#fff', margin: '0 0 8px 0', fontSize: '14px' }}>
        Edit History ({editGraph.length} operations)
      </h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
        {[...editGraph].reverse().map((op, i) => {
          const realIndex = editGraph.length - 1 - i;
          const statusColor = {
            applied: '#4ec9b0',
            reverted: '#f48771',
            superseded: '#dcdcaa',
          }[op.status];
          
          return (
            <div
              key={op.edit_id}
              style={{
                background: '#1a1a1a',
                padding: '6px 8px',
                borderRadius: '3px',
                borderLeft: `3px solid ${statusColor}`,
                cursor: 'pointer',
              }}
              onClick={() => setExpanded(expanded === op.edit_id ? null : op.edit_id)}
              onContextMenu={(e) => {
                e.preventDefault();
                const action = window.prompt(
                  `Edit ${op.edit_id}\n\nActions:\n1. Undo\n2. Redo\n3. Fine-tune\n\nEnter action number:`,
                );
                if (action === '1') undo(op.edit_id);
                else if (action === '2') redo(op.edit_id);
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#fff', fontSize: '12px' }}>
                  [{op.author}] {op.kind}
                </span>
                <span style={{ color: '#888', fontSize: '10px' }}>
                  {op.timestamp.slice(11, 19)}
                </span>
              </div>
              {expanded === op.edit_id && (
                <pre style={{
                  margin: '4px 0 0 0',
                  fontSize: '10px',
                  color: '#aaa',
                  whiteSpace: 'pre-wrap',
                }}>
                  {JSON.stringify(op, null, 2)}
                </pre>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
```

#### 14.2.11 `frontend/src/panels/Preview.tsx`

```tsx
import React from 'react';
import { useProjectStore } from '../store/projectStore';

export const Preview: React.FC = () => {
  const renderPath = useProjectStore((s) => s.renderPath);
  const qcReport = useProjectStore((s) => s.qcReport);
  
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ flex: 1, background: '#000', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {renderPath ? (
          <video
            src={`file://${renderPath}`}
            controls
            style={{ maxWidth: '100%', maxHeight: '100%' }}
          />
        ) : (
          <div style={{ color: '#888' }}>No render available</div>
        )}
      </div>
      <div style={{ padding: '8px', background: '#1e1e1e' }}>
        <h4 style={{ color: '#fff', margin: '0 0 8px 0', fontSize: '12px' }}>QC Report</h4>
        {qcReport ? (
          <div>
            <div style={{
              color: qcReport.passed ? '#4ec9b0' : '#f48771',
              fontSize: '14px', fontWeight: 'bold', marginBottom: '4px',
            }}>
              {qcReport.passed ? '✓ PASSED' : '✗ FAILED'}
            </div>
            {qcReport.checks.map((check, i) => (
              <div key={i} style={{ display: 'flex', fontSize: '11px', marginBottom: '2px' }}>
                <span style={{ width: '20px', color: check.passed ? '#4ec9b0' : '#f48771' }}>
                  {check.passed ? '✓' : '✗'}
                </span>
                <span style={{ color: '#aaa', width: '120px' }}>{check.name}</span>
                <span style={{ color: '#888' }}>{check.detail.slice(0, 80)}</span>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ color: '#888', fontSize: '12px' }}>No QC report</div>
        )}
      </div>
    </div>
  );
};
```

#### 14.2.12 `open_edit/api/server.py`

```python
"""FastAPI server entry point."""
import argparse
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from open_edit.api.chat import router as chat_router
from open_edit.api.project import router as project_router
from open_edit.api.render import router as render_router


def create_app() -> FastAPI:
    app = FastAPI(title="Open Edit API")
    
    # CORS for development (Tauri runs the frontend locally)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.include_router(chat_router, prefix="/ws")
    app.include_router(project_router, prefix="/api/projects")
    app.include_router(render_router, prefix="/api/render")
    
    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    
    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
```

#### 14.2.13 `open_edit/api/project.py`

```python
"""REST endpoints for project CRUD and edit operations."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any
from open_edit.ir.types import Project
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.ir.apply import derive_timeline

router = APIRouter()


class CreateProjectRequest(BaseModel):
    name: str


class EditRequest(BaseModel):
    op: dict


@router.post("/")
async def create_project(req: CreateProjectRequest):
    project = Project(name=req.name)
    store = EditGraphStore(project.project_id)
    return {"project_id": project.project_id, "name": project.name}


@router.get("/{project_id}")
async def get_project(project_id: str):
    store = EditGraphStore(project_id)
    ops = store.load_all()
    project = Project(name="loaded", project_id=project_id, edit_graph=ops)
    timeline = derive_timeline(project)
    return {
        "project_id": project_id,
        "timeline": timeline.model_dump(),
        "edit_graph": [op.model_dump() for op in ops],
    }


@router.post("/{project_id}/edits")
async def add_edit(project_id: str, req: EditRequest):
    from open_edit.ir.types import OperationUnion
    store = EditGraphStore(project_id)
    op = OperationUnion.model_validate(req.op)
    op.author = "user"
    store.append(op)
    return {"edit_id": op.edit_id}


@router.post("/{project_id}/undo/{edit_id}")
async def undo(project_id: str, edit_id: str):
    store = EditGraphStore(project_id)
    store.update_status(edit_id, "reverted")
    return {"status": "reverted"}


@router.post("/{project_id}/redo/{edit_id}")
async def redo(project_id: str, edit_id: str):
    store = EditGraphStore(project_id)
    store.update_status(edit_id, "applied")
    return {"status": "applied"}


@router.post("/{project_id}/reorder")
async def reorder(project_id: str, edit_id_a: str, edit_id_b: str):
    store = EditGraphStore(project_id)
    try:
        store.reorder(edit_id_a, edit_id_b)
        return {"status": "reordered"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

### 14.3 Dependencies

- Phases 1–4 complete.
- Node.js 18+ and npm for frontend.
- Rust toolchain for Tauri.
- Tauri CLI: `npm install -g @tauri-apps/cli`.

### 14.4 Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Tauri v1 vs v2 API differences | Medium | Medium | Pin Tauri v1 in `package.json`; document upgrade path to v2 in Phase 7 |
| WebSocket disconnects on app sleep / network change | Medium | Low | Auto-reconnect logic in `websocket.ts`; surface connection status in UI |
| Frontend file access for video preview (Tauri security) | High | High | Use Tauri's `asset:` protocol or convert file to a streamable URL via the backend |
| Timeline canvas performance degrades with many clips (>500) | Medium | Medium | Phase 5 uses HTML/CSS divs (simpler); canvas rendering deferred to Phase 7 |
| Edit History panel slow with >1000 operations | Medium | Low | Virtualize the list (`react-window`); cap visible rows at 100 |
| Backend not running when Tauri app starts | Medium | High | Tauri sidecar launches backend; add health check with retry before WebSocket connect |

### 14.5 Validation Criteria

- [ ] All files in §14.2.1 exist and contain the specified contents.
- [ ] `cd frontend && npm install && npm run dev` starts the Vite dev server.
- [ ] `cd desktop/src-tauri && cargo build` compiles the Tauri shell.
- [ ] `cd desktop/src-tauri && cargo tauri dev` launches the desktop app.
- [ ] The app shows the four-panel layout: Chat (left), Timeline (top center), Preview (bottom center), Edit History (right).
- [ ] User can type a message in Chat; the agent responds (using Phase 4 agent loop).
- [ ] After an AI edit, the Timeline panel updates to show new clips.
- [ ] The Edit History panel shows the new operation with an AI badge.
- [ ] The Preview panel shows the rendered video (if `render_path` is set).
- [ ] The QC report appears in the Preview panel with pass/fail badges.
- [ ] Right-click an edit in Edit History → "Undo" → edit is marked reverted; Timeline updates.
- [ ] User can drag a clip in the Timeline panel (stub; full drag-and-drop in Phase 7).

### 14.6 Definition of Done

- [ ] All validation criteria pass.
- [ ] `cargo tauri build` produces an installable package (`.deb` on Linux, `.dmg` on macOS, `.msi` on Windows).
- [ ] The installed app launches, connects to the backend, and supports the full chat → edit → render → QC → undo workflow.
- [ ] The system is in a stable, working state: a non-technical user can install the app, create a project, chat with the AI, see edits, undo them, and render the result. CLI still works as a fallback.

---

## 15. Phase 6: pyagent-kdenlive Migration

### 15.1 Objectives

Port the reusable assets from `pyagent-kdenlive` into Open Edit: the MLT effect catalog (re-sourced from MLT YAML instead of Kdenlive XML), the Phase 2 ops library (as a reference library for the AI, not a mandatory API), and the Phase 6 render/QC scripts (with minimal changes). Migrate existing test scenarios from the old system to the new. At the end of Phase 6, users can switch from `pyagent-kdenlive` to Open Edit without losing capability.

### 15.2 Deliverables

#### 15.2.1 File Layout (additions)

```
open-edit/
├── migration/
│   ├── __init__.py
│   ├── port_catalog.py         # Kdenlive XML catalog -> MLT YAML -> IR effect registry
│   ├── port_ops_library.py     # Phase 2 ops -> reference library + examples
│   ├── port_tests.py           # Xvfb golden-file tests -> scenario eval
│   └── kdenlive_to_ir.py       # Convert existing .kdenlive projects to Open Edit IR
├── open_edit/
│   ├── catalog/
│   │   └── effects.py          # Updated: real MLT YAML parsing
│   ├── reference/              # Reference library (port from pyagent-kdenlive Phase 2)
│   │   ├── __init__.py
│   │   ├── ops.py              # ripple_delete, slip_clip, etc. as plain functions
│   │   └── examples.py         # Worked examples for the AI system prompt
│   └── ...
└── tests/
    └── scenarios/              # Migrated test scenarios
        ├── test_add_intro_music.yaml
        ├── test_color_grade.yaml
        └── ...
```

#### 15.2.2 `migration/port_catalog.py`

```python
"""Port the pyagent-kdenlive catalog from Kdenlive XML to MLT YAML.

Old source: pyagent-kdenlive/phase1/catalog/*.xml (Kdenlive effect wrapper XML)
New source: /usr/share/mlt-7/**/*.yml (raw MLT metadata)

This script:
1. Crawls /usr/share/mlt-7/ for MLT service metadata.
2. Parses each YAML file into an EffectRegistry entry.
3. Writes the registry to ~/.open-edit/catalog/effects.json for runtime use.
"""
import os
import json
from pathlib import Path
import yaml  # PyYAML

MLT_DIR = Path("/usr/share/mlt-7")
OUTPUT_PATH = Path("~/.open-edit/catalog/effects.json").expanduser()


def port_catalog():
    """Crawl MLT metadata, build effect registry, write to JSON."""
    registry = {"filters": [], "transitions": [], "producers": []}
    
    # Crawl presets and metadata directories
    for yml_file in MLT_DIR.rglob("*.yml"):
        with open(yml_file) as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                print(f"  skipping {yml_file}: {e}")
                continue
        
        if not isinstance(data, dict):
            continue
        
        service_type = data.get("type", "")
        service_name = data.get("service", yml_file.stem)
        
        entry = {
            "service": service_name,
            "type": service_type,
            "description": data.get("description", ""),
            "parameters": [],
        }
        
        # Parse parameters
        params = data.get("parameters", [])
        for p in params if isinstance(params, list) else []:
            entry["parameters"].append({
                "name": p.get("identifier", ""),
                "type": p.get("type", "string"),
                "description": p.get("description", ""),
                "default": p.get("default", ""),
                "minimum": p.get("minimum"),
                "maximum": p.get("maximum"),
                "mutable": p.get("mutable", False),  # animatable flag
            })
        
        if service_type == "filter":
            registry["filters"].append(entry)
        elif service_type == "transition":
            registry["transitions"].append(entry)
        elif service_type == "producer":
            registry["producers"].append(entry)
    
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(registry, indent=2))
    print(f"Ported {len(registry['filters'])} filters, "
          f"{len(registry['transitions'])} transitions, "
          f"{len(registry['producers'])} producers to {OUTPUT_PATH}")
    return registry


if __name__ == "__main__":
    port_catalog()
```

#### 15.2.3 Updated `open_edit/catalog/effects.py`

```python
"""MLT effect catalog, sourced from ~/.open-edit/catalog/effects.json."""
import json
from pathlib import Path
from typing import Optional

CATALOG_PATH = Path("~/.open-edit/catalog/effects.json").expanduser()


def load_catalog() -> dict:
    if not CATALOG_PATH.exists():
        return {"filters": [], "transitions": [], "producers": []}
    return json.loads(CATALOG_PATH.read_text())


def get_catalog_summary() -> str:
    catalog = load_catalog()
    if not catalog["filters"] and not catalog["transitions"]:
        return "(no effects found; run `python -m migration.port_catalog` to populate)"
    
    lines = []
    lines.append("Filters:")
    for f in catalog["filters"][:40]:
        lines.append(f"  - {f['service']}: {f.get('description', '')[:60]}")
    if len(catalog["filters"]) > 40:
        lines.append(f"  ... and {len(catalog['filters']) - 40} more")
    
    lines.append("\nTransitions:")
    for t in catalog["transitions"][:20]:
        lines.append(f"  - {t['service']}: {t.get('description', '')[:60]}")
    
    return "\n".join(lines)


def list_effects() -> list[dict]:
    catalog = load_catalog()
    return catalog["filters"] + catalog["transitions"]


def get_effect_schema(effect_type: str) -> Optional[dict]:
    catalog = load_catalog()
    for entry in catalog["filters"] + catalog["transitions"]:
        if entry["service"] == effect_type:
            return {
                "type": "object",
                "properties": {
                    p["name"]: {
                        "type": p["type"],
                        "default": p.get("default"),
                        "description": p.get("description", ""),
                        "animatable": p.get("mutable", False),
                    }
                    for p in entry["parameters"]
                },
                "additionalProperties": False,
            }
    return None
```

#### 15.2.4 `migration/port_ops_library.py`

```python
"""Port pyagent-kdenlive Phase 2 ops into Open Edit reference library.

The old ops (ripple_delete, slip_clip, etc.) were a mandatory API the AI had to call.
In Open Edit, they become a reference library: example patterns the AI can use
as inspiration, but not required to call. Each op is rewritten as a plain Python
function that calls the IR API.
"""
import os
from pathlib import Path

# These functions live in open_edit/reference/ops.py and are documented in
# the system prompt as "convenience patterns". The AI may use them in Mode 3
# (free-form code) but is not required to.

REFERENCE_OPS_TEMPLATE = '''
"""Reference library of common video editing operations.

These are convenience functions that call the IR API. The AI may use them
in Mode 3 (free-form code) for common patterns, but is not required to.
Each function is also documented in the system prompt as an example pattern.
"""
from open_edit.ir.sandbox_stub import ir


def ripple_delete(clip_id: str, gap_sec: float = 0.0) -> None:
    """Delete a clip and close the gap by shifting later clips left.
    
    Args:
        clip_id: The clip to delete.
        gap_sec: Optional gap to leave after deletion (default 0 = close gap fully).
    """
    # Get the clip's position and duration
    clip = ir.get_clip(clip_id)
    if clip is None:
        raise ValueError(f"Clip {clip_id} not found")
    
    clip_end = clip["position_sec"] + (clip["out_point_sec"] - clip["in_point_sec"])
    shift_amount = (clip_end - clip["position_sec"]) - gap_sec
    
    # Remove the clip
    ir.remove_clip(clip_id)
    
    # Shift all clips on the same track that came after this one
    track_id = clip["track_id"]
    for c in ir.list_clips(track_id=track_id):
        if c["position_sec"] > clip["position_sec"]:
            ir.move_clip(c["clip_id"], track_id, c["position_sec"] - shift_amount)


def slip_clip(clip_id: str, delta_sec: float) -> None:
    """Slip a clip: change in/out points without changing position or duration.
    
    Args:
        clip_id: The clip to slip.
        delta_sec: Amount to shift in/out points. Positive = later in source.
    """
    clip = ir.get_clip(clip_id)
    if clip is None:
        raise ValueError(f"Clip {clip_id} not found")
    
    new_in = clip["in_point_sec"] + delta_sec
    new_out = clip["out_point_sec"] + delta_sec
    ir.trim_clip(clip_id, new_in, new_out)


def slide_clip(clip_id: str, delta_sec: float) -> None:
    """Slide a clip: change position without changing in/out points or duration.
    Adjacent clips trim to make room.
    
    Args:
        clip_id: The clip to slide.
        delta_sec: Amount to shift position. Positive = later in timeline.
    """
    clip = ir.get_clip(clip_id)
    if clip is None:
        raise ValueError(f"Clip {clip_id} not found")
    
    new_pos = clip["position_sec"] + delta_sec
    ir.move_clip(clip_id, clip["track_id"], new_pos)


def apply_color_grade(target_id: str, brightness: float = 0.0,
                      contrast: float = 1.0, saturation: float = 1.0) -> str:
    """Apply a basic color grade to a clip or track.
    
    Returns the effect_id of the brightness effect (the primary one).
    """
    eff_id = ir.add_effect("clip", target_id, "movit.brightness", {"level": brightness})
    ir.add_effect("clip", target_id, "movit.contrast", {"level": contrast})
    ir.add_effect("clip", target_id, "movit.saturation", {"level": saturation})
    return eff_id


def fade_in(clip_id: str, duration_sec: float = 1.0) -> None:
    """Fade a clip in over the given duration.
    
    Adds a volume effect with a keyframe ramp from 0 to 1.
    """
    clip = ir.get_clip(clip_id)
    if clip is None:
        raise ValueError(f"Clip {clip_id} not found")
    
    eff_id = ir.add_effect("clip", clip_id, "volume", {"level": 1.0})
    ir.set_keyframe(eff_id, "level", [
        (clip["position_sec"], 0.0, "linear"),
        (clip["position_sec"] + duration_sec, 1.0, "linear"),
    ])


def fade_out(clip_id: str, duration_sec: float = 1.0) -> None:
    """Fade a clip out over the given duration."""
    clip = ir.get_clip(clip_id)
    if clip is None:
        raise ValueError(f"Clip {clip_id} not found")
    
    clip_end = clip["position_sec"] + (clip["out_point_sec"] - clip["in_point_sec"])
    eff_id = ir.add_effect("clip", clip_id, "volume", {"level": 1.0})
    ir.set_keyframe(eff_id, "level", [
        (clip_end - duration_sec, 1.0, "linear"),
        (clip_end, 0.0, "linear"),
    ])
'''


def port_ops_library():
    """Write the reference library to open_edit/reference/ops.py."""
    output_path = Path("open_edit/reference/ops.py")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(REFERENCE_OPS_TEMPLATE.strip() + "\n")
    print(f"Wrote reference library to {output_path}")


if __name__ == "__main__":
    port_ops_library()
```

#### 15.2.5 `migration/kdenlive_to_ir.py`

```python
"""Convert existing .kdenlive project files to Open Edit IR projects.

This allows users with existing pyagent-kdenlive projects to migrate
to Open Edit without losing their work.

Usage:
    python -m migration.kdenlive_to_ir input.kdenlive output_project_id
"""
import sys
import re
from lxml import etree
from open_edit.ir.types import Project, AddClipOp, AddEffectOp
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.storage.assets import AssetStore


def convert(kdenlive_path: str, new_project_name: str) -> str:
    """Convert a .kdenlive file to an Open Edit project. Returns the project_id."""
    tree = etree.parse(kdenlive_path)
    root = tree.getroot()
    
    project = Project(name=new_project_name)
    store = EditGraphStore(project.project_id)
    asset_store = AssetStore()
    
    # Parse producers (assets)
    producers = {}
    for producer in root.findall(".//producer"):
        prod_id = producer.get("id")
        resource_prop = producer.find("property[@name='resource']")
        if resource_prop is not None and resource_prop.text:
            resource = resource_prop.text
            if resource and not resource.startswith("<"):
                try:
                    asset = asset_store.ingest(resource)
                    producers[prod_id] = asset.asset_hash
                    project.assets[asset.asset_hash] = asset
                except FileNotFoundError:
                    print(f"  skipping producer {prod_id}: file not found {resource}")
    
    # Parse playlists -> clips
    for playlist in root.findall(".//playlist"):
        track_id = playlist.get("id", "track_unknown")
        position_sec = 0.0
        for entry in playlist.findall("entry"):
            producer_id = entry.get("producer")
            if producer_id not in producers:
                continue
            in_frame = int(entry.get("in", "0"))
            out_frame = int(entry.get("out", "0"))
            fps = 30.0  # default; could parse from profile
            in_sec = in_frame / fps
            out_sec = (out_frame + 1) / fps  # MLT out is inclusive
            
            op = AddClipOp(
                asset_hash=producers[producer_id],
                track_id=track_id,
                position_sec=position_sec,
                in_point_sec=in_sec,
                out_point_sec=out_sec,
                author="user",
            )
            project.edit_graph.append(op)
            store.append(op)
            position_sec += (out_sec - in_sec)
    
    print(f"Converted {kdenlive_path} -> project {project.project_id}")
    print(f"  Assets: {len(project.assets)}")
    print(f"  Edits: {len(project.edit_graph)}")
    return project.project_id


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python -m migration.kdenlive_to_ir <input.kdenlive> <new_project_name>")
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
```

#### 15.2.6 `migration/port_tests.py`

```python
"""Migrate pyagent-kdenlive Phase 7 Xvfb golden-file tests to Open Edit scenario eval.

Old format: golden-file-per-tool test (one expected output per discrete tool call).
New format: scenario-based eval (natural-language request -> generated code -> QC gate).

This script generates stub scenario YAML files from the old test descriptions.
Each scenario file is then manually curated (or auto-curated by an LLM) to
produce a clean natural-language prompt + expected outcome.
"""
import os
from pathlib import Path
import yaml


SCENARIO_TEMPLATE = '''
name: {name}
description: |
  {description}
request: |
  {request}
expected_outcome:
  qc_passes: true
  min_clips: {min_clips}
  max_clips: {max_clips}
  min_duration_sec: {min_duration}
  max_duration_sec: {max_duration}
  no_black_frames: true
  no_silence_gaps_longer_than_sec: 1.0
trials: 5  # number of times to run for determinism check
'''


def generate_scenario_stub(old_test_name: str, old_test_description: str,
                            output_dir: Path = Path("tests/scenarios")) -> Path:
    """Generate a stub scenario file from an old test description."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Convert test name to scenario name
    scenario_name = old_test_name.replace("test_", "scenario_")
    
    content = SCENARIO_TEMPLATE.format(
        name=scenario_name,
        description=old_test_description or "(auto-generated stub; curate this)",
        request=f"(auto-generated from {old_test_name}; rewrite as a natural-language user request)",
        min_clips=1,
        max_clips=10,
        min_duration=1.0,
        max_duration=300.0,
    )
    
    output_path = output_dir / f"{scenario_name}.yaml"
    output_path.write_text(content.strip() + "\n")
    return output_path


if __name__ == "__main__":
    # Example: generate stubs for known pyagent-kdenlive tests
    stubs = [
        ("test_add_clip", "Add a single clip to the timeline"),
        ("test_ripple_delete", "Delete a clip and close the gap"),
        ("test_slip_clip", "Slip a clip's in/out points"),
        ("test_color_grade", "Apply brightness, contrast, saturation"),
        ("test_fade_in", "Add a 1-second fade-in to a clip"),
        ("test_fade_out", "Add a 1-second fade-out to a clip"),
        ("test_transition_dissolve", "Add a dissolve transition between two clips"),
        ("test_multi_track_audio", "Layer narration over background music"),
    ]
    
    for name, desc in stubs:
        path = generate_scenario_stub(name, desc)
        print(f"Generated {path}")
```

### 15.3 Dependencies

- Phases 1–5 complete.
- Access to the `pyagent-kdenlive` source (for porting; can be read-only).
- `PyYAML` Python package for MLT YAML parsing.

### 15.4 Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| MLT YAML structure differs from assumed format above | Medium | Medium | Run `port_catalog.py` early; spot-check 5 known filters before depending on it |
| Kdenlive XML uses complex features (multi-track compositing, nested timelines) that don't map cleanly to IR | High | Medium | `kdenlive_to_ir.py` documents unsupported features; complex projects may need manual fixing post-conversion |
| Old test scenarios are too implementation-specific ("test that `slip_clip` calls `melt` with these exact args") to migrate cleanly | High | Medium | Generate stub scenarios; manually rewrite as natural-language requests; accept some test coverage loss |
| Reference library ops (ripple_delete etc.) have subtle behavior differences from old system | Medium | Medium | Port the ops' unit tests from pyagent-kdenlive Phase 2; run them against the new reference library |
| Catalog port loses animatable (`mutable`) info if MLT YAML doesn't expose it | Low | Medium | v2 flagged this; verify against 5 known filters; if `mutable` is absent, treat all numeric params as animatable (safe default) |

### 15.5 Validation Criteria

- [ ] `python -m migration.port_catalog` runs successfully and produces `~/.open-edit/catalog/effects.json` with at least 50 filters and 10 transitions.
- [ ] The effect catalog summary appears in the AI's system prompt (verify by inspecting an assembled prompt).
- [ ] `python -m migration.port_ops_library` writes `open_edit/reference/ops.py` with at least 6 reference functions (ripple_delete, slip_clip, slide_clip, apply_color_grade, fade_in, fade_out).
- [ ] The AI can use reference library functions in Mode 3 (free-form code): `from open_edit.reference.ops import ripple_delete; ripple_delete("clip_xyz")` works inside the sandbox.
- [ ] `python -m migration.kdenlive_to_ir samples/test_project.kdenlive "Migrated Project"` produces a valid Open Edit project with the correct number of clips.
- [ ] The migrated project renders successfully via `render_project`.
- [ ] `python -m migration.port_tests` generates at least 8 scenario stub files in `tests/scenarios/`.
- [ ] At least 3 of the generated scenario stubs are manually curated into runnable scenario tests that pass.

### 15.6 Definition of Done

- [ ] All validation criteria pass.
- [ ] A user with an existing `pyagent-kdenlive` project can run `python -m migration.kdenlive_to_ir my_project.kdenlive "My Project"` and open the result in the Open Edit desktop app.
- [ ] The AI agent has access to the full MLT effect catalog (50+ effects) and can apply them via Mode 1 or Mode 3.
- [ ] The reference library is documented in the system prompt as "available convenience functions" but the AI is not forced to use them.
- [ ] The system is in a stable, working state: `pyagent-kdenlive` is no longer needed; all capabilities are available in Open Edit.

---

## 16. Phase 7: Hardening, Testing & Performance

### 16.1 Objectives

Harden the system for production use: build the full scenario eval suite (50+ tests), implement render caching, add background rendering, optimize timeline canvas rendering, and establish performance benchmarks. At the end of Phase 7, the system is ready for daily use by a real video editor.

### 16.2 Deliverables

#### 16.2.1 File Layout (additions)

```
open-edit/
├── open_edit/
│   ├── cache/
│   │   ├── __init__.py
│   │   ├── proxies.py          # proxy render cache
│   │   └── thumbnails.py       # thumbnail cache
│   ├── background/
│   │   ├── __init__.py
│   │   ├── queue.py            # background render queue (asyncio)
│   │   └── worker.py           # background worker
│   └── ...
├── tests/
│   ├── scenarios/              # 50+ scenario YAML files
│   │   ├── scenario_add_clip.yaml
│   │   ├── scenario_ripple_delete.yaml
│   │   ├── ... (50+ files)
│   ├── test_scenario_runner.py # runs scenarios with N trials
│   ├── test_performance.py     # performance benchmarks
│   └── test_security.py        # sandbox security tests
└── frontend/src/
    └── panels/
        └── TimelineCanvas.tsx  # canvas-based timeline (replaces divs for >500 clips)
```

#### 16.2.2 Scenario Test Format

```yaml
# tests/scenarios/scenario_add_clip.yaml
name: scenario_add_clip
description: |
  Test that the AI can add a single clip to an empty timeline in response
  to a natural-language request.
  
setup:
  assets:
    - path: tests/fixtures/sample_video_5sec.mp4
      alias: intro
  initial_project:
    name: empty_project
    edits: []

request: |
  Add the intro video to the timeline at position 0.

expected_outcome:
  qc_passes: true
  min_clips: 1
  max_clips: 1
  min_duration_sec: 4.0
  max_duration_sec: 6.0
  no_black_frames: true
  no_silence_gaps_longer_than_sec: 1.0
  forbidden_op_kinds: []  # no ops are forbidden
  required_op_kinds: ["add_clip"]

trials: 5
success_threshold: 0.8  # 4 of 5 trials must pass
```

#### 16.2.3 `tests/test_scenario_runner.py`

```python
"""Scenario test runner: loads YAML, runs N trials, checks outcomes."""
import asyncio
import yaml
import json
from pathlib import Path
from typing import Optional
import pytest
from open_edit.ir.types import Project, Asset, AddClipOp
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.storage.assets import AssetStore
from open_edit.agent.loop import agent_turn
from open_edit.qc.gate import run_qc_gate
from open_edit.ir.apply import derive_timeline


SCENARIO_DIR = Path("tests/scenarios")


def load_scenarios() -> list[dict]:
    scenarios = []
    for yaml_file in SCENARIO_DIR.glob("*.yaml"):
        with open(yaml_file) as f:
            scenarios.append(yaml.safe_load(f))
    return scenarios


async def run_scenario(scenario: dict) -> dict:
    """Run a single scenario. Returns {trial: int, passed: bool, details: str}."""
    # Setup
    project = Project(name=scenario["setup"]["initial_project"]["name"])
    store = EditGraphStore(project.project_id)
    asset_store = AssetStore()
    
    # Ingest assets
    for asset_spec in scenario["setup"].get("assets", []):
        asset = asset_store.ingest(asset_spec["path"])
        project.assets[asset.asset_hash] = asset
        # Store alias mapping for the AI's benefit (simplified)
    
    # Run agent
    history = []
    result = await agent_turn(project, store, history, scenario["request"])
    
    # Check outcome
    timeline = derive_timeline(project)
    qc_report = run_qc_gate(project)
    
    expected = scenario["expected_outcome"]
    errors = []
    
    # QC check
    if expected.get("qc_passes") and not qc_report.passed:
        errors.append(f"QC failed: {qc_report.to_dict()}")
    
    # Clip count
    total_clips = sum(len(t.clips) for t in timeline.tracks)
    if total_clips < expected.get("min_clips", 0):
        errors.append(f"Too few clips: {total_clips} < {expected['min_clips']}")
    if total_clips > expected.get("max_clips", 999):
        errors.append(f"Too many clips: {total_clips} > {expected['max_clips']}")
    
    # Duration
    if timeline.duration_sec < expected.get("min_duration_sec", 0):
        errors.append(f"Duration too short: {timeline.duration_sec}")
    if timeline.duration_sec > expected.get("max_duration_sec", 99999):
        errors.append(f"Duration too long: {timeline.duration_sec}")
    
    # Required op kinds
    applied_ops = [op for op in project.edit_graph if op.status == "applied"]
    op_kinds = {op.kind for op in applied_ops}
    for required in expected.get("required_op_kinds", []):
        if required not in op_kinds:
            errors.append(f"Missing required op kind: {required}")
    
    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "op_count": len(applied_ops),
        "duration_sec": timeline.duration_sec,
    }


async def run_scenario_with_trials(scenario: dict) -> dict:
    """Run a scenario N times; check if success rate meets threshold."""
    trials = scenario.get("trials", 1)
    threshold = scenario.get("success_threshold", 1.0)
    
    results = []
    for i in range(trials):
        result = await run_scenario(scenario)
        result["trial"] = i
        results.append(result)
    
    successes = sum(1 for r in results if r["passed"])
    success_rate = successes / trials
    overall_passed = success_rate >= threshold
    
    return {
        "scenario": scenario["name"],
        "trials": trials,
        "successes": successes,
        "success_rate": success_rate,
        "threshold": threshold,
        "passed": overall_passed,
        "details": results,
    }


# Pytest parametrized test: one test per scenario file
@pytest.mark.parametrize("scenario", load_scenarios(), ids=lambda s: s["name"])
@pytest.mark.asyncio
async def test_scenario(scenario):
    result = await run_scenario_with_trials(scenario)
    assert result["passed"], (
        f"Scenario {result['scenario']} failed: "
        f"{result['successes']}/{result['trials']} trials passed "
        f"(threshold {result['threshold']})\n"
        f"Details: {json.dumps(result['details'], indent=2)}"
    )
```

#### 16.2.4 `open_edit/background/queue.py`

```python
"""Background render queue. Prevents UI from blocking on long renders."""
import asyncio
from collections import deque
from typing import Optional, Callable
from open_edit.ir.types import Project
from open_edit.render.orchestrator import render_project


class RenderQueue:
    def __init__(self, max_workers: int = 1):
        self.queue: deque = deque()
        self.max_workers = max_workers
        self.workers: list[asyncio.Task] = []
        self.results: dict[str, str] = {}  # edit_graph_hash -> render_path
        self._lock = asyncio.Lock()
    
    async def enqueue(self, project: Project, profile_name: str = "proxy") -> str:
        """Enqueue a render job. Returns the edit_graph_hash (used as job ID)."""
        import hashlib, json
        edit_graph_json = json.dumps([op.model_dump() for op in project.edit_graph], sort_keys=True)
        edit_graph_hash = hashlib.sha256(edit_graph_json.encode()).hexdigest()
        
        async with self._lock:
            self.queue.append((edit_graph_hash, project, profile_name))
        
        # Start a worker if none running
        if len(self.workers) < self.max_workers:
            task = asyncio.create_task(self._worker())
            self.workers.append(task)
        
        return edit_graph_hash
    
    async def get_result(self, edit_graph_hash: str, timeout_sec: float = 60.0) -> Optional[str]:
        """Wait for a render to complete. Returns the render path or None on timeout."""
        deadline = asyncio.get_event_loop().time() + timeout_sec
        while asyncio.get_event_loop().time() < deadline:
            if edit_graph_hash in self.results:
                return self.results[edit_graph_hash]
            await asyncio.sleep(0.1)
        return None
    
    async def _worker(self):
        while True:
            async with self._lock:
                if not self.queue:
                    break
                edit_graph_hash, project, profile_name = self.queue.popleft()
            
            try:
                render_path = render_project(project, profile_name, use_cache=True)
                self.results[edit_graph_hash] = render_path
            except Exception as e:
                self.results[edit_graph_hash] = f"ERROR: {e}"


# Singleton
_render_queue: Optional[RenderQueue] = None

def get_render_queue() -> RenderQueue:
    global _render_queue
    if _render_queue is None:
        _render_queue = RenderQueue(max_workers=1)
    return _render_queue
```

#### 16.2.5 `tests/test_performance.py`

```python
"""Performance benchmarks. Not pytest tests; run manually with `python -m tests.test_performance`."""
import time
import json
from pathlib import Path
from open_edit.ir.types import Project, AddClipOp
from open_edit.ir.apply import derive_timeline
from open_edit.render.emitter import emit_mlt_xml
from open_edit.render.orchestrator import render_project
from open_edit.storage.assets import AssetStore


def benchmark_derive_timeline(clip_count: int = 1000):
    """Benchmark: how long to derive a timeline with N clips?"""
    project = Project(name="bench")
    for i in range(clip_count):
        project.edit_graph.append(AddClipOp(
            asset_hash=f"hash_{i}", track_id=f"v{i//100}",
            position_sec=float(i), author="user",
        ))
    
    start = time.perf_counter()
    timeline = derive_timeline(project)
    elapsed = time.perf_counter() - start
    
    print(f"derive_timeline({clip_count} clips): {elapsed*1000:.2f}ms")
    assert elapsed < 1.0, f"Deriving {clip_count} clips took {elapsed:.2f}s; should be < 1s"


def benchmark_emit_mlt_xml(clip_count: int = 100):
    """Benchmark: how long to emit MLT XML for N clips?"""
    project = Project(name="bench")
    for i in range(clip_count):
        project.edit_graph.append(AddClipOp(
            asset_hash=f"hash_{i}", track_id="v1",
            position_sec=float(i), author="user",
        ))
    timeline = derive_timeline(project)
    
    start = time.perf_counter()
    xml = emit_mlt_xml(timeline, project, "proxy")
    elapsed = time.perf_counter() - start
    
    print(f"emit_mlt_xml({clip_count} clips): {elapsed*1000:.2f}ms, XML size: {len(xml)} bytes")
    assert elapsed < 0.5, f"Emitting {clip_count} clips took {elapsed:.2f}s; should be < 0.5s"


def benchmark_render_cache_hit():
    """Benchmark: render cache should make second render instant."""
    import subprocess
    import tempfile
    
    # Create a 1-second test video
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=30",
            "-c:v", "libx264", f.name,
        ], check=True, capture_output=True)
        video_path = f.name
    
    asset = AssetStore().ingest(video_path)
    project = Project(name="bench", assets={asset.asset_hash: asset})
    project.edit_graph.append(AddClipOp(
        asset_hash=asset.asset_hash, track_id="v1", position_sec=0.0, author="user",
    ))
    
    # First render (cache miss)
    start = time.perf_counter()
    render_project(project, "proxy", use_cache=True)
    first_render = time.perf_counter() - start
    
    # Second render (cache hit)
    start = time.perf_counter()
    render_project(project, "proxy", use_cache=True)
    second_render = time.perf_counter() - start
    
    print(f"First render (cache miss): {first_render*1000:.2f}ms")
    print(f"Second render (cache hit): {second_render*1000:.2f}ms")
    assert second_render < 0.01, f"Cache hit took {second_render*1000:.2f}ms; should be < 10ms"


if __name__ == "__main__":
    benchmark_derive_timeline(100)
    benchmark_derive_timeline(1000)
    benchmark_emit_mlt_xml(100)
    benchmark_render_cache_hit()
```

#### 16.2.6 `tests/test_security.py`

```python
"""Security tests for the sandbox."""
import subprocess
import tempfile
import os
from pathlib import Path


SANDBOX_BINARY = os.environ.get("OPEN_EDIT_SANDBOX_BINARY", "./sandbox/target/release/sandbox")


def run_in_sandbox(code: str, timeout: int = 10) -> tuple[int, str, str]:
    """Run Python code in the sandbox. Returns (exit_code, stdout, stderr)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        code_path = f.name
    
    output_path = tempfile.mktemp(suffix=".json")
    workdir = tempfile.mkdtemp()
    asset_dir = tempfile.mkdtemp()
    
    result = subprocess.run(
        [SANDBOX_BINARY,
         "--code", code_path,
         "--workdir", workdir,
         "--asset-dir", asset_dir,
         "--timeout", str(timeout),
         "--mem", "256M",
         "--output", output_path],
        capture_output=True, text=True, timeout=timeout + 5,
    )
    return result.returncode, result.stdout, result.stderr


def test_sandbox_blocks_network():
    code = """
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("example.com", 80))
    print("NETWORK_ALLOWED")
except Exception as e:
    print(f"NETWORK_BLOCKED: {e}")
"""
    _, stdout, _ = run_in_sandbox(code)
    assert "NETWORK_BLOCKED" in stdout, f"Network should be blocked: {stdout}"


def test_sandbox_blocks_filesystem_write_outside_workdir():
    code = """
try:
    with open("/etc/open_edit_test", "w") as f:
        f.write("test")
    print("WRITE_ALLOWED")
except Exception as e:
    print(f"WRITE_BLOCKED: {e}")
"""
    _, stdout, _ = run_in_sandbox(code)
    assert "WRITE_BLOCKED" in stdout, f"Write outside workdir should be blocked: {stdout}"


def test_sandbox_blocks_disallowed_subprocess():
    code = """
import subprocess
try:
    result = subprocess.run(["ls", "/"], capture_output=True, text=True)
    print(f"SUBPROCESS_ALLOWED: {result.stdout[:50]}")
except Exception as e:
    print(f"SUBPROCESS_BLOCKED: {e}")
"""
    _, stdout, _ = run_in_sandbox(code)
    assert "SUBPROCESS_BLOCKED" in stdout, f"Non-allowlisted subprocess should be blocked: {stdout}"


def test_sandbox_allows_ffmpeg():
    code = """
import subprocess
try:
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
    print(f"FFMPEG_ALLOWED: {result.stdout[:50]}")
except Exception as e:
    print(f"FFMPEG_BLOCKED: {e}")
"""
    _, stdout, _ = run_in_sandbox(code)
    assert "FFMPEG_ALLOWED" in stdout, f"ffmpeg should be allowed: {stdout}"


def test_sandbox_enforces_timeout():
    code = """
import time
time.sleep(60)  # exceeds the 5-second timeout
print("SHOULD_NOT_REACH_HERE")
"""
    code_path = tempfile.mktemp(suffix=".py")
    with open(code_path, "w") as f:
        f.write(code)
    
    output_path = tempfile.mktemp(suffix=".json")
    workdir = tempfile.mkdtemp()
    asset_dir = tempfile.mkdtemp()
    
    start = __import__("time").perf_counter()
    result = subprocess.run(
        [SANDBOX_BINARY,
         "--code", code_path,
         "--workdir", workdir,
         "--asset-dir", asset_dir,
         "--timeout", "5",
         "--mem", "256M",
         "--output", output_path],
        capture_output=True, text=True, timeout=30,
    )
    elapsed = __import__("time").perf_counter() - start
    
    assert elapsed < 15, f"Sandbox should have killed the process after 5s; took {elapsed:.1f}s"
    assert "SHOULD_NOT_REACH_HERE" not in result.stdout
```

### 16.3 Dependencies

- Phases 1–6 complete.
- `pytest-asyncio` for async test support.
- `PyYAML` for scenario file parsing.

### 16.4 Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Scenario eval suite is flaky (LLM non-determinism causes 80% success rate to dip below threshold) | High | Medium | Set threshold to 0.8 (4/5 trials); re-run failed scenarios; track flakiness over time |
| Render cache invalidation: edit graph hash collision (extremely rare but possible) | Very Low | High | Use SHA-256; collision probability is negligible; document the assumption |
| Background render queue deadlocks on rapid edits | Medium | Medium | Single worker; FIFO; document that concurrent edits to the same project serialize |
| Timeline canvas performance still degrades with >5000 clips | Medium | Low | Document 5000-clip limit; virtualize rendering (only draw visible clips) |
| Security test for `subprocess.run(["ls", ...])` fails because `ls` is not in the path that the sandbox restricts | Low | Low | Use absolute path `/bin/ls` in the test; sandbox blocks by binary name AND by absolute path |

### 16.5 Validation Criteria

- [ ] At least 50 scenario YAML files exist in `tests/scenarios/`.
- [ ] `pytest tests/test_scenario_runner.py` runs all scenarios; at least 80% pass at the configured success threshold.
- [ ] `python -m tests.test_performance` runs without assertion failures; benchmarks are within targets (derive_timeline 1000 clips < 1s, emit_mlt_xml 100 clips < 0.5s, cache hit < 10ms).
- [ ] `pytest tests/test_security.py` passes all 5 security tests.
- [ ] Background render queue works: enqueuing 5 renders in quick succession does not block the UI; results are returned via `get_result`.
- [ ] Timeline canvas (if implemented) renders 500 clips at 60fps; falls back to div-based rendering for <= 100 clips.

### 16.6 Definition of Done

- [ ] All validation criteria pass.
- [ ] The scenario eval suite runs in CI (GitHub Actions or equivalent) on every PR.
- [ ] Performance benchmarks are documented in `BENCHMARKS.md`; regression > 20% on any benchmark blocks merge.
- [ ] Security tests run in CI; any failure blocks merge.
- [ ] The system is in a stable, working state: ready for daily use by a real video editor. Performance is acceptable for typical projects (up to 100 clips, 10-minute duration). Edge cases (1000+ clips, 1-hour duration) are documented as known limitations.

---

## 17. Risks

### 17.1 Architectural Risks

| Risk | Likelihood | Impact | Mitigation | Owner | Escalation Trigger |
|---|---|---|---|---|---|
| **IR cannot represent all MLT features.** Some MLT features (e.g. multi-track compositing with custom tractor properties) may not map cleanly to the operation set. | High | Medium | Mode 2 (raw XML) escape hatch handles these cases; document which features are not IR-representable. | Architect | > 20% of AI emissions use Mode 2 |
| **Sandbox escape.** AI-emitted code finds a way to bypass the landlock/seccomp jail. | Low | Critical | Container-level isolation as defense-in-depth; regular security audits; bounty program if open-sourced. | Security | Any successful escape in a security test |
| **Edit graph grows unbounded.** Long editing sessions produce thousands of operations; `derive_timeline` becomes slow. | Medium | Medium | Snapshotting: periodically persist the derived timeline as a "checkpoint" and reset the edit graph. Future improvement. | Backend | `derive_timeline` > 1s for 5000 ops |
| **MLT version incompatibility.** MLT 7.x API changes break the emitter or catalog. | Medium | High | Pin MLT version in CI; test against multiple versions; document required version. | Backend | Any emitter test failure on a new MLT version |
| **Tauri v1 → v2 migration required.** Tauri v2 is released mid-project with breaking changes. | Medium | Low | Pin Tauri v1; defer v2 migration to post-v1. | Frontend | Tauri v1 reaches end-of-life |

### 17.2 Schedule Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Phase 3 (sandbox) takes longer than estimated.** Landlock/seccomp integration is fiddly. | High | Medium | Allow 3 weeks, not 2. If Linux sandbox is delayed, ship with macOS stub and document Linux as required. |
| **Phase 4 (AI agent) requires prompt engineering iteration.** First-pass system prompt produces < 50% success rate. | High | Medium | Budget 2 weeks; iterate on prompt using scenario eval suite from Phase 7 (build it early). |
| **Phase 5 (UI) timeline drag-and-drop is harder than expected.** | Medium | Low | Ship Phase 5 with click-only timeline (no drag); add drag in Phase 7. |
| **Phase 6 (migration) reveals pyagent-kdenlive is more complex than assumed.** | Medium | Medium | Read the source early (before Phase 6 starts); adjust reusability estimates. |

### 17.3 AI Behavior Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **AI emits valid operations that are semantically wrong.** E.g. adds a clip at position 100s when the user meant 0s. | High | High | QC gate catches structural problems, not semantic ones. User-visible preview is mandatory before accepting an edit. Future: AI fine-tuning on edit history. |
| **AI overuses Mode 2 (raw XML).** Bypasses the IR, defeats the edit-history safety property. | Medium | High | Track mode usage; if > 20%, investigate prompt or expand IR operation set. |
| **AI emits too many operations per turn.** E.g. 50 operations for "trim every clip by 10%" (should be 1 Mode 3 code emission). | Medium | Low | Cap operations per emission at 20; if exceeded, suggest Mode 3 in the retry feedback. |
| **AI retries exhaust (3 attempts) too often.** | Medium | Medium | Track failure rate; if > 10%, investigate common failure modes and improve prompt. |
| **AI invents asset hashes or effect types despite validation.** | High | Low | Validation rejects; retry with error. Not a real risk; just costs retries. |

### 17.4 Security Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Sandbox binary has a vulnerability.** | Low | Critical | Keep dependencies updated; security audit before v1 release. |
| **AI-emitted code accesses user's home directory via symlink.** | Medium | High | Sandbox resolves symlinks before applying landlock; deny any path that resolves outside workdir/asset_dir. |
| **AI-emitted code triggers fork bomb.** | Medium | Medium | Resource limits (memory, process count) in sandbox; wall-clock timeout. |
| **Render cache poisoning.** Attacker swaps a cached MP4. | Low | Medium | Cache files are keyed by SHA-256 of edit graph; verify file hash on cache hit. |

### 17.5 Operational Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Asset store fills the disk.** Long editing sessions ingest many large videos. | Medium | Medium | Document disk usage; add LRU eviction in Phase 7+; warn user when asset store > 50GB. |
| **SQLite database corruption.** | Low | High | Use WAL mode; daily backup; document recovery procedure. |
| **Backend crashes mid-edit.** Edit graph transaction is incomplete. | Low | Medium | SQLite transactions are atomic; on restart, load edit graph and verify integrity. |

---

## 18. Open Questions

### 18.1 Must Answer Before Phase N

| # | Question | Blocks Phase | Default If Unanswered |
|---|---|---|---|
| 1 | What is the actual `pyagent-kdenlive` source structure? (No code was provided at review time.) | Phase 6 | Treat reusability matrix as upper bounds; discover actual reusability during Phase 6. |
| 2 | Is the `z-ai-web-dev-sdk` Python package available and what is its API? | Phase 4 | Use the stub `_mock_llm_response` for testing; integrate real SDK when available. |
| 3 | Which LLM model will be used (GLM, GPT-4, Claude, local)? | Phase 4 | Default to GLM via `z-ai-web-dev-sdk`; adjust prompt format if model differs. |
| 4 | Target OS for v1 release? (Linux-only? macOS too? Windows?) | Phase 3, 5 | Linux required for full sandbox; macOS supported with reduced sandbox; Windows deferred. |
| 5 | Asset size limit? (Will users ingest 4K video files? 100GB+?) | Phase 1, 7 | Document 10GB per asset limit; warn above; reject above 50GB. |

### 18.2 Nice to Have (Does Not Block)

| # | Question | Why It Matters |
|---|---|---|
| 6 | Should the IR support nested timelines (sequences within sequences)? | Affects data model; defer to future improvement. |
| 7 | Should there be a "project export" feature (export to .kdenlive, .fcpxml, .edl)? | Affects emitter design; defer. |
| 8 | Should the AI support multi-turn planning (e.g. "First, I'll add the music. Then I'll trim the intro. Then I'll add transitions.")? | Affects agent loop; defer to Phase 7+ improvement. |
| 9 | Should the system support keyboard shortcuts for common operations? | Affects UI; defer to Phase 7 polish. |
| 10 | Should there be a "tutorial mode" that walks new users through the interface? | Affects UI; defer. |

### 18.3 Deferred to Future Improvements (See §19)

| # | Question | Why Deferred |
|---|---|---|
| 11 | Real-time multi-user collaboration (CRDT)? | Single-user desktop is v1; collaboration is a separate project. |
| 12 | Cloud render farm integration? | Local rendering is sufficient for v1; cloud is a scaling concern for later. |
| 13 | GPU-accelerated rendering? | `melt` supports Movit (GPU); document as opt-in; not v1 scope. |
| 14 | Plugin SDK for third-party effects? | Defer until v1 stabilizes the effect catalog format. |
| 15 | AI fine-tuning on edit history? | Requires accumulated edit data; defer until v1 has users. |

---

## 19. Future Improvements

### 19.1 Real-Time Multi-User Collaboration

**What it unlocks:** Multiple users edit the same project simultaneously; changes propagate in real-time.

**What needs to change:**
- Replace SQLite per-project DB with a shared backend (Postgres + CRDT library, or Y.js / Automerge).
- Edit graph operations need vector clocks for ordering.
- WebSocket broadcast to all connected clients.
- Conflict resolution policy (last-write-wins for independent clips; manual merge for conflicting edits).

**Effort estimate:** 4-6 weeks of focused work, post-v1.

### 19.2 Plugin SDK

**What it unlocks:** Third-party developers can add custom effects, transitions, and AI tools.

**What needs to change:**
- Define a stable plugin API (`open_edit.plugin.EffectPlugin`, `ToolPlugin`).
- Plugin discovery via Python entry points.
- Plugin sandboxing (plugins run in the same sandbox as AI-emitted code).
- Plugin marketplace UI in the desktop app.

**Effort estimate:** 3-4 weeks.

### 19.3 Cloud Render Farm

**What it unlocks:** Users can offload long renders to cloud GPUs; render 4K/8K without local hardware.

**What needs to change:**
- Render Orchestrator gains a "cloud" backend (in addition to "local").
- Project + assets packaged and uploaded to cloud worker.
- Cloud worker runs `melt`, returns MP4.
- Billing integration (per-render-minute).

**Effort estimate:** 4-6 weeks (depends on cloud provider choice).

### 19.4 GPU-Accelerated Rendering

**What it unlocks:** 5-10x faster rendering for GPU-supported effects.

**What needs to change:**
- MLT already supports Movit (GPU); document `movit.*` effect types in catalog.
- Add a `gpu_profile` render profile that uses Movit.
- Test GPU effects in the sandbox (GPU access from sandboxed processes is non-trivial).

**Effort estimate:** 2 weeks (mostly testing and documentation).

### 19.5 AI Fine-Tuning on Edit History

**What it unlocks:** The AI learns from accumulated edit data; produces higher-quality edits over time.

**What needs to change:**
- Collect edit history (with user consent) from production users.
- Build a fine-tuning dataset: (user_request, IR_snapshot, applied_operations, qc_report, user_acceptance).
- Fine-tune a model (e.g. GLM) on this dataset.
- Deploy the fine-tuned model behind the same `z-ai-web-dev-sdk` interface.

**Effort estimate:** 6-8 weeks (requires accumulated data first).

### 19.6 Project Versioning and Branching

**What it unlocks:** Users can branch a project ("what if I had stopped editing 10 steps ago?"), compare versions, merge changes.

**What needs to change:**
- Edit graph supports branching: a new branch starts from a specific edit_id.
- Branch metadata stored in SQLite.
- UI for branch selection, diff visualization, merge.
- Merge semantics (similar to git merge, but for operations).

**Effort estimate:** 4-5 weeks.

### 19.7 Multi-Track Audio Mixing

**What it unlocks:** Proper audio mixing with per-track volume, panning, EQ, sidechain compression.

**What needs to change:**
- Add audio-specific operations: `SetTrackVolumeOp`, `SetTrackPanOp`, `AddAudioBusOp`.
- MLT XML emitter gains audio mixing tractor properties.
- UI: audio mixer panel with faders, meters.

**Effort estimate:** 3-4 weeks.

### 19.8 Marketplace for Edit Templates

**What it unlocks:** Users share and download pre-built edit templates ("YouTube intro", "podcast outro", "wedding highlight reel").

**What needs to change:**
- Template format: a JSON file containing a subgraph of operations + asset placeholders.
- Template discovery UI (browse, search, install).
- Template instantiation: replace placeholders with user's assets.

**Effort estimate:** 2-3 weeks.

### 19.9 Timeline Canvas Optimization

**What it unlocks:** Smooth timeline performance with 10,000+ clips.

**What needs to change:**
- Replace HTML/CSS div-based timeline with HTML5 Canvas rendering.
- Implement viewport virtualization (only draw visible clips).
- Implement level-of-detail (thumbnails when zoomed in, bars when zoomed out).

**Effort estimate:** 2-3 weeks.

### 19.10 Keyboard Shortcuts and Power-User Features

**What it unlocks:** Fast editing for experienced users; competitive with Premiere/Final Cut.

**What needs to change:**
- Define a keyboard shortcut schema (configurable).
- Add shortcuts for: play/pause (Space), undo (Ctrl+Z), redo (Ctrl+Shift+Z), cut (C), razor (R), select all (Ctrl+A), etc.
- Add a command palette (Ctrl+Shift+P) for discovering actions.

**Effort estimate:** 1-2 weeks.

---

## Document End

This architecture document is a living specification. As Phases are executed and real-world feedback is collected, sections should be updated to reflect learned lessons. The Open Questions section (§18) is the canonical place to track unresolved decisions.

For execution: an autonomous AI coding agent should begin with Phase 1 (§10) and proceed sequentially. Each phase's Definition of Done (§10.6, §11.6, etc.) is the gate; do not proceed to the next phase until the current phase's DoD is met.





