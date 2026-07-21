# Open Edit — Architecture & Migration Plan

**Status:** Approved design for migration from `pyagent-kdenlive` to an AI-native video editing platform.

**Author:** Senior software architect review & expansion.

**Date:** 2026-07-20.

**Audience:** Autonomous AI coding agents (primary executor); human architect (reviewer).

**Constraints locked in this document:**

| Dimension | Decision |
|---|---|
| Edit model | Hybrid IR — edit graph is source of truth; AI can also write raw MLT XML for one-offs, which is parsed back into IR |
| Deployment | Local desktop app, single user |
| Multi-user | Out of scope for v1, but data model uses stable edit IDs + append-only operation log as cheap insurance |
| Stack | Python core, TypeScript/React frontend, Rust sandbox (Linux-only), Tauri shell, Headless Chromium |
| Executor | Weaker AI coding agent — all phase specs are copy-paste-ready, file-level |
| Deliverable format | Markdown |
| Review scope | Full architecture design and 7-phase migration roadmap |

---

## 1. Executive Summary

This document establishes the architecture for **Open Edit**, a headless, AI-native video editing engine. It separates concerns between **execution-time safety** (isolating AI code and validating output renders) and **edit-history safety** (the ability to undo, redo, reorder, or fine-tune individual edits).

### Core Architectural Separation:
- **Edit Graph**: An append-only transactional log (SQLite) recording discrete, stable operations with UUIDs. This is the source of truth.
- **Timeline State**: A derived projection recomputed on demand by replaying the edit graph. This is what the user views on the timeline.
- **Hybrid Rendering Pipeline**: 
  - **A/B-Roll (MLT)**: Video cuts, speed ramps, transitions, and audio tracks are compiled into standard MLT XML and rendered into a temporary MP4 background file.
  - **Overlays (Chromium/Puppeteer)**: Graphics, typography, animations, lower-thirds, and subtitles are authored as HTML/CSS/JS (utilizing GSAP/Lottie). Headless Chromium renders these layers on top of the background video frame-by-frame using frame-stepping control (`beginFrame` CDP commands), piped to FFmpeg for final compilation.
- **AI Emission Modes**: Three tiers of execution (Structured JSON operations, raw MLT XML ingest fallback, and sandboxed free-form Python scripts).
- **Execution Sandbox + QC Gate**: A Linux-only Rust syscall jail (`seccomp` + `landlock`) to execute scripts safely, and a post-render validation harness.

The migration is divided into **7 concrete engineering phases**, designed to keep the system in a stable, working state at the end of each phase.

---

## 2. Architecture Review

### 2.1 Edit-History Safety vs. Execution-Time Safety
Traditional video editors store the current timeline state directly. If an AI agent modifies this state by writing flat MLT XML, the user cannot easily undo a specific AI edit without losing subsequent modifications, nor can they reorder or fine-tune the parameters of an edit. 

Open Edit solves this by implementing the **Command Pattern** with **Projections**:
- The project file is an database log of operations.
- Undo is implemented by marking an operation as `reverted` and re-generating the timeline state.
- Reorder is implemented by swapping the application order of two operations in the list (validated for commutativity).
- Fine-tune is implemented by superseding a past operation with a new operation containing updated parameters.

### 2.2 Reusability Matrix of `pyagent-kdenlive` Code

| Component | Porting Strategy | Feasibility | Action Plan |
|---|---|---|---|
| **Phase 1: Catalog** | Scraping MLT YAML files | **High** | Re-use YAML parsing logic; discard Kdenlive XML wrappers. |
| **Phase 2: Project Engine** | Timeline math & XML edits | **Medium** | Re-use clip sliding/trimming math; rewrite parser to emit clean MLT XML instead of Kdenlive namespaces. |
| **Phase 3: Core Runner** | CLI subprocess executor | **High** | Keep Python CLI runner; remove D-Bus live sync. |
| **Phase 4: Chat UI** | FastAPI WebSocket server | **High** | Keep Websocket stream; replace Kdenlive reload banner with HTML5 video preview and DOM overlays. |
| **Phase 5: D-Bus Sync** | Process reloading via D-Bus | **None** | Discard entirely. Headless mode replaces this. |
| **Phase 6: Render & QC** | `melt` rendering & ffmpeg checks | **Very High** | Port 1:1; modify render profile parser to work without Kdenlive project XML. |
| **Phase 7: E2E Tests** | Test assertions & CLI | **Medium** | Keep test client; remove `Xvfb` and GUI launch context. |

---

## 3. Data Model & Schema Definitions

### 3.1 Edit Graph Schema (Concrete Pydantic Models)

Every operation appended to the database inherits from a base `Operation` class containing metadata.

```python
# open_edit/ir/types.py

from typing import Literal, Optional, Union, Any
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

class AddHtmlOverlayOp(Operation):
    kind: Literal["add_html_overlay"] = "add_html_overlay"
    template_path: str         # E.g., "templates/lower_third.html"
    variables: dict[str, Any]  # E.g., {"title": "Main Title", "color": "#FF00FF"}
    position_sec: float
    duration_sec: float
    overlay_id: str = Field(default_factory=new_id)

class GroupEditsOp(Operation):
    kind: Literal["group_edits"] = "group_edits"
    edit_ids: list[str]  # child edits
    label: str  # human-readable, e.g. "AI: add intro music"

class RawMltXmlOp(Operation):
    kind: Literal["raw_mlt_xml"] = "raw_mlt_xml"
    xml: str  # the raw MLT XML fragment
    description: str  # what the AI was trying to do

class FreeFormCodeOp(Operation):
    kind: Literal["free_form_code"] = "free_form_code"
    code: str  # Python source

OperationUnion = Union[
    AddClipOp, RemoveClipOp, MoveClipOp, TrimClipOp,
    AddTransitionOp, AddEffectOp, SetKeyframeOp,
    AddHtmlOverlayOp, GroupEditsOp, RawMltXmlOp, FreeFormCodeOp,
]
```

### 3.2 Derived Timeline State Schema

```python
# open_edit/ir/timeline.py

from typing import Literal, Any
from pydantic import BaseModel

class Effect(BaseModel):
    effect_id: str
    effect_type: str
    params: dict
    keyframes: dict[str, list[tuple[float, float, str]]] = {}

class HtmlOverlay(BaseModel):
    overlay_id: str
    template_path: str
    variables: dict[str, Any]
    position_sec: float
    duration_sec: float

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
    tracks: list[Track]
    overlays: list[HtmlOverlay] = []
    duration_sec: float  # computed from clips
```

---

## 4. Operation Application & Command Replay

### 4.1 Applying Operations
Applying an operation to a timeline projects a new state without mutating the previous state.

```python
# open_edit/ir/apply.py

from .types import Operation, AddClipOp, RemoveClipOp, AddHtmlOverlayOp, RawMltXmlOp, FreeFormCodeOp
from .timeline import Timeline, Clip, Track, HtmlOverlay

def apply_operation(timeline: Timeline, op: Operation) -> Timeline:
    if op.status == "reverted":
        return timeline  # Reverted operations are skipped
    
    if isinstance(op, AddClipOp):
        # Locate target track or create one
        track = next((t for t in timeline.tracks if t.track_id == op.track_id), None)
        if not track:
            kind = "audio" if "audio" in op.track_id else "video"
            track = Track(track_id=op.track_id, kind=kind)
            timeline.tracks.append(track)
        
        # Add clip (math helper slides/trims around collisions)
        out_val = op.out_point_sec if op.out_point_sec is not None else 10.0
        new_clip = Clip(
            clip_id=op.clip_id,
            asset_hash=op.asset_hash,
            track_id=op.track_id,
            position_sec=op.position_sec,
            in_point_sec=op.in_point_sec,
            out_point_sec=out_val
        )
        track.clips.append(new_clip)
        track.clips.sort(key=lambda c: c.position_sec)
        
    elif isinstance(op, RemoveClipOp):
        for track in timeline.tracks:
            track.clips = [c for c in track.clips if c.clip_id != op.clip_id]
            
    elif isinstance(op, AddHtmlOverlayOp):
        new_overlay = HtmlOverlay(
            overlay_id=op.overlay_id,
            template_path=op.template_path,
            variables=op.variables,
            position_sec=op.position_sec,
            duration_sec=op.duration_sec
        )
        timeline.overlays.append(new_overlay)
        timeline.overlays.sort(key=lambda o: o.position_sec)
            
    return timeline

def derive_timeline(operations: list[Operation]) -> Timeline:
    timeline = Timeline(tracks=[], duration_sec=0.0)
    # Sort chronologically by timestamp
    sorted_ops = sorted(operations, key=lambda o: o.timestamp)
    for op in sorted_ops:
        timeline = apply_operation(timeline, op)
    
    # Calculate overall duration
    max_duration = 0.0
    for track in timeline.tracks:
        for clip in track.clips:
            max_duration = max(max_duration, clip.position_sec + (clip.out_point_sec - clip.in_point_sec))
    for overlay in timeline.overlays:
        max_duration = max(max_duration, overlay.position_sec + overlay.duration_sec)
    timeline.duration_sec = max_duration
    return timeline
```

### 4.2 Reordering and Fine-Tuning Operations
- **Undo**: Look up the operation by `edit_id` in the database, update its status column to `reverted`, and call `derive_timeline` on the full edit graph.
- **Reorder**: Swapping the order of two operations in the list. Two operations can be swapped if they commute (e.g., adding a clip to track 1 commutes with adding a clip to track 2; adding a filter to clip A does not commute with removing clip A). A commutativity matrix evaluates swaps before committing.
- **Fine-Tune**: To adjust a clip's length, mark the original `AddClipOp` as `superseded` and append a new `AddClipOp` with the same `clip_id` but updated duration/in-point parameters.

---

## 5. Storage & Folder Layout

- **Project Directories**: `~/.open-edit/projects/`
  - Each project has its own folder containing `project.db` (SQLite edit log) and metadata.
- **Content-Addressed Asset Store**: `~/.open-edit/assets/`
  - Original media assets stored by their SHA-256 hash to prevent duplicates (e.g. `~/.open-edit/assets/ab/cdef1234...`).
- **Cache Directories**: `~/.open-edit/cache/`
  - `proxies/`: Low-resolution proxy videos for canvas rendering.
  - `renders/`: Full timeline previews rendered via `melt`, keyed by the SHA-256 hash of the project's edit graph JSON representation. If the edit graph is unchanged, the cache hit immediately returns the rendered preview path.
  - `thumbs/`: Extracted thumbnails for timeline visualization.

---

## 6. Detailed 7-Phase Migration Roadmap

```
Phase 1: IR & SQLite Store ──► Phase 2: MLT Emitter/Ingest ──► Phase 3: Rust Sandbox
                                                                      │
Phase 6: Asset/QC Migration ◄── Phase 5: Tauri UI & Video player ◄── Phase 4: Agent loop
           │
           ▼
Phase 7: Scenario Eval & CI
```

---

### Phase 1: IR Runtime & SQLite Store
- **Objective**: Establish the Python data structures for operations, the project state compiler, and the SQLite history log.

#### Tasks:
1. Create `open_edit/ir/types.py` implementing all `Operation` Pydantic models (including basic and HTML overlays) and the derived `Timeline` structure.
2. Create `open_edit/storage/edit_graph.py` managing SQLite tables. Create schema:
   ```sql
   CREATE TABLE edits (
       edit_id TEXT PRIMARY KEY,
       parent_id TEXT,
       kind TEXT NOT NULL,
       author TEXT NOT NULL,
       timestamp TEXT NOT NULL,
       status TEXT NOT NULL CHECK (status IN ('applied', 'reverted', 'superseded')),
       payload TEXT NOT NULL
   );
   ```
3. Implement `append_operation(project_id: str, op: Operation)` and `get_project_operations(project_id: str) -> list[Operation]`.
4. Implement `open_edit/ir/apply.py` containing the `derive_timeline` logic.

#### Acceptance Criteria:
- Unit tests in `tests/test_ir.py` must assert:
  - Appending operations to SQLite works.
  - Deleting/reverting operations correctly marks them `reverted` in the database.
  - Replaying 10+ sequential operations returns the correct, expected `Timeline` state.

---

### Phase 2: MLT XML Emitter & Strict Ingest Parser
- **Objective**: Translate derived `Timeline` state to standard MLT XML, and implement the strict XML parser to ingest raw XML blocks back into IR operations.

#### Tasks:
1. Create `open_edit/render/emitter.py` using `lxml.etree` to build standard MLT XML documents containing a single `<profile>`, `<tractor>` wrapping a `<multitrack>` of `<playlist>` tracks, and `<entry>` clips.
2. Implement the XML parser `open_edit/render/ingest.py`. It must recursively parse `<entry>` and `<filter>` tags, mapping them to standard `AddClipOp` and `AddEffectOp` schemas.
3. Configure the parser to be strict: if it encounters unknown tags, keyframes containing custom curve characters (like Kdenlive's smooth `~` interpolation), or unsupported nesting layouts, it must immediately raise a `ValidationError`.

#### Acceptance Criteria:
- Tests in `tests/test_render.py` must assert:
  - Emitted XML compiles without warnings under the `melt` validation command:
    ```bash
    melt -consumer xml:validate.xml /tmp/test_project.mlt
    ```
  - The strict parser correctly accepts standard XML tracks, and successfully raises a validation error when encountering Kdenlive-specific formatting properties.

---

### Phase 3: Rust Sandbox Environment (Linux-Only)
- **Objective**: Implement the execution sandbox for free-form Python scripts using a Rust wrapper utilizing Linux-specific security layers.

#### Tasks:
1. Create `sandbox/Cargo.toml` and `sandbox/src/main.rs`.
2. Configure `sandbox/src/jail.rs` to restrict file access via `landlock`:
   - Read-only access to `/usr/` (python/system libs) and the global Asset Store `~/.open-edit/assets/`.
   - Read-write access restricted strictly to the project's temporary directory.
   - Network socket creation blocked completely.
3. Configure `sandbox/src/allowlist.rs` using `seccomp-sys` to block execution of any system binaries unless explicitly allowlisted (`melt`, `ffmpeg`, `ffprobe`).
4. Support CLI arguments:
   ```bash
   open-edit-sandbox --code /tmp/script.py --workdir /tmp/project_dir --timeout 30 --mem 512M
   ```

#### Acceptance Criteria:
- Rust sandbox compilation must succeed.
- Tests in `sandbox/tests/test_jail.rs` must assert:
  - Python scripts attempting to read `/etc/passwd` or write outside the workdir are blocked.
  - Python scripts attempting to resolve internet hosts (`socket.connect`) are blocked.
  - Running a safe script that prints clip info completes successfully.

---

### Phase 4: AI Agent Loop (Python Core)
- **Objective**: Implement the core agent loop using the `z-ai-web-dev-sdk` to process user messages, manage the conversation prompt, and parse the three emission modes.

#### Tasks:
1. Create `open_edit/agent/loop.py`.
2. Create prompt templates in `open_edit/agent/prompt.py` detailing:
   - The available operations schema (JSON).
   - The current `Timeline` state representation.
   - Instructions on choosing between Structured JSON (preferred), Raw XML (escape hatch), and Python scripts (free-form).
3. Implement `open_edit/agent/retry.py`. If the model's output fails Pydantic validation or sandbox execution crashes, capture the exception traceback, format it as a `fix: <error>` message, and query the model again (max 3 attempts).

#### Acceptance Criteria:
- Unit tests in `tests/test_agent.py` using mocked SDK calls must assert:
  - Correct formatting of the system prompt.
  - Successful retry loop execution when the model outputs a validation-failing JSON.

---

### Phase 5: Tauri Desktop Shell & React UI
- **Objective**: Build the visual client application and the WebSocket server to stream real-time events.

#### Tasks:
1. Initialize Tauri in `desktop/` and the React frontend in `frontend/`.
2. Implement WebSocket route in FastAPI backend `open_edit/api/chat.py` communicating:
   - Chat message streams.
   - Timeline update payloads (`Timeline` state sent as JSON).
   - Rendering state changes and QC flags.
3. Build React panels:
   - **Chat Panel**: Displays text bubbles and QC check badges.
   - **Timeline Panel**: Draws clips, tracks, and selection handles on an HTML5 canvas. Highlights edited clips with a glowing outline.
   - **Edit History Panel**: A list of operations displaying authors and status. Adds buttons for one-click Undo/Redo.
   - **Preview Panel**: Embeds a standard HTML5 `<video>` player playing proxy renders from the FastAPI static mount `/static/renders/` with CSS/DOM overlays rendering lower-thirds and templates in real-time.

#### Acceptance Criteria:
- Running `npm run tauri dev` must compile and open the desktop GUI.
- Dragging a clip on the canvas timeline must send the `move_clip` operation via the WebSocket, trigger a database save, and redraw the canvas.

---

### Phase 6: Migration & Asset Import
- **Objective**: Port the asset management pipelines, proxy generation, and render QC checks from `pyagent-kdenlive`.

#### Tasks:
1. Port asset store logic to `open_edit/storage/assets.py`. Calculate the SHA-256 of imported videos, copy them to content-addressed directories, and invoke `ffprobe` to extract frame rates, durations, and channels.
2. Port proxy generation. Run `ffmpeg` in the background to render a low-resolution (640x360) progressive MP4 file for every imported asset.
3. Port Phase 6 QC tools to `open_edit/qc/gate.py`. After any rendering task finishes, run the `blackdetect` and `silencedetect` filters on the output MP4 and output a `QCReport` JSON. Also trigger Puppeteer headless browser rendering loop to overlay graphics onto the generated video.

#### Acceptance Criteria:
- Import a video file and verify that the original is stored by hash, a 360p proxy file is successfully generated, and metadata is populated.
- Render a timeline containing a silent gap and verify that the QC gate flag detects the silence correctly.

---

### Phase 7: Optimization & Hardening
- **Objective**: Develop the scenario-based accuracy evaluation suite, optimize caching, and prepare CI/CD pipelines.

#### Tasks:
1. Create `tests/eval_scenarios.py`. Implement 20+ editing scenarios (e.g. "trim clip A to 5s, slide clip B to 10s, and add crossfade").
2. Set up the evaluation metrics: run the agent against these scenarios 5 times. If the success rate is <80% (i.e. the final derived timeline state does not match the target state), log the validation errors and block merges.
3. Optimize the render cache: ensure that identical edit graph states result in cache hits, skipping calls to the `melt` binary.

#### Acceptance Criteria:
- Running `python3 tests/eval_scenarios.py` executes all scenarios and generates an accuracy report on stdout.
- CI pipelines execute Phase 2, Phase 3, and Phase 6 tests successfully.
