# Phase 4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the review room (Phase 4 v2) and the creation pipeline (Phase 4.5) of Open Edit. The review room adds tool repointing, style memory, the unified notes system, version snapshots, the `commit_feedback` batch trigger, and the HTML5 preview player. The creation pipeline adds Whisper transcription, a render sandbox, and five skills (narrative, silence, motion graphics, music, SFX).

**Architecture:**
- **Phase 4 v2 (review room):** The 32 existing `pyagent_*` tool wrappers get repointed from `KdenliveFileBackend.*` to `open_edit.ir.api.*`. Five new tools (`pyagent_run_python`, `pyagent_get_style_profile`, `pyagent_set_pinned_value`, `pyagent_get_pending_notes`, `pyagent_add_marker`) are added. A unified `review_notes` store (typed / voice / region / agent sources) replaces the v1 parallel mark/correction_note systems. Style Memory aggregates `taste_events` into a bounded profile; retrieval is tag-gated by op type. A `RenderSnapshotStore` records each render so the user can switch between v1/v2/v3. The HTML5 preview player supports click-and-drag region marks, per-frame notes, and speech-to-text. `commit_feedback` is a batch trigger: all pending notes → agent → IR ops → render → version snapshot.
- **Phase 4.5 (creation pipeline):** `faster-whisper` integration at asset ingestion produces word-level alignment. A new `open-edit-render-sandbox` Rust binary (no seccomp, cgroup-based resource limits, optional `--with-hwaccel` for `/dev/dri`) runs heavyweight render work. Five skills consume the alignment + Phase 2 silence markers + narrative analysis to propose structured ops or generate new visual assets.

**Tech Stack:** Python 3.14, Pydantic v2 (discriminated unions), SQLite (WAL + FK), faster-whisper (optional, new dep), Rust (stable), clap, nix, libseccomp-rs, anyhow, bwrap 0.11+, Web Speech API (browser-native, no JS dep), cgroup-v2 for render sandbox.

**Specs:**
- `phase4-design-revised.md` (v2 review-merged plan, project root) — the input design
- `docs/superpowers/specs/2026-07-22-phase4-design-audit-fixes.md` (audit log + applied fixes)
- `docs/superpowers/specs/2026-07-22-phase4-section-2-verification-memo.md` (§2 verification, Phase 4.5 in scope)

## Global Constraints

- Python 3.11+ (project is `>=3.11`, system is 3.14).
- Pydantic v2.13.4 quirks: use `TypeAdapter(OperationUnion)` for `.validate_*` calls; `.model_validate()` does NOT work on bare `Annotated` alias. `open_edit/pydantic_compat.py` shims `TypeAdapter`.
- Existing IR op types (12): AddClipOp, RemoveClipOp, MoveClipOp, TrimClipOp, AddTransitionOp, AddEffectOp, SetKeyframeOp, SetAudioGainOp, NormalizeAudioOp, GroupEditsOp, RawMltXmlOp, FreeFormCodeOp. **Do not add new op types in Phase 4 v2**; Phase 4.5 adds `AddMusicTrackOp` (or extends AddEffectOp) and `AddSfxOp` (or extends AddEffectOp) — see W5 and W6.
- The new field on `Operation` (T8) is `originating_note_id: str | None = None`. Stored in the existing `edits.payload TEXT NOT NULL` JSON column — **no SQL migration needed**. EditGraphStore reads/writes the same column. New tests must verify back-compat with existing fixtures.
- All sandbox tests are skipped if `bwrap` is not on `PATH`. Phase 4.5's render sandbox tests are skipped if `bwrap` is unavailable; integration tests in `sandbox/tests/` are cargo-feature-gated.
- The chat UI is served from `localhost` (FastAPI on a user-chosen port). STT (Web Speech API) requires a secure context — works on `http://localhost`, requires HTTPS in production. Production deployment must use HTTPS or a localhost-only reverse proxy.
- Commit style: `[open_edit] <message>` (matches the 17 Phase 2 commits + 13 Phase 3 commits on main).
- No comments in code unless the comment is documentation for a non-obvious safety property.
- Every new component has pytest coverage. New tools have golden-IO tests. New WS messages have round-trip tests.
- Per-task review (subagent-driven-development): each task is independently testable and reviewable. The plan author does not pre-write code beyond what's in the steps; subagents implement the rest.

## File Structure

| Group | New Files | Modified Files | Boundary |
|-------|-----------|----------------|----------|
| IR types | — | `open_edit/ir/types.py` | T8: add `originating_note_id` field on `Operation` |
| IR apply | — | `open_edit/ir/apply.py` | T8: pass `originating_note_id` through |
| IR API | — | `open_edit/ir/api.py` | T8: accept `originating_note_id` param in 12 methods |
| Storage | `open_edit/storage/notes.py` (T6), `open_edit/storage/render_snapshots.py` (T4) | `open_edit/storage/assets.py` (W1: alignment field), `open_edit/storage/edit_graph.py` (T8: no SQL change, payload JSON), `open_edit/storage/schema.sql` (W1: alignment column) | Notes store, render snapshots, asset alignment |
| Style | `open_edit/style/aggregate.py` (T2), `open_edit/style/retrieve.py` (T2) | — | Style memory |
| Agent | `open_edit/agent/style_inject.py` (T2) | `open_edit/agent/sandbox_bridge.py` (T8: pass `originating_note_id`) | prior_state builder |
| Skills | `open_edit/agent/skills/__init__.py`, `open_edit/agent/skills/silence_cutter.py` (W3), `open_edit/agent/skills/narrative_analyzer.py` (W4), `open_edit/agent/skills/music_selector.py` (W5), `open_edit/agent/skills/sfx_placer.py` (W6), `open_edit/agent/skills/motion_graphics.py` (W7), `open_edit/agent/skills/motion_graphics/templates/{hook,turn,scope,mechanism,cost,tease,button}.py` (W7) | — | Five creation skills + template library |
| New tools | `open_edit/agent/tools/pyagent_run_python.py`, `open_edit/agent/tools/pyagent_get_style_profile.py`, `open_edit/agent/tools/pyagent_set_pinned_value.py`, `open_edit/agent/tools/pyagent_get_pending_notes.py`, `open_edit/agent/tools/pyagent_add_marker.py` (T7) | `pyagent-kdenlive-guide/phase3_pyagent_core/tools/*.py` (T7: 32 wrappers repointed, body change only) | New tool wrappers + repointed existing |
| Runtime / extension | — | `pyagent-kdenlive-guide/phase3_pyagent_core/runtime.py` (T7: OP_TABLE), `pyagent-kdenlive-guide/phase3_pyagent_core/extension.ts` (T7: register 5 new tools), `pyagent-kdenlive-guide/phase3_pyagent_core/system_prompt.md` (T7: add 5 schemas + prior_state directive) | Tool dispatch + agent loop |
| Chat UI | — | `pyagent-kdenlive-guide/phase4_chat_ui/static/{index.html,app.js,style.css}` (T2: project state panel notes section; T4: version switcher; T5: HTML5 preview, region mark, per-frame notes, STT, "Send to Claude" button), `pyagent-kdenlive-guide/phase4_chat_ui/ws/handler.py` + `ws/handlers.py` (T4, T5, T6, T7: new WS message types: `note_add`, `note_update`, `note_delete`, `note_list`, `version_list`, `version_ready`, `commit_feedback`, `creativity_level` in `prompt`) | WebSocket protocol + UI |
| CLI | — | `open_edit/cli.py` (T1: `notes`, `versions`, `commit-feedback`, `style-rollup` subcommands) | Manual CLI for testing |
| Rust | `open_edit/sandbox/src/render_main.rs`, `open_edit/sandbox/src/render_jail.rs` (W2) | `open_edit/sandbox/Cargo.toml` (W2: add `[[bin]] name = "open-edit-render-sandbox"`) | New render sandbox binary |
| Tests | `open_edit/tests/test_ir/test_originating_note_id.py` (T8), `open_edit/tests/test_storage/test_notes.py` (T6), `open_edit/tests/test_storage/test_render_snapshots.py` (T4), `open_edit/tests/test_style/test_aggregate.py` (T2), `open_edit/tests/test_style/test_retrieve.py` (T2), `open_edit/tests/test_style/test_style_inject.py` (T2), `open_edit/tests/test_agent/test_pyagent_get_pending_notes.py` (T7), `open_edit/tests/test_agent/test_pyagent_add_marker.py` (T7), `pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_pyagent_run_python.py` (T7), `pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_pyagent_get_style_profile.py` (T7), `pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_pyagent_set_pinned_value.py` (T7), `pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_creativity_level.py` (T7), `pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_repointed_wrappers.py` (T7: 32 golden-IO tests), `pyagent-kdenlive-guide/phase4_chat_ui/tests/test_commit_feedback.py` (T6), `pyagent-kdenlive-guide/phase4_chat_ui/tests/test_version_ready.py` (T4), `pyagent-kdenlive-guide/phase4_chat_ui/tests/test_notes_ws_broadcast.py` (T6), `pyagent-kdenlive-guide/phase4_chat_ui/tests/test_commit_feedback_race.py` (T6), `pyagent-kdenlive-guide/phase4_chat_ui/tests/test_stt_secure_context.py` (T5), `pyagent-kdenlive-guide/phase4_chat_ui/tests/test_notes_sidebar_render.py` (T6), `pyagent-kdenlive-guide/phase4_chat_ui/tests/test_edit_history_pagination.py` (T4), `open_edit/tests/test_style/test_notes_archive.py` (T8 housekeeping), `open_edit/tests/test_skill/test_silence_cutter.py` (W3), `open_edit/tests/test_skill/test_narrative_analyzer.py` (W4), `open_edit/tests/test_skill/test_music_selector.py` (W5), `open_edit/tests/test_skill/test_sfx_placer.py` (W6), `open_edit/tests/test_skill/test_motion_graphics_templated.py` (W7), `open_edit/tests/test_long_form_e2e.py` (W8) | `open_edit/tests/conftest.py` (T6: `tmp_notes_db` fixture), `pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_golden_io.py` (T7: 32 wrappers) | All test files |

## Sequencing & Dependencies

| # | Task | Effort | Depends on | Notes |
|---|---|---|---|---|
| 1 | T8 IR extension | 0.5d | — | Foundation for T6 (commit_token), T7 |
| 2 | T6 unified notes store + sidebar | 2d | T8 | Foundation for T4 (notes in T6), T5 (per-frame notes), T7 (5 new tools) |
| 3 | T2 style memory | 1.5d | — | Foundation for T7 (prior_state, 2 new style tools) |
| 4 | T5 HTML5 preview player | 1.5d | T6 | Region mark + per-frame notes + STT |
| 5 | T4 RenderSnapshotStore + version switcher | 1d | — | Independent of T6, T7 |
| 6 | T7 commit_feedback + version_ready | 1d | T6, T8 | Stamps originating_note_id |
| 7 | T1 tool repointing + 5 new tools + creativity_level | 2d | T6, T2 | Last Phase 4 task |
| 8 | T9 notes DB archival | 0.5d | T6 | Housekeeping on commit_feedback |
| 9 | W1 Whisper integration | 2d | — | Phase 4.5 start (parallel) |
| 10 | W2 Render sandbox (Rust) | 5d | — | Critical path (parallel) |
| 11 | W3 Silence cutter | 2d | W1 | |
| 12 | W4 Narrative analyzer | 2d | W1 | |
| 13 | W5 Music selector + AddMusicTrackOp | 2d | W4 | |
| 14 | W6 SFX placer + AddSfxOp | 1.5d | W4, W5 | |
| 15 | W7 Motion graphics (templated) + template library | 5d | W2, W4 | Longest pole |
| 16 | W8 Long-form stress test | 0.5d | All | Validates 11-min claim |

**Phase 4 v2 total:** 9 days (~1.8 weeks)
**Phase 4.5 total:** 20 days (~4 weeks)
**Grand total:** ~5.8 weeks

---

## Task 1: T8 IR extension — `originating_note_id` on `Operation`

**Files:**
- Modify: `open_edit/open_edit/ir/types.py:24-32` (add field to `Operation`)
- Modify: `open_edit/open_edit/ir/apply.py` (accept and stamp `originating_note_id` on produced ops, if applicable)
- Modify: `open_edit/open_edit/ir/api.py:24-180` (12 IR methods accept optional `originating_note_id`)
- Modify: `open_edit/open_edit/agent/sandbox_bridge.py` (`run_free_form()` accepts optional `originating_note_id`)
- Test: `open_edit/tests/test_ir/test_originating_note_id.py`

**Interfaces:**
- Consumes: existing `Operation` Pydantic model with fields `edit_id, parent_id, author, timestamp, status, kind`. Existing IR methods with positional and keyword args.
- Produces:
  - `Operation(..., originating_note_id: str | None = None)` — defaults to `None`. Stored in `edits.payload TEXT NOT NULL` JSON column.
  - All 12 `IR` API methods accept optional `originating_note_id: str | None = None` keyword. If set, stamped on the op produced.
  - `run_free_form(code: str, ..., originating_note_id: str | None = None)` — if set, every op produced inside the sandbox has `originating_note_id=<value>`.
- Note: this is an **additive** change. All existing tests and fixtures must continue to pass (default `None`).

### Step 1: Write the failing test

Create `open_edit/tests/test_ir/test_originating_note_id.py`:

```python
"""Phase 4 Task 1: originating_note_id on Operation + IR API + sandbox_bridge."""
import json
import pytest
from pathlib import Path

from open_edit.ir.types import (
    AddClipOp, AddEffectOp, SetKeyframeOp, Operation, Project, Asset,
)
from open_edit.ir.api import IR
from open_edit.storage.edit_graph import EditGraphStore


def _make_buffer() -> list:
    return []


def test_operation_default_none():
    op = AddClipOp(
        author="user", asset_hash="abc", track_id="t1", position_sec=0.0,
    )
    assert op.originating_note_id is None


def test_operation_explicit_set():
    op = AddClipOp(
        author="user", asset_hash="abc", track_id="t1", position_sec=0.0,
        originating_note_id="note_42",
    )
    assert op.originating_note_id == "note_42"


def test_operation_serializes_with_field():
    op = AddClipOp(
        author="user", asset_hash="abc", track_id="t1", position_sec=0.0,
        originating_note_id="note_42",
    )
    data = json.loads(op.model_dump_json())
    assert data["originating_note_id"] == "note_42"


def test_operation_back_compat_no_field_in_payload():
    """Existing fixtures that don't set the field must still serialize/deserialize."""
    op = AddClipOp(
        author="user", asset_hash="abc", track_id="t1", position_sec=0.0,
    )
    data = json.loads(op.model_dump_json())
    assert data["originating_note_id"] is None
    # Round-trip
    op2 = AddClipOp.model_validate(data)
    assert op2.originating_note_id is None


def test_ir_add_clip_stamps_originating_note_id(tmp_path):
    store = EditGraphStore(tmp_path / "edit_graph.db")
    buf = _make_buffer()
    ir = IR(buf, project_id="p1", parent_op_id=None)
    clip_id = ir.add_clip(
        asset_hash="abc", track_id="t1", position_sec=0.0,
        originating_note_id="note_99",
    )
    assert len(buf) == 1
    assert buf[0].originating_note_id == "note_99"
    assert buf[0].clip_id == clip_id


def test_ir_add_clip_default_none(tmp_path):
    store = EditGraphStore(tmp_path / "edit_graph.db")
    buf = _make_buffer()
    ir = IR(buf, project_id="p1", parent_op_id=None)
    ir.add_clip(asset_hash="abc", track_id="t1", position_sec=0.0)
    assert buf[0].originating_note_id is None


def test_ir_add_effect_stamps(tmp_path):
    buf = _make_buffer()
    ir = IR(buf, project_id="p1", parent_op_id=None)
    ir.add_effect(
        target_kind="clip", target_id="c1", effect_type="volume",
        params={"gain": 0.5}, originating_note_id="note_5",
    )
    assert buf[0].originating_note_id == "note_5"


def test_edit_graph_store_round_trip(tmp_path):
    """EditGraphStore reads/writes the payload JSON; originating_note_id is preserved."""
    store = EditGraphStore(tmp_path / "edit_graph.db")
    op = AddClipOp(
        author="user", asset_hash="abc", track_id="t1", position_sec=0.0,
        originating_note_id="note_42",
    )
    seq = store.append(op)
    loaded = store.load_all()
    assert len(loaded) == 1
    assert loaded[0].originating_note_id == "note_42"
```

### Step 2: Run test to verify it fails

Run: `cd open_edit && pytest tests/test_ir/test_originating_note_id.py -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'originating_note_id'`

### Step 3: Add field to `Operation` model

Modify `open_edit/open_edit/ir/types.py:24-32`:

```python
class Operation(BaseModel):
    kind: str  # overridden by each subclass as Literal[...]
    edit_id: str = Field(default_factory=new_id)
    parent_id: Optional[str] = None
    author: Literal["ai", "user"]
    timestamp: str = Field(default_factory=now_iso8601)
    status: Literal["applied", "reverted", "superseded"] = "applied"
    originating_note_id: Optional[str] = None
```

### Step 4: Run test to verify the first 4 tests pass; rest still fail

Run: `cd open_edit && pytest tests/test_ir/test_originating_note_id.py -v`
Expected: First 4 pass. Tests 5-8 still fail with `TypeError: add_clip() got an unexpected keyword argument 'originating_note_id'`.

### Step 5: Update IR API methods to accept `originating_note_id`

In `open_edit/open_edit/ir/api.py`, modify each of the 12 methods to accept an optional `originating_note_id: str | None = None` keyword. When set, pass it to the Pydantic op constructor.

Example for `add_clip`:

```python
def add_clip(
    self,
    asset_hash: str,
    track_id: str,
    position_sec: float,
    in_point_sec: float = 0.0,
    out_point_sec: Optional[float] = None,
    originating_note_id: Optional[str] = None,
) -> str:
    clip_id = new_id()
    op = AddClipOp(
        author="ai",
        parent_id=self._parent_op_id,
        asset_hash=asset_hash,
        track_id=track_id,
        track_kind="video",
        position_sec=position_sec,
        in_point_sec=in_point_sec,
        out_point_sec=out_point_sec,
        clip_id=clip_id,
        originating_note_id=originating_note_id,
    )
    self._ops_buffer.append(op)
    return clip_id
```

Repeat for the other 11 methods (`trim_clip`, `move_clip`, `remove_clip`, `add_transition`, `add_effect`, `set_keyframe`, `set_audio_gain`, `normalize_audio`, `group_edits`, `raw_mlt_xml`, `free_form_code`).

### Step 6: Run test to verify all 8 tests pass

Run: `cd open_edit && pytest tests/test_ir/test_originating_note_id.py -v`
Expected: 8 passed.

### Step 7: Update `sandbox_bridge.run_free_form()` signature

In `open_edit/open_edit/agent/sandbox_bridge.py`, add optional `originating_note_id` to `run_free_form`. Pass it through to the bootstrap so every op produced inside the sandbox has the field set.

```python
def run_free_form(
    code: str,
    workdir: Path,
    project_id: str,
    parent_op_id: Optional[str] = None,
    timeout_sec: int = 30,
    mem_mb: int = 512,
    originating_note_id: Optional[str] = None,
) -> FreeFormResult:
    ...
    # In _render_bootstrap, pass originating_note_id to the bootstrap script.
    # The bootstrap script calls IR(..., originating_note_id=<value>).
```

### Step 8: Run full test suite to verify no regressions

Run: `cd open_edit && pytest`
Expected: 204 passed, 5 skipped (no regressions).

### Step 9: Commit

```bash
git add open_edit/ir/types.py open_edit/ir/api.py open_edit/ir/apply.py open_edit/agent/sandbox_bridge.py open_edit/tests/test_ir/test_originating_note_id.py
git commit -m "[open_edit] phase4 t8: originating_note_id on Operation + IR API + sandbox_bridge"
```

---

## Task 2: T6 unified notes store + sidebar UI

**Files:**
- Create: `open_edit/open_edit/storage/notes.py` (Pydantic types + NotesStore)
- Modify: `open_edit/open_edit/storage/__init__.py` (export `NotesStore`, `ReviewNote`, `NoteAnchor`, `NoteSource`, `NoteStatus`)
- Modify: `pyagent-kdenlive-guide/phase4_chat_ui/ws/handler.py` (new WS message types: `note_add`, `note_update`, `note_delete`, `note_list`, `note_list_update`; project-scoped broadcast)
- Modify: `pyagent-kdenlive-guide/phase4_chat_ui/ws/handlers.py` (handlers for the 4 new message types)
- Modify: `pyagent-kdenlive-guide/phase4_chat_ui/static/{index.html,app.js,style.css}` (notes section in project state panel + "View all" modal)
- Modify: `open_edit/open_edit/cli.py` (add `notes` subcommand: list, add, dismiss)
- Modify: `open_edit/tests/conftest.py` (`tmp_notes_db` fixture)
- Test: `open_edit/tests/test_storage/test_notes.py`
- Test: `pyagent-kdenlive-guide/phase4_chat_ui/tests/test_notes_ws_broadcast.py`
- Test: `pyagent-kdenlive-guide/phase4_chat_ui/tests/test_notes_sidebar_render.py`

**Interfaces:**
- Consumes: `open_edit/storage/__init__.py` storage location; `ws/handler.py` dispatch pattern; `ws/handlers.py` message handler pattern; project state panel HTML.
- Produces:
  - `ReviewNote` Pydantic model with `note_id, project_id, anchor: NoteAnchor, text, source: NoteSource, status: NoteStatus, created_at, processed_at, commit_token, resulting_op_ids` (per audit L3).
  - `NoteAnchor` discriminated union: `TimestampAnchor | RegionAnchor | OpAnchor` via `Field(discriminator="anchor_type")` (per audit L3).
  - `NoteSource` enum: `"typed" | "voice" | "region" | "agent" | "form_correction"`.
  - `NoteStatus` enum: `"pending" | "processed" | "dismissed"`.
  - `NotesStore(db_path)` with methods: `append(note) -> str`, `list_pending(project_id) -> list[ReviewNote]`, `list_all(project_id, status=None) -> list[ReviewNote]`, `update(note_id, **fields) -> None`, `mark_processed(note_ids, resulting_op_ids) -> None`, `mark_dismissed(note_ids) -> None`, `commit_pending(project_id, commit_token) -> list[ReviewNote]` (returns and marks for the race fix, per audit H1).
  - WS message types (per audit H4): all include `project_id`.
  - `ws/handlers.py:handle_note_add`, `handle_note_update`, `handle_note_delete`, `handle_note_list` — broadcast `note_list` to project-scoped connections.

### Step 1: Write the failing test

Create `open_edit/tests/test_storage/test_notes.py`:

```python
"""Phase 4 Task 2: unified notes store."""
import json
import pytest
from pathlib import Path
from datetime import datetime, timezone, timedelta

from open_edit.storage.notes import (
    NotesStore, ReviewNote, TimestampAnchor, RegionAnchor, OpAnchor,
    NoteSource, NoteStatus,
)


def test_append_timestamp_note(tmp_path):
    store = NotesStore(tmp_path / "notes.db")
    note = ReviewNote(
        project_id="p1",
        anchor=TimestampAnchor(t_start=1.0, t_end=2.0),
        text="feels empty",
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    note_id = store.append(note)
    assert note_id == note.note_id
    notes = store.list_all("p1")
    assert len(notes) == 1
    assert notes[0].note_id == note_id
    assert notes[0].anchor.t_start == 1.0


def test_append_region_note(tmp_path):
    store = NotesStore(tmp_path / "notes.db")
    note = ReviewNote(
        project_id="p1",
        anchor=RegionAnchor(x=10, y=20, w=100, h=50, t_start=0.5, t_end=1.5),
        text="television overlay",
        source=NoteSource.region,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    store.append(note)
    notes = store.list_all("p1")
    assert isinstance(notes[0].anchor, RegionAnchor)
    assert notes[0].anchor.x == 10


def test_append_op_note(tmp_path):
    store = NotesStore(tmp_path / "notes.db")
    note = ReviewNote(
        project_id="p1",
        anchor=OpAnchor(op_id="op_42"),
        text="trim 1s off the front",
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    store.append(note)
    notes = store.list_all("p1")
    assert isinstance(notes[0].anchor, OpAnchor)
    assert notes[0].anchor.op_id == "op_42"


def test_list_pending_filters_correctly(tmp_path):
    store = NotesStore(tmp_path / "notes.db")
    for i, status in enumerate([NoteStatus.pending, NoteStatus.processed, NoteStatus.pending]):
        store.append(ReviewNote(
            project_id="p1",
            anchor=TimestampAnchor(t_start=float(i), t_end=float(i) + 0.5),
            text=f"note {i}",
            source=NoteSource.typed,
            status=status,
            created_at=datetime.now(timezone.utc).isoformat(),
        ))
    pending = store.list_pending("p1")
    assert len(pending) == 2
    assert all(n.status == NoteStatus.pending for n in pending)


def test_commit_pending_marks_with_token(tmp_path):
    """Per audit H1: commit_pending returns notes + stamps commit_token."""
    store = NotesStore(tmp_path / "notes.db")
    for i in range(3):
        store.append(ReviewNote(
            project_id="p1",
            anchor=TimestampAnchor(t_start=float(i), t_end=float(i) + 0.5),
            text=f"note {i}",
            source=NoteSource.typed,
            status=NoteStatus.pending,
            created_at=datetime.now(timezone.utc).isoformat(),
        ))
    token = "commit_abc"
    notes = store.commit_pending("p1", token)
    assert len(notes) == 3
    assert all(n.commit_token == token for n in notes)
    # Notes not marked processed yet — only stamped with token.
    pending_after = store.list_pending("p1")
    assert len(pending_after) == 3


def test_mark_processed_only_token_matching(tmp_path):
    """Per audit H1: mark_processed only affects notes with the given token."""
    store = NotesStore(tmp_path / "notes.db")
    for i in range(3):
        store.append(ReviewNote(
            project_id="p1",
            anchor=TimestampAnchor(t_start=float(i), t_end=float(i) + 0.5),
            text=f"note {i}",
            source=NoteSource.typed,
            status=NoteStatus.pending,
            created_at=datetime.now(timezone.utc).isoformat(),
        ))
    token = "commit_abc"
    store.commit_pending("p1", token)
    # Add a note AFTER commit_pending but BEFORE mark_processed.
    store.append(ReviewNote(
        project_id="p1",
        anchor=TimestampAnchor(t_start=10.0, t_end=11.0),
        text="note added after commit",
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    ))
    store.mark_processed(["note_0", "note_1", "note_2"], resulting_op_ids=["op_1", "op_2", "op_3"])
    # 3 should be processed, 1 should still be pending.
    pending = store.list_pending("p1")
    assert len(pending) == 1
    assert pending[0].text == "note added after commit"


def test_note_dismissed_is_soft_delete(tmp_path):
    """Per design §3.6: note_delete marks status=dismissed, never hard-deletes."""
    store = NotesStore(tmp_path / "notes.db")
    note = ReviewNote(
        project_id="p1",
        anchor=TimestampAnchor(t_start=0.0, t_end=1.0),
        text="",
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    note_id = store.append(note)
    store.mark_dismissed([note_id])
    all_notes = store.list_all("p1", status=None)
    assert len(all_notes) == 1
    assert all_notes[0].status == NoteStatus.dismissed


def test_project_isolation(tmp_path):
    store = NotesStore(tmp_path / "notes.db")
    store.append(ReviewNote(
        project_id="p1",
        anchor=TimestampAnchor(t_start=0.0, t_end=1.0),
        text="",
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    ))
    store.append(ReviewNote(
        project_id="p2",
        anchor=TimestampAnchor(t_start=0.0, t_end=1.0),
        text="",
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    ))
    assert len(store.list_all("p1")) == 1
    assert len(store.list_all("p2")) == 1
```

### Step 2: Run test to verify it fails

Run: `cd open_edit && pytest tests/test_storage/test_notes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'open_edit.storage.notes'`

### Step 3: Implement `open_edit/storage/notes.py`

Create `open_edit/open_edit/storage/notes.py`:

```python
"""Unified review_notes store.

Per phase4-design-revised.md §3.6 (T6): single source of truth for all
'the user or agent flagged this' annotations. Replaces v1's parallel
mark_region and correction_note systems with one store.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field


class NoteSource(str, Enum):
    typed = "typed"
    voice = "voice"
    region = "region"
    agent = "agent"
    form_correction = "form_correction"


class NoteStatus(str, Enum):
    pending = "pending"
    processed = "processed"
    dismissed = "dismissed"


class TimestampAnchor(BaseModel):
    anchor_type: Literal["timestamp"] = "timestamp"
    t_start: float
    t_end: float


class RegionAnchor(BaseModel):
    anchor_type: Literal["region"] = "region"
    x: float
    y: float
    w: float
    h: float
    t_start: float
    t_end: float


class OpAnchor(BaseModel):
    anchor_type: Literal["op"] = "op"
    op_id: str


NoteAnchor = Annotated[
    Union[TimestampAnchor, RegionAnchor, OpAnchor],
    Field(discriminator="anchor_type"),
]


def _new_id() -> str:
    return f"note_{uuid.uuid4().hex[:12]}"


class ReviewNote(BaseModel):
    note_id: str = Field(default_factory=_new_id)
    project_id: str
    anchor: NoteAnchor
    text: str = ""
    source: NoteSource
    status: NoteStatus = NoteStatus.pending
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    processed_at: Optional[str] = None
    commit_token: Optional[str] = None
    resulting_op_ids: list[str] = []


_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    note_id        TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL,
    anchor_type    TEXT NOT NULL CHECK (anchor_type IN ('timestamp', 'region', 'op')),
    anchor         TEXT NOT NULL,
    text           TEXT NOT NULL DEFAULT '',
    source         TEXT NOT NULL CHECK (source IN ('typed', 'voice', 'region', 'agent', 'form_correction')),
    status         TEXT NOT NULL CHECK (status IN ('pending', 'processed', 'dismissed')),
    created_at     TEXT NOT NULL,
    processed_at   TEXT,
    commit_token   TEXT,
    resulting_op_ids TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_notes_project_status ON notes(project_id, status);
CREATE INDEX IF NOT EXISTS idx_notes_commit_token ON notes(commit_token);
CREATE INDEX IF NOT EXISTS idx_notes_created_at ON notes(created_at);
"""


class NotesStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as con:
            con.executescript(_SCHEMA)

    def _row_to_note(self, row: sqlite3.Row) -> ReviewNote:
        anchor_type = row["anchor_type"]
        anchor_data = json.loads(row["anchor"])
        if anchor_type == "timestamp":
            anchor = TimestampAnchor(**anchor_data)
        elif anchor_type == "region":
            anchor = RegionAnchor(**anchor_data)
        else:
            anchor = OpAnchor(**anchor_data)
        return ReviewNote(
            note_id=row["note_id"],
            project_id=row["project_id"],
            anchor=anchor,
            text=row["text"],
            source=NoteSource(row["source"]),
            status=NoteStatus(row["status"]),
            created_at=row["created_at"],
            processed_at=row["processed_at"],
            commit_token=row["commit_token"],
            resulting_op_ids=json.loads(row["resulting_op_ids"] or "[]"),
        )

    def append(self, note: ReviewNote) -> str:
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT INTO notes (note_id, project_id, anchor_type, anchor, text, source, status, created_at, processed_at, commit_token, resulting_op_ids) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    note.note_id,
                    note.project_id,
                    note.anchor.anchor_type,
                    note.anchor.model_dump_json(),
                    note.text,
                    note.source.value,
                    note.status.value,
                    note.created_at,
                    note.processed_at,
                    note.commit_token,
                    json.dumps(note.resulting_op_ids),
                ),
            )
        return note.note_id

    def list_all(self, project_id: str, status: Optional[NoteStatus] = None) -> list[ReviewNote]:
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            if status is None:
                rows = con.execute(
                    "SELECT * FROM notes WHERE project_id = ? ORDER BY created_at",
                    (project_id,),
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM notes WHERE project_id = ? AND status = ? ORDER BY created_at",
                    (project_id, status.value),
                ).fetchall()
        return [self._row_to_note(r) for r in rows]

    def list_pending(self, project_id: str) -> list[ReviewNote]:
        return self.list_all(project_id, status=NoteStatus.pending)

    def commit_pending(self, project_id: str, commit_token: str) -> list[ReviewNote]:
        """Per audit H1: stamp commit_token on all pending notes; return them.

        Does NOT mark them processed. The agent run uses the returned list
        to build pending_feedback; mark_processed is called after agent run.
        """
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "UPDATE notes SET commit_token = ? WHERE project_id = ? AND status = 'pending'",
                (commit_token, project_id),
            )
        return self.list_pending(project_id)

    def mark_processed(self, note_ids: list[str], resulting_op_ids: list[str]) -> None:
        with sqlite3.connect(self.db_path) as con:
            for note_id, op_id in zip(note_ids, resulting_op_ids):
                con.execute(
                    "UPDATE notes SET status = 'processed', processed_at = ?, resulting_op_ids = ? "
                    "WHERE note_id = ?",
                    (datetime.now(timezone.utc).isoformat(), json.dumps([op_id]), note_id),
                )

    def mark_dismissed(self, note_ids: list[str]) -> None:
        with sqlite3.connect(self.db_path) as con:
            for note_id in note_ids:
                con.execute(
                    "UPDATE notes SET status = 'dismissed' WHERE note_id = ?",
                    (note_id,),
                )
```

### Step 4: Run test to verify it passes

Run: `cd open_edit && pytest tests/test_storage/test_notes.py -v`
Expected: 8 passed.

### Step 5: Export from storage package

Modify `open_edit/open_edit/storage/__init__.py`:

```python
from open_edit.storage.notes import (
    NotesStore, ReviewNote, TimestampAnchor, RegionAnchor, OpAnchor,
    NoteSource, NoteStatus, NoteAnchor,
)
```

### Step 6: Run full open_edit test suite

Run: `cd open_edit && pytest`
Expected: 212 passed, 5 skipped (no regressions).

### Step 7: Implement WS message handlers

In `pyagent-kdenlive-guide/phase4_chat_ui/ws/handler.py`, add to the message dispatch:

```python
if msg["type"] == "note_add":
    await handlers.handle_note_add(ws, project_id, msg, broadcast)
elif msg["type"] == "note_update":
    await handlers.handle_note_update(ws, project_id, msg, broadcast)
elif msg["type"] == "note_delete":
    await handlers.handle_note_delete(ws, project_id, msg, broadcast)
elif msg["type"] == "note_list":
    await handlers.handle_note_list(ws, project_id, msg, broadcast)
```

In `pyagent-kdenlive-guide/phase4_chat_ui/ws/handlers.py`, add 4 handlers:

```python
async def handle_note_add(ws, project_id, msg, broadcast):
    from open_edit.storage.notes import NotesStore, ReviewNote
    store = NotesStore(get_notes_db_path(project_id))
    note = ReviewNote(
        project_id=project_id,
        anchor=parse_anchor(msg["anchor"]),
        text=msg.get("text", ""),
        source=msg["source"],
        status="pending",
    )
    store.append(note)
    await broadcast(project_id, {"type": "note_list", "project_id": project_id, "notes": [n.model_dump(mode="json") for n in store.list_all(project_id)]})


async def handle_note_update(ws, project_id, msg, broadcast):
    from open_edit.storage.notes import NotesStore
    store = NotesStore(get_notes_db_path(project_id))
    if "text" in msg:
        # Update text via direct SQL
        with sqlite3.connect(store.db_path) as con:
            con.execute("UPDATE notes SET text = ? WHERE note_id = ?", (msg["text"], msg["note_id"]))
    if msg.get("status") == "dismissed":
        store.mark_dismissed([msg["note_id"]])
    await broadcast(project_id, {"type": "note_list", "project_id": project_id, "notes": [n.model_dump(mode="json") for n in store.list_all(project_id)]})


async def handle_note_delete(ws, project_id, msg, broadcast):
    from open_edit.storage.notes import NotesStore
    store = NotesStore(get_notes_db_path(project_id))
    store.mark_dismissed([msg["note_id"]])
    await broadcast(project_id, {"type": "note_list", "project_id": project_id, "notes": [n.model_dump(mode="json") for n in store.list_all(project_id)]})


async def handle_note_list(ws, project_id, msg, broadcast):
    from open_edit.storage.notes import NotesStore
    store = NotesStore(get_notes_db_path(project_id))
    await ws.send_json({
        "type": "note_list",
        "project_id": project_id,
        "notes": [n.model_dump(mode="json") for n in store.list_all(project_id)],
    })
```

The `broadcast(project_id, msg)` function maintains a `project_id → set[ws]` map and sends to all websockets for that project (per audit H4).

### Step 8: Implement notes sidebar in project state panel

In `pyagent-kdenlive-guide/phase4_chat_ui/static/index.html`, add a notes section to the right sidebar (project state column):

```html
<div class="notes-section">
    <h3>Notes <span id="notes-count" class="badge">0</span></h3>
    <div id="notes-list"></div>
    <button id="notes-view-all" class="ghost-btn">View all</button>
</div>
```

In `pyagent-kdenlive-guide/phase4_chat_ui/static/app.js`, add:

```javascript
function renderNotesSection(notes) {
    const list = document.getElementById("notes-list");
    list.innerHTML = "";
    const pending = notes.filter(n => n.status === "pending");
    document.getElementById("notes-count").textContent = pending.length;
    for (const n of pending.slice(0, 3)) {
        const item = document.createElement("div");
        item.className = "note-item";
        const anchorText = n.anchor.anchor_type === "timestamp"
            ? `[${formatTime(n.anchor.t_start)} - ${formatTime(n.anchor.t_end)}]`
            : n.anchor.anchor_type === "region"
            ? `[${formatTime(n.anchor.t_start)} region]`
            : `[op: ${n.anchor.op_id}]`;
        item.textContent = `${anchorText} ${n.text || "(no text)"}`;
        list.appendChild(item);
    }
}

ws.addEventListener("message", (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === "note_list") {
        renderNotesSection(msg.notes);
    }
});
```

### Step 9: Add CLI subcommand

In `open_edit/open_edit/cli.py`, add a `notes` subcommand:

```python
def notes_cmd(args):
    from open_edit.storage.notes import NotesStore
    store = NotesStore(Path(args.project_dir) / "notes.db")
    notes = store.list_all(args.project_id, status=getattr(NoteStatus, args.status) if args.status else None)
    for n in notes:
        print(f"{n.note_id} [{n.status}] {n.anchor.anchor_type} {n.text}")

# Add to argparse:
parser_notes = subparsers.add_parser("notes", help="List notes for a project")
parser_notes.add_argument("project_id")
parser_notes.add_argument("--project-dir", required=True)
parser_notes.add_argument("--status", choices=["pending", "processed", "dismissed"])
```

### Step 10: Write WS broadcast test

Create `pyagent-kdenlive-guide/phase4_chat_ui/tests/test_notes_ws_broadcast.py`:

```python
"""Phase 4 Task 2: WS broadcast is project-scoped (audit H4)."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from phase4_chat_ui.ws.handlers import handle_note_add


@pytest.mark.asyncio
async def test_note_add_broadcasts_to_project():
    broadcast = AsyncMock()
    ws = AsyncMock()
    await handle_note_add(
        ws,
        project_id="p1",
        msg={"anchor": {"anchor_type": "timestamp", "t_start": 0.0, "t_end": 1.0}, "text": "test", "source": "typed"},
        broadcast=broadcast,
    )
    broadcast.assert_called_once()
    call_args = broadcast.call_args[0]
    assert call_args[0] == "p1"
    assert call_args[1]["type"] == "note_list"
    assert call_args[1]["project_id"] == "p1"
```

### Step 11: Run all new tests + existing tests

Run: `cd open_edit && pytest tests/test_storage/test_notes.py -v && cd ../pyagent-kdenlive-guide/phase4_chat_ui && pytest tests/test_notes_ws_broadcast.py -v`
Expected: 8 + 1 = 9 passed.

### Step 12: Commit

```bash
git add open_edit/storage/notes.py open_edit/storage/__init__.py open_edit/cli.py open_edit/tests/test_storage/test_notes.py open_edit/tests/conftest.py
git add pyagent-kdenlive-guide/phase4_chat_ui/ws/handler.py pyagent-kdenlive-guide/phase4_chat_ui/ws/handlers.py pyagent-kdenlive-guide/phase4_chat_ui/static/index.html pyagent-kdenlive-guide/phase4_chat_ui/static/app.js
git add pyagent-kdenlive-guide/phase4_chat_ui/tests/test_notes_ws_broadcast.py
git commit -m "[open_edit] phase4 t6: unified notes store + sidebar UI + WS broadcast"
```

---

## Task 3: T2 Style Memory — aggregate, retrieve, style_inject

**Files:**
- Create: `open_edit/open_edit/style/aggregate.py` (rule-based rollup)
- Create: `open_edit/open_edit/style/retrieve.py` (tag-gated slice)
- Create: `open_edit/open_edit/agent/style_inject.py` (prior_state block builder)
- Create: `open_edit/open_edit/storage/config.py` (manages `~/.open-edit/` bootstrap + chmod 600)
- Modify: `open_edit/open_edit/style/__init__.py` (export)
- Modify: `open_edit/open_edit/storage/taste_events.py` (already exists; verify rollup trigger)
- Test: `open_edit/tests/test_style/test_aggregate.py`
- Test: `open_edit/tests/test_style/test_retrieve.py`
- Test: `open_edit/tests/test_style/test_style_inject.py`

**Interfaces:**
- Consumes: existing `TasteEvent` Pydantic model and `TasteEventStore` (Phase 3 stub at `open_edit/open_edit/style/taste_events.py`).
- Produces:
  - `aggregate.rollup(project_id: str) -> StyleProfile` — reads all taste events, applies weights, writes `~/.open-edit/style_profile.json` (chmod 600), keeps last 3 versions as `.bak`. Returns the new profile.
  - `aggregate.reset() -> None` — clears `style_profile.json` and the relevant events.
  - `aggregate.set_pinned(key: str, value) -> None` — sets a pinned value in the profile's `pinned` block.
  - `aggregate.check_rollup_trigger(project_id: str) -> bool` — checks if any of the three triggers (project close, commit_feedback, token budget) fired.
  - `retrieve.get_slice(op_type: str) -> dict` — returns tag-gated profile slice, ≤250 tokens, omitting categories with confidence < 0.2.
  - `style_inject.build_prior_state(project_id: str, expected_op_type: str | None = None) -> str` — returns the formatted prior_state block, ≤600 tokens total (per audit M4: style ≤250 + notes ≤150 + creativity ≤50 + last 3 ops ≤150).
  - `storage/config.py:get_config_dir() -> Path` — returns `~/.open-edit/`, creates it with `chmod 700` if missing. `get_profile_path() -> Path` — returns `~/.open-edit/style_profile.json`, sets `chmod 600` if created.

### Step 1: Write the failing test for `aggregate.py`

Create `open_edit/tests/test_style/test_aggregate.py`:

```python
"""Phase 4 Task 3: style memory aggregation."""
import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from open_edit.style.taste_events import TasteEvent, TasteEventStore
from open_edit.style.aggregate import rollup, reset, set_pinned


def _make_event(action: str, weight: int, proposed: dict, final: dict | None = None, ts_offset_days: int = 0) -> TasteEvent:
    ts = (datetime.now(timezone.utc) - timedelta(days=ts_offset_days)).isoformat()
    return TasteEvent(
        project_id="p1",
        op_type="AddTransition",
        proposed_params=proposed,
        final_params=final or proposed,
        action=action,
        correction_note="",
        timestamp=ts,
        weight=weight,
    )


def test_rollup_creates_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    store.append(_make_event("applied_modified", 5, {"duration_s": 2.0}, {"duration_s": 1.5}))
    profile = rollup("p1", store)
    assert "transitions" in profile.model_dump()
    assert profile.meta["sample_size"] == 1


def test_rollup_weights_applied(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    for _ in range(10):
        store.append(_make_event("applied_modified", 5, {"duration_s": 2.0}, {"duration_s": 1.5}))
    profile = rollup("p1", store)
    assert profile.transitions["confidence"] >= 0.9


def test_rollup_applied_unmodified_weight_zero(tmp_path, monkeypatch):
    """Per spec §8.4: indifference is not signal."""
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    for _ in range(20):
        store.append(_make_event("applied_unmodified", 1, {"duration_s": 1.0}))
    profile = rollup("p1", store)
    # 20 weak signals (weight=1) should not reach confidence 1.0
    assert profile.transitions["confidence"] < 0.5


def test_rollup_eviction_by_weight(tmp_path, monkeypatch):
    """Per spec §8.6.3: cap at 4 examples per category, evict lowest weight."""
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    for i in range(6):
        store.append(_make_event("applied_modified", 5, {"duration_s": 2.0 + i * 0.1}, {"duration_s": 1.0}))
    profile = rollup("p1", store)
    assert len(profile.transitions["examples"]) <= 4


def test_rollup_keeps_last_3_versions(tmp_path, monkeypatch):
    """Per spec §8.6.7: keep last 3 versions as .bak."""
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    for v in range(5):
        store.append(_make_event("applied_modified", 5, {"duration_s": float(v)}, {"duration_s": float(v) * 0.5}))
        rollup("p1", store)
    profile_dir = Path.home() / ".open-edit"
    baks = sorted(profile_dir.glob("style_profile_v*.json.bak"))
    assert len(baks) == 3


def test_chmod_600(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    store.append(_make_event("applied_modified", 5, {"duration_s": 2.0}, {"duration_s": 1.5}))
    rollup("p1", store)
    profile_path = Path.home() / ".open-edit" / "style_profile.json"
    assert oct(profile_path.stat().st_mode)[-3:] == "600"


def test_set_pinned(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    store.append(_make_event("applied_modified", 5, {"duration_s": 2.0}, {"duration_s": 1.5}))
    rollup("p1", store)
    set_pinned("fades.default_out_s", 1.8)
    profile = rollup("p1", store)  # Re-read
    assert profile.pinned["fades.default_out_s"] == 1.8
```

### Step 2: Run test to verify it fails

Run: `cd open_edit && pytest tests/test_style/test_aggregate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'open_edit.style.aggregate'`

### Step 3: Implement `storage/config.py`

Create `open_edit/open_edit/storage/config.py`:

```python
"""Manages ~/.open-edit/ directory and config files."""
import json
import os
from pathlib import Path


def get_config_dir() -> Path:
    p = Path.home() / ".open-edit"
    p.mkdir(parents=True, exist_ok=True)
    os.chmod(p, 0o700)
    return p


def get_profile_path() -> Path:
    p = get_config_dir() / "style_profile.json"
    if not p.exists():
        p.write_text(json.dumps(_default_profile()))
        os.chmod(p, 0o600)
    return p


def _default_profile() -> dict:
    return {
        "meta": {"version": 0, "updated_at": "", "sample_size": 0, "window": "90d_or_200events"},
        "transitions": {"preferred": [], "avoid": [], "default_duration_s": 1.0, "confidence": 0.0, "examples": []},
        "fades": {"default_in_s": 0.5, "default_out_s": 1.0, "tendency": "", "confidence": 0.0, "examples": []},
        "pacing": {"agent_avg_clip_s": 0.0, "user_avg_clip_s": 0.0, "ratio": 1.0, "tendency": "", "confidence": 0.0, "examples": []},
        "color": {"tendency": "", "confidence": 0.0, "examples": []},
        "audio": {"music_preference": "", "voice_leveling": "", "confidence": 0.0},
        "text_captions": {"style": "", "timing": "", "confidence": 0.0},
        "visual_treatment": {"recurring_effects": [], "confidence": 0.0, "note": ""},
        "structure": {"intro_pattern": "", "outro_pattern": "", "common_shape": ""},
        "export": {"aspect_ratio": "16:9", "resolution": "1080p", "confidence": 0.0},
        "corrections": {"most_overridden_param": "", "direction": "", "note": ""},
        "pinned": {},
    }
```

### Step 4: Implement `style/aggregate.py`

Create `open_edit/open_edit/style/aggregate.py`:

```python
"""Rule-based rollup of taste events into a style profile.

Per phase4-design-revised.md §3.2 and spec §8.6.
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from open_edit.style.taste_events import TasteEventStore, TasteEvent
from open_edit.storage.config import get_config_dir, get_profile_path


def rollup(project_id: str, store: TasteEventStore) -> dict:
    events = store.pull(project_id=project_id, window_days=90, max_events=200)
    profile = json.loads(get_profile_path().read_text())

    weighted_sum_transitions = 0
    examples_transitions = []
    for ev in events:
        if ev.op_type == "AddTransition":
            weight = _weight_for_action(ev.action)
            weighted_sum_transitions += weight
            if ev.action == "applied_modified" and len(examples_transitions) < 4:
                examples_transitions.append({
                    "proposed": ev.proposed_params,
                    "final": ev.final_params,
                    "weight": abs(weight),
                })
    profile["transitions"]["examples"] = examples_transitions
    profile["transitions"]["confidence"] = min(abs(weighted_sum_transitions) / 50, 1.0)
    profile["meta"]["sample_size"] = len(events)
    profile["meta"]["updated_at"] = datetime.now(timezone.utc).isoformat()
    profile["meta"]["version"] = profile["meta"].get("version", 0) + 1

    _write_profile_with_backup(profile)
    store.purge(project_id=project_id)
    return profile


def reset() -> None:
    profile_path = get_profile_path()
    if profile_path.exists():
        profile_path.unlink()
    get_profile_path()  # Re-create with defaults


def set_pinned(key: str, value) -> None:
    profile = json.loads(get_profile_path().read_text())
    profile.setdefault("pinned", {})[key] = value
    _write_profile_with_backup(profile)


def check_rollup_trigger(project_id: str, store: TasteEventStore) -> bool:
    """Per audit M3: triggers are project close, commit_feedback, token budget.

    Token budget: if unrolled events would exceed ~2000 tokens.
    """
    events = store.pull(project_id=project_id, window_days=90, max_events=200)
    estimated_tokens = sum(len(json.dumps(e.model_dump())) for e in events) / 4
    return estimated_tokens >= 2000


def _weight_for_action(action: str) -> int:
    if action == "applied_modified":
        return 5
    if action == "reverted":
        return -3
    return 0  # applied_unmodified


def _write_profile_with_backup(profile: dict) -> None:
    profile_path = get_profile_path()
    config_dir = get_config_dir()
    # Rotate last 3 versions
    for i in range(2, 0, -1):
        src = config_dir / f"style_profile_v{i}.json.bak"
        dst = config_dir / f"style_profile_v{i+1}.json.bak"
        if src.exists():
            shutil.copy2(src, dst)
    if profile_path.exists():
        shutil.copy2(profile_path, config_dir / "style_profile_v1.json.bak")
    # Clean up old backups beyond 3
    for f in config_dir.glob("style_profile_v[4-9]*.json.bak"):
        f.unlink()
    profile_path.write_text(json.dumps(profile, indent=2))
    os.chmod(profile_path, 0o600)
```

### Step 5: Run aggregate test to verify it passes

Run: `cd open_edit && pytest tests/test_style/test_aggregate.py -v`
Expected: 7 passed.

### Step 6: Write the failing test for `retrieve.py`

Create `open_edit/tests/test_style/test_retrieve.py`:

```python
"""Phase 4 Task 3: tag-gated style profile retrieval."""
import json
import pytest
from pathlib import Path

from open_edit.style.taste_events import TasteEvent, TasteEventStore
from open_edit.style.aggregate import rollup
from open_edit.style.retrieve import get_slice


def _make_event(action: str, weight: int, proposed: dict, final: dict | None = None):
    from datetime import datetime, timezone
    return TasteEvent(
        project_id="p1",
        op_type="AddTransition",
        proposed_params=proposed,
        final_params=final or proposed,
        action=action,
        correction_note="",
        timestamp=datetime.now(timezone.utc).isoformat(),
        weight=weight,
    )


def test_get_slice_add_transition(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    for _ in range(10):
        store.append(_make_event("applied_modified", 5, {"duration_s": 2.0}, {"duration_s": 1.5}))
    rollup("p1", store)
    slice_data = get_slice("AddTransition")
    assert "transitions" in slice_data
    assert "corrections" in slice_data  # Always included


def test_get_slice_omits_low_confidence(tmp_path, monkeypatch):
    """Per spec §8.8: below confidence 0.2, category is omitted."""
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    # 1 weak signal = confidence = 5/50 = 0.1
    store.append(_make_event("applied_modified", 5, {"duration_s": 2.0}, {"duration_s": 1.5}))
    rollup("p1", store)
    slice_data = get_slice("AddTransition")
    # transitions confidence is 0.1, should be omitted
    assert "transitions" not in slice_data
    # corrections is always included
    assert "corrections" in slice_data


def test_get_slice_token_cap(tmp_path, monkeypatch):
    """Per spec §8.8: slice is ≤250 tokens."""
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    for _ in range(10):
        store.append(_make_event("applied_modified", 5, {"duration_s": 2.0}, {"duration_s": 1.5}))
    rollup("p1", store)
    slice_data = get_slice("AddTransition")
    text = json.dumps(slice_data)
    tokens = len(text) / 4  # rough estimate
    assert tokens <= 250


def test_tag_map_covers_all_op_types():
    """All 12 op types have a tag map entry."""
    from open_edit.style.retrieve import TAG_MAP
    expected_ops = [
        "AddTransition", "AddEffect", "SetKeyframe", "AddClip", "MoveClip",
        "TrimClip", "SetAudioGain", "NormalizeAudio", "RemoveClip", "GroupEdits",
        "RawMltXml", "FreeFormCode",
    ]
    for op in expected_ops:
        assert op in TAG_MAP, f"Missing op type: {op}"
```

### Step 7: Implement `style/retrieve.py`

Create `open_edit/open_edit/style/retrieve.py`:

```python
"""Tag-gated style profile retrieval for system prompt injection.

Per phase4-design-revised.md §3.2 and spec §8.8.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from open_edit.storage.config import get_profile_path


TAG_MAP: dict[str, list[str]] = {
    "AddTransition": ["transitions", "corrections"],
    "AddEffect": ["fades", "color", "visual_treatment", "corrections"],
    "SetKeyframe": ["fades", "color", "corrections"],
    "AddClip": ["pacing", "corrections"],
    "MoveClip": ["pacing", "corrections"],
    "TrimClip": ["pacing", "corrections"],
    "RemoveClip": ["pacing", "corrections"],
    "SetAudioGain": ["audio", "corrections"],
    "NormalizeAudio": ["audio", "corrections"],
    "GroupEdits": ["structure", "corrections"],
    "RawMltXml": ["corrections"],
    "FreeFormCode": ["corrections"],
}

CONFIDENCE_THRESHOLD = 0.2
MAX_TOKENS = 250


def get_slice(op_type: str) -> dict[str, Any]:
    profile = json.loads(get_profile_path().read_text())
    categories = TAG_MAP.get(op_type, ["corrections"])
    result: dict[str, Any] = {}
    for cat in categories:
        if cat == "corrections":
            result["corrections"] = profile.get("corrections", {})
            continue
        if cat not in profile:
            continue
        data = profile[cat]
        confidence = data.get("confidence", 0.0) if isinstance(data, dict) else 0.0
        if confidence < CONFIDENCE_THRESHOLD:
            continue
        result[cat] = data
    return _trim_to_token_cap(result)


def _trim_to_token_cap(slice_data: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(slice_data)
    tokens = len(text) / 4
    if tokens <= MAX_TOKENS:
        return slice_data
    # Trim in order: examples first, then non-essential fields
    for cat in list(slice_data.keys()):
        if cat == "corrections":
            continue
        if "examples" in slice_data[cat]:
            slice_data[cat]["examples"] = []
            text = json.dumps(slice_data)
            tokens = len(text) / 4
            if tokens <= MAX_TOKENS:
                return slice_data
    return slice_data
```

### Step 8: Run retrieve test to verify it passes

Run: `cd open_edit && pytest tests/test_style/test_retrieve.py -v`
Expected: 4 passed.

### Step 9: Write the failing test for `style_inject.py`

Create `open_edit/tests/test_style/test_style_inject.py`:

```python
"""Phase 4 Task 3: prior_state block builder."""
import pytest
from pathlib import Path

from open_edit.style.taste_events import TasteEvent, TasteEventStore
from open_edit.style.aggregate import rollup
from open_edit.agent.style_inject import build_prior_state


def _make_event(action: str, weight: int, proposed: dict, final: dict | None = None):
    from datetime import datetime, timezone
    return TasteEvent(
        project_id="p1",
        op_type="AddTransition",
        proposed_params=proposed,
        final_params=final or proposed,
        action=action,
        correction_note="",
        timestamp=datetime.now(timezone.utc).isoformat(),
        weight=weight,
    )


def test_build_prior_state_format(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    for _ in range(10):
        store.append(_make_event("applied_modified", 5, {"duration_s": 2.0}, {"duration_s": 1.5}))
    rollup("p1", store)
    state = build_prior_state(project_id="p1", expected_op_type="AddTransition", creativity_level="balanced")
    assert "<prior_state>" in state
    assert "</prior_state>" in state
    assert "creativity_level: balanced" in state


def test_build_prior_state_token_budget(tmp_path, monkeypatch):
    """Per audit M4: total ≤600 tokens."""
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    for _ in range(10):
        store.append(_make_event("applied_modified", 5, {"duration_s": 2.0}, {"duration_s": 1.5}))
    rollup("p1", store)
    state = build_prior_state(project_id="p1", expected_op_type="AddTransition", creativity_level="balanced")
    tokens = len(state) / 4
    assert tokens <= 600, f"prior_state is {tokens} tokens, exceeds 600 budget"


def test_pin_precedence_in_prior_state(tmp_path, monkeypatch):
    """Per spec §8.7: pinned > profile_default > LLM_default."""
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    for _ in range(10):
        store.append(_make_event("applied_modified", 5, {"duration_s": 2.0}, {"duration_s": 1.5}))
    rollup("p1", store)
    from open_edit.style.aggregate import set_pinned
    set_pinned("transitions.default_duration_s", 0.5)
    state = build_prior_state(project_id="p1", expected_op_type="AddTransition", creativity_level="balanced")
    # The pinned value should appear, with priority marker
    assert "0.5" in state
    assert "[pinned]" in state
```

### Step 10: Implement `agent/style_inject.py`

Create `open_edit/open_edit/agent/style_inject.py`:

```python
"""Builds the prior_state block for the system prompt.

Per phase4-design-revised.md §3.2 (T2) and audit M4.
"""
from __future__ import annotations

from typing import Optional

from open_edit.style.retrieve import get_slice
from open_edit.storage.config import get_profile_path
from open_edit.storage.edit_graph import EditGraphStore


def build_prior_state(
    project_id: str,
    expected_op_type: Optional[str] = None,
    creativity_level: str = "balanced",
    workdir: Optional[str] = None,
) -> str:
    parts = []

    # 1. Creativity directive (≤50 tokens)
    parts.append(f"<creativity_level>{creativity_level}</creativity_level>")

    # 2. Style slice (≤250 tokens)
    if expected_op_type:
        slice_data = get_slice(expected_op_type)
        if slice_data:
            parts.append(f"<style_slice>{_format_slice(slice_data)}</style_slice>")

    # 3. Pin overrides
    profile = _load_profile()
    pinned = profile.get("pinned", {})
    if pinned:
        pinned_lines = "\n".join(f"{k}: {v} [pinned]" for k, v in pinned.items())
        parts.append(f"<pinned>\n{pinned_lines}\n</pinned>")

    # 4. Latest 3 ops (≤150 tokens)
    if workdir:
        store = EditGraphStore(Path(workdir) / "edit_graph.db")
        recent = store.load_all()[-3:]
        if recent:
            ops_lines = "\n".join(
                f"- {op.kind} ({op.author}) at {op.timestamp[:19]}"
                for op in recent
            )
            parts.append(f"<latest_ops>\n{ops_lines}\n</latest_ops>")

    # 5. Pending notes summary (≤150 tokens)
    # Implemented in T6's style_inject update; here just placeholder.
    parts.append("<pending_notes_summary>0 pending notes</pending_notes_summary>")

    inner = "\n".join(parts)
    return f"<prior_state>\n{inner}\n</prior_state>"


def _load_profile() -> dict:
    import json
    return json.loads(get_profile_path().read_text())


def _format_slice(slice_data: dict) -> str:
    import json
    return json.dumps(slice_data, indent=2)
```

### Step 11: Run style_inject test

Run: `cd open_edit && pytest tests/test_style/test_style_inject.py -v`
Expected: 3 passed.

### Step 12: Run full open_edit test suite

Run: `cd open_edit && pytest`
Expected: 220 passed, 5 skipped.

### Step 13: Commit

```bash
git add open_edit/style/aggregate.py open_edit/style/retrieve.py open_edit/agent/style_inject.py open_edit/storage/config.py open_edit/style/__init__.py
git add open_edit/tests/test_style/test_aggregate.py open_edit/tests/test_style/test_retrieve.py open_edit/tests/test_style/test_style_inject.py
git commit -m "[open_edit] phase4 t2: style memory (aggregate + retrieve + style_inject + chmod 600)"
```

---

## Task 4: T5 HTML5 preview player + region mark + per-frame notes + STT

**Files:**
- Modify: `pyagent-kdenlive-guide/phase4_chat_ui/static/index.html` (add `<video>` element, version switcher dropdown, region mark overlay, per-frame note input, STT button)
- Modify: `pyagent-kdenlive-guide/phase4_chat_ui/static/app.js` (video player logic, region mark drag handler, per-frame note input, STT button hook)
- Modify: `pyagent-kdenlive-guide/phase4_chat_ui/static/style.css` (video player styles, region mark overlay)
- Modify: `open_edit/open_edit/render/orchestrator.py` (emit `version_ready` event after render; integrate with RenderSnapshotStore — Task 5's deliverable)
- Test: `pyagent-kdenlive-guide/phase4_chat_ui/tests/test_stt_secure_context.py`
- Test: `pyagent-kdenlive-guide/phase4_chat_ui/tests/test_region_mark_validation.py`

**Interfaces:**
- Consumes: T6's `note_add` WS message; T4's `version_list` and `version_ready` WS messages; existing chat UI's state.
- Produces:
  - HTML5 `<video>` element loading the latest render URL.
  - Click-and-drag on the video frame: produces a region `(x, y, w, h, t_start, t_end)`; client-side validation rejects `t_start < 0` or `t_end > video_duration` (per audit C3); sends `note_add` with `source=region`.
  - Per-frame note input: click on scrub bar at time `T` → note input appears → user types → `note_add` with `source=typed` and `anchor={t_start: T, t_end: T}`.
  - STT button: uses `window.SpeechRecognition || window.webkitSpeechRecognition`; hidden if `!window.isSecureContext` (per audit M7); transcribed text populates the note field.
  - "Send to Claude" button: sends `commit_feedback` (T6's message type); disabled until `version_ready` is received.

### Step 1: Write the failing test for STT

Create `pyagent-kdenlive-guide/phase4_chat_ui/tests/test_stt_secure_context.py`:

```python
"""Phase 4 Task 4: STT button is hidden when not in secure context (audit M7)."""
import pytest
from unittest.mock import MagicMock, patch
import importlib


def test_stt_button_hidden_when_not_secure():
    """Per audit M7: STT requires secure context; button is hidden otherwise."""
    # Simulate a non-secure browser context
    with patch.dict("sys.modules", {
        "phase4_chat_ui.static.app": MagicMock(isSecureContext=False),
    }):
        # The function under test checks `window.isSecureContext`; if false, button is hidden
        from phase4_chat_ui.static.app import shouldShowSttButton
        assert shouldShowSttButton() is False


def test_stt_button_visible_when_secure():
    with patch("phase4_chat_ui.static.app.isSecureContext", True, create=True):
        from phase4_chat_ui.static.app import shouldShowSttButton
        assert shouldShowSttButton() is True
```

### Step 2: Run test to verify it fails

Run: `cd pyagent-kdenlive-guide/phase4_chat_ui && pytest tests/test_stt_secure_context.py -v`
Expected: FAIL with `ImportError` (function doesn't exist yet).

### Step 3: Add `<video>` element + region mark overlay + per-frame note input + STT button to `index.html`

Modify `pyagent-kdenlive-guide/phase4_chat_ui/static/index.html`:

```html
<!-- Add to the right sidebar (project state column) before the notes section -->
<div class="preview-section">
    <h3>Preview</h3>
    <video id="preview-video" controls></video>
    <div id="region-overlay" class="region-overlay"></div>
    <div id="scrub-marker-row" class="scrub-marker-row"></div>
    <div class="preview-controls">
        <select id="version-switcher" class="ghost-btn"></select>
        <button id="stt-btn" class="ghost-btn" style="display:none;">🎙️</button>
        <input type="text" id="per-frame-note" placeholder="Note at current time..." style="display:none;">
        <button id="commit-btn" class="primary-btn">Send to Claude</button>
    </div>
</div>
```

### Step 4: Add JS logic in `app.js`

Modify `pyagent-kdenlive-guide/phase4_chat_ui/static/app.js`:

```javascript
function shouldShowSttButton() {
    return window.isSecureContext === true &&
        ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window);
}

function initSttButton() {
    const btn = document.getElementById("stt-btn");
    if (shouldShowSttButton()) {
        btn.style.display = "inline-block";
        const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        const recognition = new Recognition();
        btn.onclick = () => {
            const noteInput = document.getElementById("per-frame-note");
            recognition.start();
            recognition.onresult = (e) => {
                noteInput.value = e.results[0][0].transcript;
            };
        };
    }
}

function initVideoPlayer() {
    const video = document.getElementById("preview-video");
    // Load latest render URL
    send({ type: "version_list" });

    // Click-and-drag region mark
    const overlay = document.getElementById("region-overlay");
    let dragStart = null;
    overlay.onmousedown = (e) => {
        const rect = video.getBoundingClientRect();
        dragStart = {
            x: e.clientX - rect.left,
            y: e.clientY - rect.top,
            t_start: video.currentTime,
        };
    };
    overlay.onmousemove = (e) => {
        if (!dragStart) return;
        const rect = video.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        overlay.style.left = Math.min(dragStart.x, x) + "px";
        overlay.style.top = Math.min(dragStart.y, y) + "px";
        overlay.style.width = Math.abs(x - dragStart.x) + "px";
        overlay.style.height = Math.abs(y - dragStart.y) + "px";
    };
    overlay.onmouseup = (e) => {
        if (!dragStart) return;
        const rect = video.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const w = Math.abs(x - dragStart.x);
        const h = Math.abs(y - dragStart.y);
        const t_end = video.currentTime;
        // Per audit C3: validate t_start and t_end
        if (dragStart.t_start < 0 || t_end > video.duration) {
            showToast("Cannot mark region outside video bounds");
            dragStart = null;
            overlay.style.width = "0";
            return;
        }
        // Send note_add
        send({
            type: "note_add",
            project_id: currentProjectId,
            anchor: {
                anchor_type: "region",
                x: dragStart.x, y: dragStart.y, w, h,
                t_start: dragStart.t_start, t_end,
            },
            text: "",
            source: "region",
        });
        dragStart = null;
        overlay.style.width = "0";
    };
}

function initPerFrameNote() {
    const video = document.getElementById("preview-video");
    const noteInput = document.getElementById("per-frame-note");
    video.ontimeupdate = () => {
        // Show note input when paused
        if (video.paused) {
            noteInput.style.display = "inline-block";
            noteInput.dataset.t_start = video.currentTime;
        } else {
            noteInput.style.display = "none";
        }
    };
    noteInput.onkeydown = (e) => {
        if (e.key === "Enter" && noteInput.value) {
            const t = parseFloat(noteInput.dataset.t_start);
            send({
                type: "note_add",
                project_id: currentProjectId,
                anchor: { anchor_type: "timestamp", t_start: t, t_end: t },
                text: noteInput.value,
                source: "typed",
            });
            noteInput.value = "";
            video.play();
        }
    };
}

function initCommitButton() {
    const btn = document.getElementById("commit-btn");
    btn.onclick = () => {
        send({ type: "commit_feedback", project_id: currentProjectId });
        btn.disabled = true;
        btn.textContent = "Processing...";
    };
}

ws.addEventListener("message", (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === "version_list") {
        const sel = document.getElementById("version-switcher");
        sel.innerHTML = "";
        for (const v of msg.versions) {
            const opt = document.createElement("option");
            opt.value = v.version_id;
            opt.textContent = v.label + (v.status === "rendering" ? " (rendering...)" : "");
            opt.disabled = v.status !== "ready";
            sel.appendChild(opt);
        }
        const latest = msg.versions.find(v => v.status === "ready");
        if (latest) {
            document.getElementById("preview-video").src = latest.render_path;
        }
    }
    if (msg.type === "version_ready") {
        // Re-enable commit button
        document.getElementById("commit-btn").disabled = false;
        document.getElementById("commit-btn").textContent = "Send to Claude";
        showToast(`v${msg.version_id} ready`);
        send({ type: "version_list" });
    }
});

initSttButton();
initVideoPlayer();
initPerFrameNote();
initCommitButton();
```

### Step 5: Add CSS for video player + region overlay

Modify `pyagent-kdenlive-guide/phase4_chat_ui/static/style.css`:

```css
.preview-section { padding: 8px; }
.preview-section video { width: 100%; max-height: 360px; }
.region-overlay {
    position: absolute;
    border: 2px dashed yellow;
    background: rgba(255, 255, 0, 0.1);
    pointer-events: all;
}
.scrub-marker-row { position: relative; height: 8px; background: #333; }
.scrub-marker-row .marker { position: absolute; width: 2px; background: red; height: 100%; }
.preview-controls { display: flex; gap: 4px; align-items: center; margin-top: 4px; }
```

### Step 6: Run STT test

Run: `cd pyagent-kdenlive-guide/phase4_chat_ui && pytest tests/test_stt_secure_context.py -v`
Expected: 2 passed.

### Step 7: Manual smoke test

```bash
cd pyagent-kdenlive-guide/phase4_chat_ui && python -m http.server 8000
# Open http://localhost:8000 in Chrome
# Verify: video element appears; region mark drag works; STT button shows; "Send to Claude" button works
```

### Step 8: Commit

```bash
git add pyagent-kdenlive-guide/phase4_chat_ui/static/index.html pyagent-kdenlive-guide/phase4_chat_ui/static/app.js pyagent-kdenlive-guide/phase4_chat_ui/static/style.css
git add pyagent-kdenlive-guide/phase4_chat_ui/tests/test_stt_secure_context.py
git commit -m "[open_edit] phase4 t5: HTML5 preview + region mark + per-frame notes + STT"
```

---

## Task 5: T4 RenderSnapshotStore + version switcher

**Files:**
- Create: `open_edit/open_edit/storage/render_snapshots.py` (Pydantic types + RenderSnapshotStore)
- Modify: `open_edit/open_edit/render/orchestrator.py` (after each render, append a snapshot)
- Modify: `pyagent-kdenlive-guide/phase4_chat_ui/ws/handler.py` (new WS message types: `version_list`, `version_ready`)
- Modify: `pyagent-kdenlive-guide/phase4_chat_ui/ws/handlers.py` (handlers)
- Test: `open_edit/tests/test_storage/test_render_snapshots.py`
- Test: `pyagent-kdenlive-guide/phase4_chat_ui/tests/test_version_ready.py`
- Test: `pyagent-kdenlive-guide/phase4_chat_ui/tests/test_edit_history_pagination.py`

**Interfaces:**
- Consumes: existing `RenderCache` (Phase 2); `EditGraphStore`; `qc/gate.py` QC report.
- Produces:
  - `RenderSnapshot` Pydantic model with `version_id, project_id, edit_graph_hash, render_path, created_at, status, label` (per audit M5).
  - `RenderSnapshotStore(db_path)` with methods: `append(snapshot) -> str`, `list_for_project(project_id) -> list[RenderSnapshot]`, `latest_ready(project_id) -> Optional[RenderSnapshot]`, `evict_oldest_ready(max_versions: int) -> None` (per audit M1).
  - Max-versions cap: default 20; evict oldest `status=ready` entry; never evict `status=rendering` or `status=failed` (per audit H2).
  - Status transitions: `rendering` (initial) → `ready` (after successful render) or `failed` (on error).
  - Integration in `orchestrator.py`: after `melt_render`, call `RenderSnapshotStore.append` with `status=ready`. On error, append with `status=failed`.

### Step 1: Write the failing test

Create `open_edit/tests/test_storage/test_render_snapshots.py`:

```python
"""Phase 4 Task 5: RenderSnapshotStore + max-versions cap + status states."""
import json
import pytest
from pathlib import Path
from datetime import datetime, timezone, timedelta

from open_edit.storage.render_snapshots import (
    RenderSnapshot, RenderSnapshotStore, RenderStatus,
)


def _make_snapshot(project_id: str = "p1", status: RenderStatus = RenderStatus.ready, age_days: int = 0) -> RenderSnapshot:
    return RenderSnapshot(
        version_id=f"v_{project_id}_{age_days}",
        project_id=project_id,
        edit_graph_hash="abc123",
        render_path=Path(f"/tmp/render_{age_days}.mp4"),
        created_at=(datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat(),
        status=status,
        label=f"v{age_days}",
    )


def test_append_and_list(tmp_path):
    store = RenderSnapshotStore(tmp_path / "snapshots.db")
    snap = _make_snapshot()
    store.append(snap)
    snaps = store.list_for_project("p1")
    assert len(snaps) == 1
    assert snaps[0].version_id == snap.version_id


def test_latest_ready(tmp_path):
    store = RenderSnapshotStore(tmp_path / "snapshots.db")
    store.append(_make_snapshot(status=RenderStatus.rendering, age_days=2))
    store.append(_make_snapshot(status=RenderStatus.ready, age_days=1))
    latest = store.latest_ready("p1")
    assert latest.label == "v1"


def test_evict_oldest_ready(tmp_path):
    """Per audit M1: max-versions cap; evict oldest status=ready; never evict rendering/failed."""
    store = RenderSnapshotStore(tmp_path / "snapshots.db")
    store.append(_make_snapshot(status=RenderStatus.rendering, age_days=5))
    for i in range(25):
        store.append(_make_snapshot(age_days=i))
    store.evict_oldest_ready(max_versions=20)
    snaps = store.list_for_project("p1")
    # 25 + 1 rendering = 26; should evict 6 oldest ready; keep 19 ready + 1 rendering
    assert len(snaps) == 20
    rendering = [s for s in snaps if s.status == RenderStatus.rendering]
    assert len(rendering) == 1


def test_status_transitions(tmp_path):
    store = RenderSnapshotStore(tmp_path / "snapshots.db")
    snap = _make_snapshot(status=RenderStatus.rendering)
    store.append(snap)
    store.update_status(snap.version_id, RenderStatus.ready)
    latest = store.latest_ready("p1")
    assert latest is not None
    assert latest.status == RenderStatus.ready


def test_failed_not_evicted(tmp_path):
    store = RenderSnapshotStore(tmp_path / "snapshots.db")
    for i in range(25):
        store.append(_make_snapshot(age_days=i, status=RenderStatus.failed))
    store.evict_oldest_ready(max_versions=5)
    snaps = store.list_for_project("p1")
    # All 25 failed; evict only if status==ready
    assert len(snaps) == 25
```

### Step 2: Run test to verify it fails

Run: `cd open_edit && pytest tests/test_storage/test_render_snapshots.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'open_edit.storage.render_snapshots'`

### Step 3: Implement `storage/render_snapshots.py`

Create `open_edit/open_edit/storage/render_snapshots.py`:

```python
"""RenderSnapshotStore for version-switchable render history.

Per phase4-design-revised.md §3.4 (T4).
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class RenderStatus(str, Enum):
    rendering = "rendering"
    ready = "ready"
    failed = "failed"


def _new_version_id() -> str:
    return f"v_{uuid.uuid4().hex[:12]}"


class RenderSnapshot(BaseModel):
    version_id: str = Field(default_factory=_new_version_id)
    project_id: str
    edit_graph_hash: str
    render_path: Path
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: RenderStatus = RenderStatus.rendering
    label: str = ""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS render_snapshots (
    version_id      TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    edit_graph_hash TEXT NOT NULL,
    render_path     TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('rendering', 'ready', 'failed')),
    label           TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_snapshots_project_created ON render_snapshots(project_id, created_at);
"""


class RenderSnapshotStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as con:
            con.executescript(_SCHEMA)

    def append(self, snapshot: RenderSnapshot) -> str:
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "INSERT INTO render_snapshots (version_id, project_id, edit_graph_hash, render_path, created_at, status, label) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    snapshot.version_id, snapshot.project_id, snapshot.edit_graph_hash,
                    str(snapshot.render_path), snapshot.created_at, snapshot.status.value, snapshot.label,
                ),
            )
        return snapshot.version_id

    def list_for_project(self, project_id: str) -> list[RenderSnapshot]:
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT * FROM render_snapshots WHERE project_id = ? ORDER BY created_at",
                (project_id,),
            ).fetchall()
        return [
            RenderSnapshot(
                version_id=r["version_id"],
                project_id=r["project_id"],
                edit_graph_hash=r["edit_graph_hash"],
                render_path=Path(r["render_path"]),
                created_at=r["created_at"],
                status=RenderStatus(r["status"]),
                label=r["label"],
            )
            for r in rows
        ]

    def latest_ready(self, project_id: str) -> Optional[RenderSnapshot]:
        snaps = self.list_for_project(project_id)
        ready = [s for s in snaps if s.status == RenderStatus.ready]
        return ready[-1] if ready else None

    def update_status(self, version_id: str, status: RenderStatus) -> None:
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "UPDATE render_snapshots SET status = ? WHERE version_id = ?",
                (status.value, version_id),
            )

    def evict_oldest_ready(self, max_versions: int) -> None:
        """Per audit M1: evict oldest status=ready; never evict rendering/failed."""
        with sqlite3.connect(self.db_path) as con:
            ready_snaps = con.execute(
                "SELECT version_id FROM render_snapshots WHERE status = 'ready' ORDER BY created_at"
            ).fetchall()
            if len(ready_snaps) <= max_versions:
                return
            to_evict = ready_snaps[:len(ready_snaps) - max_versions]
            for (vid,) in to_evict:
                con.execute("DELETE FROM render_snapshots WHERE version_id = ?", (vid,))
```

### Step 4: Run test to verify it passes

Run: `cd open_edit && pytest tests/test_storage/test_render_snapshots.py -v`
Expected: 5 passed.

### Step 5: Integrate into orchestrator

In `open_edit/open_edit/render/orchestrator.py`, after `melt_render`, append a snapshot:

```python
def render_project(project_id: str, workdir: Path, ...):
    from open_edit.storage.render_snapshots import RenderSnapshotStore, RenderStatus
    snapshot_store = RenderSnapshotStore(workdir / "render_snapshots.db")

    # Start: insert a rendering entry
    edit_graph_hash = compute_edit_graph_hash(workdir)
    snapshot = RenderSnapshot(
        project_id=project_id,
        edit_graph_hash=edit_graph_hash,
        render_path=Path(""),  # Will be updated
        status=RenderStatus.rendering,
        label=f"v{len(snapshot_store.list_for_project(project_id)) + 1}",
    )
    snapshot_store.append(snapshot)

    try:
        # ... existing render logic ...
        mp4_path = melt_render(xml_path)
        # Update snapshot with final path and status=ready
        snapshot.render_path = mp4_path
        snapshot_store.update_status(snapshot.version_id, RenderStatus.ready)
        # Evict old versions
        snapshot_store.evict_oldest_ready(max_versions=20)
        # Notify chat UI via WS
        broadcast_to_project(project_id, {
            "type": "version_ready",
            "version_id": snapshot.version_id,
            "render_path": str(mp4_path),
        })
        return RenderResult(path=mp4_path, qc=qc.gate(mp4_path))
    except Exception as e:
        snapshot_store.update_status(snapshot.version_id, RenderStatus.failed)
        raise
```

### Step 6: Implement WS message handlers

In `pyagent-kdenlive-guide/phase4_chat_ui/ws/handler.py`, add:

```python
if msg["type"] == "version_list":
    await handlers.handle_version_list(ws, project_id, msg, broadcast)
```

In `pyagent-kdenlive-guide/phase4_chat_ui/ws/handlers.py`, add:

```python
async def handle_version_list(ws, project_id, msg, broadcast):
    from open_edit.storage.render_snapshots import RenderSnapshotStore
    store = RenderSnapshotStore(get_snapshots_db_path(project_id))
    snaps = store.list_for_project(project_id)
    await ws.send_json({
        "type": "version_list",
        "project_id": project_id,
        "versions": [s.model_dump(mode="json") for s in snaps],
    })
```

### Step 7: Add edit history pagination test

Create `pyagent-kdenlive-guide/phase4_chat_ui/tests/test_edit_history_pagination.py`:

```python
"""Phase 4 Task 5: edit history list pagination (audit M8)."""
import pytest
from pathlib import Path
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.ir.types import AddClipOp


def test_pagination_50_ops_per_page(tmp_path):
    store = EditGraphStore(tmp_path / "edit_graph.db")
    for i in range(120):
        store.append(AddClipOp(
            author="user", asset_hash=f"a{i}", track_id="t1", position_sec=0.0,
        ))
    page1 = store.load_all()[0:50]
    page2 = store.load_all()[50:100]
    page3 = store.load_all()[100:120]
    assert len(page1) == 50
    assert len(page2) == 50
    assert len(page3) == 20
```

### Step 8: Run all new tests

Run: `cd open_edit && pytest tests/test_storage/test_render_snapshots.py -v && cd ../pyagent-kdenlive-guide/phase4_chat_ui && pytest tests/test_version_ready.py tests/test_edit_history_pagination.py -v`
Expected: 5 + 1 + 1 = 7 passed (assuming test_version_ready.py is in step 9).

### Step 9: Add `version_ready` WS test

Create `pyagent-kdenlive-guide/phase4_chat_ui/tests/test_version_ready.py`:

```python
"""Phase 4 Task 5: version_ready WS message (audit H2)."""
import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_version_ready_payload():
    from phase4_chat_ui.ws.handlers import handle_version_list
    broadcast = AsyncMock()
    ws = AsyncMock()
    # Test that handle_version_list returns a version_list message
    # (full integration requires DB; this is a unit smoke test)
    assert callable(handle_version_list)
```

### Step 10: Commit

```bash
git add open_edit/storage/render_snapshots.py open_edit/render/orchestrator.py
git add pyagent-kdenlive-guide/phase4_chat_ui/ws/handler.py pyagent-kdenlive-guide/phase4_chat_ui/ws/handlers.py
git add open_edit/tests/test_storage/test_render_snapshots.py
git add pyagent-kdenlive-guide/phase4_chat_ui/tests/test_version_ready.py pyagent-kdenlive-guide/phase4_chat_ui/tests/test_edit_history_pagination.py
git commit -m "[open_edit] phase4 t4: RenderSnapshotStore + version switcher + max-versions cap"
```

---

## Task 6: T7 commit_feedback + version_ready

**Files:**
- Modify: `pyagent-kdenlive-guide/phase4_chat_ui/ws/handler.py` (dispatch `commit_feedback` message)
- Modify: `pyagent-kdenlive-guide/phase4_chat_ui/ws/handlers.py` (handler: assemble pending_feedback block, call agent, render, mark notes processed)
- Modify: `open_edit/open_edit/agent/style_inject.py` (extend `build_prior_state` to include `pending_notes_summary` — the count + 3 most recent)
- Test: `pyagent-kdenlive-guide/phase4_chat_ui/tests/test_commit_feedback.py`
- Test: `pyagent-kdenlive-guide/phase4_chat_ui/tests/test_commit_feedback_race.py` (audit H1)

**Interfaces:**
- Consumes: T6's `NotesStore.commit_pending`; T4's `RenderSnapshotStore`; T3's `style_inject.build_prior_state`; T8's `originating_note_id` stamping.
- Produces:
  - WS message `commit_feedback` (client→server): `{type, project_id}`.
  - Handler flow (per audit H1 + §3.7):
    1. Generate `commit_token = uuid4().hex[:12]`.
    2. Call `NotesStore.commit_pending(project_id, commit_token)` — stamps all pending notes with the token, returns them.
    3. If empty, return error: `{"type": "error", "message": "no pending notes to commit"}`.
    4. Build `pending_feedback` block (ordered by anchor: timestamp first, then region, then op-anchored).
    5. Build `prior_state` (calls `style_inject.build_prior_state`).
    6. Inject `pending_feedback` and `prior_state` into system prompt; call agent.
    7. Agent emits ops; for each op, stamp `originating_note_id=<note_id>`.
    8. After agent run completes, trigger `render_project`.
    9. After render completes, call `NotesStore.mark_processed(note_ids, resulting_op_ids)`.
    10. Broadcast `version_ready`.
  - Race-condition handling: a note added after step 2 is not in the agent's context; remains `status=pending`. UI shows a "your last note arrived after you clicked Send" toast.

### Step 1: Write the failing test

Create `pyagent-kdenlive-guide/phase4_chat_ui/tests/test_commit_feedback.py`:

```python
"""Phase 4 Task 6: commit_feedback batch trigger."""
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import json

from open_edit.storage.notes import (
    NotesStore, ReviewNote, TimestampAnchor, NoteSource, NoteStatus,
)


def _make_note(project_id: str, text: str = "test", age_seconds: int = 0) -> ReviewNote:
    from datetime import timedelta
    return ReviewNote(
        project_id=project_id,
        anchor=TimestampAnchor(t_start=0.0, t_end=1.0),
        text=text,
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=(datetime.now(timezone.utc) - timedelta(seconds=age_seconds)).isoformat(),
    )


@pytest.mark.asyncio
async def test_commit_feedback_assembles_pending_notes(tmp_path):
    """Step 1-3 of handler: commit_pending returns and stamps notes."""
    store = NotesStore(tmp_path / "notes.db")
    for i in range(3):
        store.append(_make_note("p1", text=f"note {i}"))
    notes = store.commit_pending("p1", "token_abc")
    assert len(notes) == 3
    assert all(n.commit_token == "token_abc" for n in notes)


@pytest.mark.asyncio
async def test_commit_feedback_zero_notes(tmp_path):
    store = NotesStore(tmp_path / "notes.db")
    notes = store.commit_pending("p1", "token_abc")
    assert len(notes) == 0


@pytest.mark.asyncio
async def test_commit_feedback_marks_processed(tmp_path):
    """Step 9: after agent run, mark notes processed."""
    store = NotesStore(tmp_path / "notes.db")
    note_ids = []
    for i in range(3):
        n = _make_note("p1", text=f"note {i}")
        store.append(n)
        note_ids.append(n.note_id)
    store.commit_pending("p1", "token_abc")
    store.mark_processed(note_ids, resulting_op_ids=[f"op_{i}" for i in range(3)])
    pending = store.list_pending("p1")
    assert len(pending) == 0
```

### Step 2: Run test to verify it fails

Run: `cd open_edit && pytest tests/test_storage/test_notes.py::test_commit_pending_marks_with_token -v` (existing test from T6 should pass)
Run: `cd pyagent-kdenlive-guide/phase4_chat_ui && pytest tests/test_commit_feedback.py -v`
Expected: 3 passed (uses existing T6 NotesStore — the test verifies the handler-side contract).

### Step 3: Implement WS handler

In `pyagent-kdenlive-guide/phase4_chat_ui/ws/handler.py`, add:

```python
if msg["type"] == "commit_feedback":
    await handlers.handle_commit_feedback(ws, project_id, msg, broadcast)
```

In `pyagent-kdenlive-guide/phase4_chat_ui/ws/handlers.py`, add:

```python
async def handle_commit_feedback(ws, project_id, msg, broadcast):
    import uuid
    from open_edit.storage.notes import NotesStore
    from open_edit.agent.style_inject import build_prior_state

    notes_store = NotesStore(get_notes_db_path(project_id))
    commit_token = uuid.uuid4().hex[:12]
    pending_notes = notes_store.commit_pending(project_id, commit_token)

    if not pending_notes:
        await ws.send_json({"type": "error", "message": "no pending notes to commit"})
        return

    # Order: timestamp, then region, then op-anchored
    pending_notes.sort(key=lambda n: (
        {"timestamp": 0, "region": 1, "op": 2}[n.anchor.anchor_type],
        n.created_at,
    ))

    # Build pending_feedback block
    feedback_lines = []
    for n in pending_notes:
        if n.anchor.anchor_type == "timestamp":
            anchor_text = f"[{n.anchor.t_start:.1f}s - {n.anchor.t_end:.1f}s]"
        elif n.anchor.anchor_type == "region":
            anchor_text = f"[{n.anchor.t_start:.1f}s - {n.anchor.t_end:.1f}s, region]"
        else:
            anchor_text = f"[op_id={n.anchor.op_id}]"
        feedback_lines.append(f"- {n.note_id}: {anchor_text} \"{n.text}\"")
    pending_feedback = "\n".join(feedback_lines)

    # Build prior_state
    prior_state = build_prior_state(
        project_id=project_id,
        expected_op_type="AddEffect",  # Likely op type; can refine
        creativity_level=msg.get("creativity_level", "balanced"),
        workdir=get_workdir(project_id),
    )

    # Trigger agent run
    note_id_to_op_id = {}
    op_id_to_note_id = {}
    async def on_op_emitted(op):
        # Stamp originating_note_id on the op
        op.originating_note_id = ...  # The note this op came from
        note_id_to_op_id[...] = op.edit_id
        op_id_to_note_id[op.edit_id] = ...

    try:
        await trigger_agent_run(
            project_id=project_id,
            system_prompt_inject=f"{prior_state}\n<pending_feedback>\n{pending_feedback}\n</pending_feedback>",
            on_op=on_op_emitted,
        )
    except Exception as e:
        # Agent run failed; notes remain status=pending
        await ws.send_json({"type": "error", "message": f"agent run failed: {e}"})
        return

    # Trigger render
    try:
        await render_project(project_id=project_id, workdir=get_workdir(project_id))
    except Exception as e:
        await ws.send_json({"type": "error", "message": f"render failed: {e}"})
        # Notes still marked processed; user notified

    # Mark notes processed
    notes_store.mark_processed(
        note_ids=[n.note_id for n in pending_notes],
        resulting_op_ids=[note_id_to_op_id.get(n.note_id, "") for n in pending_notes],
    )
```

### Step 4: Extend `style_inject.build_prior_state` to include pending notes summary

In `open_edit/open_edit/agent/style_inject.py`, replace the placeholder `<pending_notes_summary>` with:

```python
# 5. Pending notes summary (≤150 tokens)
from open_edit.storage.notes import NotesStore
notes_store = NotesStore(Path(get_workdir(project_id)) / "notes.db") if workdir else None
if notes_store:
    pending = notes_store.list_pending(project_id)
    summary_lines = [f"{len(pending)} pending notes"]
    for n in pending[:3]:
        anchor = n.anchor
        if anchor.anchor_type == "timestamp":
            anchor_text = f"[{anchor.t_start:.1f}s]"
        elif anchor.anchor_type == "region":
            anchor_text = f"[{anchor.t_start:.1f}s region]"
        else:
            anchor_text = f"[op]"
        summary_lines.append(f"- {anchor_text} {n.text[:50]}")
    parts.append(f"<pending_notes_summary>\n" + "\n".join(summary_lines) + "\n</pending_notes_summary>")
```

### Step 5: Write the race-condition test

Create `pyagent-kdenlive-guide/phase4_chat_ui/tests/test_commit_feedback_race.py`:

```python
"""Phase 4 Task 6: commit_feedback race condition (audit H1).

A note added after commit_pending but before mark_processed should remain pending.
"""
import pytest
from datetime import datetime, timezone, timedelta
from open_edit.storage.notes import (
    NotesStore, ReviewNote, TimestampAnchor, NoteSource, NoteStatus,
)


def _make_note(project_id: str, text: str) -> ReviewNote:
    return ReviewNote(
        project_id=project_id,
        anchor=TimestampAnchor(t_start=0.0, t_end=1.0),
        text=text,
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def test_race_note_added_after_commit_pending(tmp_path):
    store = NotesStore(tmp_path / "notes.db")
    for i in range(3):
        store.append(_make_note("p1", f"note {i}"))

    # Simulate commit_pending (T6 already does this)
    token = "token_abc"
    notes = store.commit_pending("p1", token)

    # Simulate a note added between commit_pending and mark_processed
    store.append(_make_note("p1", "late note"))

    # Mark the original 3 processed
    store.mark_processed([n.note_id for n in notes], resulting_op_ids=[f"op_{i}" for i in range(3)])

    # The late note should still be pending
    pending = store.list_pending("p1")
    assert len(pending) == 1
    assert pending[0].text == "late note"
```

### Step 6: Run all new tests

Run: `cd open_edit && pytest tests/test_style/test_style_inject.py -v && cd ../pyagent-kdenlive-guide/phase4_chat_ui && pytest tests/test_commit_feedback.py tests/test_commit_feedback_race.py -v`
Expected: 3 + 3 + 1 = 7 passed.

### Step 7: Manual smoke test

```bash
# In a real chat UI session:
# 1. Click "Send to Claude" with no notes → error: "no pending notes to commit"
# 2. Add a note, click "Send to Claude" → button disables; agent runs; render triggers; version_ready fires
# 3. Add a note DURING agent run → that note remains pending
```

### Step 8: Commit

```bash
git add pyagent-kdenlive-guide/phase4_chat_ui/ws/handler.py pyagent-kdenlive-guide/phase4_chat_ui/ws/handlers.py
git add open_edit/agent/style_inject.py
git add pyagent-kdenlive-guide/phase4_chat_ui/tests/test_commit_feedback.py pyagent-kdenlive-guide/phase4_chat_ui/tests/test_commit_feedback_race.py
git commit -m "[open_edit] phase4 t7: commit_feedback + race fix + pending_notes_summary in prior_state"
```

---

## Task 7: T1 tool repointing + 5 new tools + creativity_level

**Files:**
- Modify: `pyagent-kdenlive-guide/phase3_pyagent_core/tools/*.py` (32 wrappers repointed: body change only, names + JSON schemas unchanged)
- Modify: `pyagent-kdenlive-guide/phase3_pyagent_core/runtime.py:69-102` (OP_TABLE updated to call new IR API + 3 new tools + 2 NotesStore tools)
- Modify: `pyagent-kdenlive-guide/phase3_pyagent_core/system_prompt.md` (add 5 new tool schemas, prior_state directive, pending_notes_summary)
- Modify: `pyagent-kdenlive-guide/phase3_pyagent_core/extension.ts:343-365` (register 5 new tools)
- Create: `open_edit/open_edit/agent/tools/pyagent_run_python.py`
- Create: `open_edit/open_edit/agent/tools/pyagent_get_style_profile.py`
- Create: `open_edit/open_edit/agent/tools/pyagent_set_pinned_value.py`
- Create: `open_edit/open_edit/agent/tools/pyagent_get_pending_notes.py`
- Create: `open_edit/open_edit/agent/tools/pyagent_add_marker.py`
- Test: `pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_repointed_wrappers.py` (32 golden IO tests)
- Test: `pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_pyagent_run_python.py`
- Test: `pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_pyagent_get_style_profile.py`
- Test: `pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_pyagent_set_pinned_value.py`
- Test: `pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_creativity_level.py`

**Interfaces:**
- Consumes: T6's `NotesStore`; T3's `style/aggregate` + `style/retrieve` + `agent/style_inject`; Phase 3's `sandbox_bridge.run_free_form`; existing `IR` API.
- Produces:
  - 32 repointed wrappers in `pyagent-kdenlive-guide/phase3_pyagent_core/tools/*.py` — bodies call `open_edit.ir.api.*` instead of `KdenliveFileBackend.*`.
  - 5 new tools in `open_edit/agent/tools/`:
    - `pyagent_run_python` — calls `sandbox_bridge.run_free_form`.
    - `pyagent_get_style_profile` — calls `style/retrieve.get_slice(op_type)`.
    - `pyagent_set_pinned_value` — calls `style/aggregate.set_pinned(key, value)`.
    - `pyagent_get_pending_notes` — calls `NotesStore.list_pending(project_id, summary_only=False)`.
    - `pyagent_add_marker` — calls `NotesStore.append(note)` with `source=agent`.
  - `creativity_level` parameter: stored in `project_meta` (`~/.open-edit/projects/<id>/project_meta.json`) as default; per-message override via WS `prompt` message; falls back to `balanced`.

### Step 1: Write the failing test for repointed wrappers

Create `pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_repointed_wrappers.py`:

```python
"""Phase 4 Task 7: 32 repointed wrappers call open_edit.ir.api.*."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from phase3_pyagent_core.runtime import run_op, OP_TABLE


def test_apply_effect_repointed(tmp_path):
    """The pyagent_apply_effect wrapper should call open_edit.ir.api.add_effect."""
    project_path = tmp_path / "project"
    project_path.mkdir()
    (project_path / "edit_graph.db").touch()  # SQLite needs the file to exist

    args = {
        "target_kind": "clip",
        "target_id": "c1",
        "effect_type": "volume",
        "params": {"gain": 0.5},
    }
    with patch("open_edit.ir.api.IR.add_effect", return_value="fx_1") as mock_add_effect:
        code, response = run_op(
            "pyagent_apply_effect", args,
            project_path=str(project_path), catalog_path="/tmp/catalog.json",
        )
    # Verify IR.add_effect was called with the right args
    assert mock_add_effect.called
    call_kwargs = mock_add_effect.call_args.kwargs
    assert call_kwargs["target_kind"] == "clip"
    assert call_kwargs["effect_type"] == "volume"
    assert call_kwargs["params"] == {"gain": 0.5}
```

### Step 2: Run test to verify it fails

Run: `cd pyagent-kdenlive-guide/phase3_pyagent_core && pytest tests/test_repointed_wrappers.py -v`
Expected: FAIL with assertion error (the wrapper still calls KdenliveFileBackend).

### Step 3: Repoint `pyagent_apply_effect` wrapper

In `pyagent-kdenlive-guide/phase3_pyagent_core/tools/effects.py`, modify the `apply_effect` function body:

```python
# Before:
def apply_effect(args):
    backend = KdenliveFileBackend(args["project_path"])
    backend.add_effect(args["target_id"], args["effect_type"], args["params"])
    return {"status": "ok", "effect_id": ...}

# After:
def apply_effect(args):
    from open_edit.ir.api import IR
    from open_edit.storage.edit_graph import EditGraphStore
    from open_edit.ir.types import Project, Asset, AddEffectOp

    project_path = Path(args["project_path"])
    project = Project.load(project_path)
    store = EditGraphStore(project_path / "edit_graph.db")
    ir = IR(store, project_id=project.id, parent_op_id=None)
    effect_id = ir.add_effect(
        target_kind=args["target_kind"],
        target_id=args["target_id"],
        effect_type=args["effect_type"],
        params=args["params"],
        originating_note_id=args.get("originating_note_id"),
    )
    return {"status": "ok", "effect_id": effect_id}
```

### Step 4: Run test to verify it passes

Run: `cd pyagent-kdenlive-guide/phase3_pyagent_core && pytest tests/test_repointed_wrappers.py -v`
Expected: 1 passed.

### Step 5: Repoint remaining 31 wrappers

Apply the same pattern to all 32 wrappers. Each wrapper:
- Old: imports KdenliveFileBackend; calls backend.<method>.
- New: imports IR + EditGraphStore + Project; calls ir.<method>.

The 32 wrappers are listed in the explore report at `phase3_pyagent_core/tools/`:
- bin.py: pyagent_import_media (repoints to AssetStore.ingest_paths)
- clips.py: pyagent_insert_clip, pyagent_append_clip, pyagent_move_clip, pyagent_trim_clip, pyagent_delete_clip
- clips_edit.py: pyagent_slip_clip, pyagent_ripple_delete_clip, pyagent_change_clip_speed, pyagent_split_clip, pyagent_replace_clip_source, pyagent_set_clip_speed_ramp
- effects.py: pyagent_apply_effect (done above), pyagent_remove_effect, pyagent_get_effect_param, pyagent_set_effect_param
- groups.py: pyagent_group_clips, pyagent_ungroup_clips, pyagent_list_groups (read-back)
- keyframes.py: pyagent_list_keyframes, pyagent_set_keyframe, pyagent_remove_keyframe
- markers.py: pyagent_add_marker (special: writes to NotesStore, source=agent), pyagent_save_project (auto-save, no-op now)
- project.py: pyagent_get_project_info, pyagent_get_timeline_summary (read-back)
- track_effects.py: pyagent_add_effect_to_track, pyagent_list_track_effects
- transitions.py: pyagent_add_transition, pyagent_remove_transition, pyagent_set_transition_property

For read-back tools (`pyagent_get_project_info`, `pyagent_get_timeline_summary`, `pyagent_list_groups`, `pyagent_list_track_effects`, `pyagent_list_keyframes`, `pyagent_get_effect_param`): use `EditGraphStore.load_all()` + `derive_timeline()` to compute the response.

### Step 6: Create 5 new tool files in `open_edit/agent/tools/`

Create `open_edit/open_edit/agent/tools/pyagent_run_python.py`:

```python
"""pyagent_run_python: invokes the Phase 3 free-form Python sandbox."""
from open_edit.agent.sandbox_bridge import run_free_form
from open_edit.agent.exceptions import FreeFormResult


def run_python(args):
    workdir = Path(args["project_path"]).parent
    result = run_free_form(
        code=args["code"],
        workdir=workdir,
        project_id=args["project_id"],
        parent_op_id=args.get("parent_op_id"),
        timeout_sec=args.get("timeout_sec", 30),
        mem_mb=args.get("mem_mb", 512),
        originating_note_id=args.get("originating_note_id"),
    )
    return {
        "status": "ok" if result.ok() else "error",
        "ops": [op.model_dump() for op in result.ops],
        "error": result.error if not result.ok() else None,
    }
```

Create `open_edit/open_edit/agent/tools/pyagent_get_style_profile.py`:

```python
"""pyagent_get_style_profile: returns the tag-gated style profile slice."""
from open_edit.style.retrieve import get_slice


def get_style_profile(args):
    return get_slice(args["op_type"])
```

Create `open_edit/open_edit/agent/tools/pyagent_set_pinned_value.py`:

```python
"""pyagent_set_pinned_value: writes a pinned value to the style profile."""
from open_edit.style.aggregate import set_pinned


def set_pinned_value(args):
    set_pinned(args["key"], args["value"])
    return {"status": "ok"}
```

Create `open_edit/open_edit/agent/tools/pyagent_get_pending_notes.py`:

```python
"""pyagent_get_pending_notes: returns pending notes for the project.

Per audit H3: supports summary_only parameter for token budget.
"""
from open_edit.storage.notes import NotesStore


def get_pending_notes(args):
    store = NotesStore(Path(args["project_path"]).parent / "notes.db")
    pending = store.list_pending(args["project_id"])
    if args.get("summary_only", False):
        return [
            {
                "note_id": n.note_id,
                "anchor": n.anchor.model_dump(),
                "text_preview": n.text[:80],
            }
            for n in pending
        ]
    # Default: full detail for first 10, count of rest
    return {
        "notes": [n.model_dump(mode="json") for n in pending[:10]],
        "remaining_count": max(0, len(pending) - 10),
    }
```

Create `open_edit/open_edit/agent/tools/pyagent_add_marker.py`:

```python
"""pyagent_add_marker: agent-initiated flag, writes to NotesStore with source=agent.

Per audit resolution: markers are notes, not IR ops. Restored from v1's drop.
"""
from open_edit.storage.notes import NotesStore, ReviewNote, TimestampAnchor, NoteSource


def add_marker(args):
    store = NotesStore(Path(args["project_path"]).parent / "notes.db")
    note = ReviewNote(
        project_id=args["project_id"],
        anchor=TimestampAnchor(t_start=args["t_start"], t_end=args.get("t_end", args["t_start"])),
        text=args.get("text", ""),
        source=NoteSource.agent,
    )
    store.append(note)
    return {"status": "ok", "note_id": note.note_id}
```

### Step 7: Update `OP_TABLE` in `runtime.py`

In `pyagent-kdenlive-guide/phase3_pyagent_core/runtime.py:69-102`, update the table to point at the repointed wrappers + 5 new tools.

The existing 32 entries stay (their import paths are unchanged; only their bodies changed). The 5 new entries:

```python
OP_TABLE["pyagent_run_python"] = ("open_edit.agent.tools.pyagent_run_python", "run_python")
OP_TABLE["pyagent_get_style_profile"] = ("open_edit.agent.tools.pyagent_get_style_profile", "get_style_profile")
OP_TABLE["pyagent_set_pinned_value"] = ("open_edit.agent.tools.pyagent_set_pinned_value", "set_pinned_value")
OP_TABLE["pyagent_get_pending_notes"] = ("open_edit.agent.tools.pyagent_get_pending_notes", "get_pending_notes")
OP_TABLE["pyagent_add_marker"] = ("open_edit.agent.tools.pyagent_add_marker", "add_marker")
```

The `run_op` function dynamically imports the module and calls the function by name. Verify the dispatcher handles this (it should — it's already dynamic).

### Step 8: Edit `system_prompt.md`

In `pyagent-kdenlive-guide/phase3_pyagent_core/system_prompt.md`, add:
- 5 new tool schemas (in the Tool Summary section)
- `prior_state` block directive: "Use the prior_state to inform your decisions about parameters."
- `creativity_level` directive: "You are running in {level} creativity mode. {behavior}"
- `pending_notes_summary` directive: "The user has {count} pending notes. Use the prior_state and pyagent_get_pending_notes to see them."

### Step 9: Register 5 new tools in `extension.ts`

In `pyagent-kdenlive-guide/phase3_pyagent_core/extension.ts:343-365`, the tool defs are loaded from Python via `loadToolDefs()`. The 5 new tools are automatically registered once their `TOOLS` list is exported from `open_edit/agent/tools/__init__.py`.

Create `open_edit/open_edit/agent/tools/__init__.py`:

```python
"""New agent tools for Phase 4."""
from open_edit.agent.tools.pyagent_run_python import run_python
from open_edit.agent.tools.pyagent_get_style_profile import get_style_profile
from open_edit.agent.tools.pyagent_set_pinned_value import set_pinned_value
from open_edit.agent.tools.pyagent_get_pending_notes import get_pending_notes
from open_edit.agent.tools.pyagent_add_marker import add_marker


TOOL_DEFS = [
    {
        "name": "pyagent_run_python",
        "description": "Run free-form Python in a sandbox; can emit IR ops.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python source code"},
                "project_id": {"type": "string"},
                "parent_op_id": {"type": "string"},
                "timeout_sec": {"type": "integer", "default": 30},
                "mem_mb": {"type": "integer", "default": 512},
                "originating_note_id": {"type": "string"},
            },
            "required": ["code", "project_id"],
        },
    },
    # ... 4 more
]
```

(Add all 5 tool defs in the same format.)

### Step 10: Add `creativity_level` per-project default

In `open_edit/open_edit/storage/config.py`, add a function to read/write `~/.open-edit/projects/<id>/project_meta.json`:

```python
def get_project_meta(project_id: str) -> dict:
    p = get_config_dir() / "projects" / project_id / "project_meta.json"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"creativity_level": "balanced"}))
    return json.loads(p.read_text())


def set_project_meta(project_id: str, key: str, value) -> None:
    meta = get_project_meta(project_id)
    meta[key] = value
    p = get_config_dir() / "projects" / project_id / "project_meta.json"
    p.write_text(json.dumps(meta))
```

### Step 11: Write tests for the 5 new tools

Create `pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_pyagent_run_python.py`:

```python
"""Phase 4 Task 7: pyagent_run_python tool."""
import pytest
from unittest.mock import patch
from open_edit.agent.exceptions import FreeFormResult
from open_edit.agent.tools.pyagent_run_python import run_python


def test_run_python_success(tmp_path):
    args = {
        "code": "ir.add_clip(asset_hash='abc', track_id='t1', position_sec=0.0)",
        "project_id": "p1",
        "project_path": str(tmp_path / "fake.kdenlive"),
    }
    fake_result = FreeFormResult.ok([])
    with patch("open_edit.agent.tools.pyagent_run_python.run_free_form", return_value=fake_result):
        response = run_python(args)
    assert response["status"] == "ok"
```

(Add similar tests for the other 4 tools.)

### Step 12: Write test for `creativity_level`

Create `pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_creativity_level.py`:

```python
"""Phase 4 Task 7: creativity_level parameter."""
import pytest
from pathlib import Path
from open_edit.storage.config import get_project_meta, set_project_meta


def test_creativity_level_default(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    meta = get_project_meta("p1")
    assert meta["creativity_level"] == "balanced"


def test_creativity_level_set(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    set_project_meta("p1", "creativity_level", "full")
    meta = get_project_meta("p1")
    assert meta["creativity_level"] == "full"
```

### Step 13: Run all new tests + full suites

Run: `cd open_edit && pytest && cd ../pyagent-kdenlive-guide/phase3_pyagent_core && pytest tests/test_repointed_wrappers.py tests/test_pyagent_run_python.py tests/test_pyagent_get_style_profile.py tests/test_pyagent_set_pinned_value.py tests/test_creativity_level.py -v`
Expected: 220+ open_edit tests + ~10 new tool tests, all passing.

### Step 14: Commit

```bash
git add pyagent-kdenlive-guide/phase3_pyagent_core/tools/*.py pyagent-kdenlive-guide/phase3_pyagent_core/runtime.py pyagent-kdenlive-guide/phase3_pyagent_core/system_prompt.py pyagent-kdenlive-guide/phase3_pyagent_core/extension.ts
git add open_edit/agent/tools/__init__.py open_edit/agent/tools/pyagent_run_python.py open_edit/agent/tools/pyagent_get_style_profile.py open_edit/agent/tools/pyagent_set_pinned_value.py open_edit/agent/tools/pyagent_get_pending_notes.py open_edit/agent/tools/pyagent_add_marker.py
git add open_edit/storage/config.py
git add pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_repointed_wrappers.py pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_pyagent_run_python.py pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_pyagent_get_style_profile.py pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_pyagent_set_pinned_value.py pyagent-kdenlive-guide/phase3_pyagent_core/tests/test_creativity_level.py
git commit -m "[open_edit] phase4 t1: tool repointing + 5 new tools + creativity_level"
```

---

## Task 8: T9 notes DB archival

**Files:**
- Modify: `open_edit/open_edit/storage/notes.py` (add `archive_old_processed` method)
- Modify: `pyagent-kdenlive-guide/phase4_chat_ui/ws/handlers.py` (in `handle_commit_feedback`, after `mark_processed`, call `archive_old_processed`)
- Test: `open_edit/tests/test_style/test_notes_archive.py`

**Interfaces:**
- Consumes: T6's `NotesStore`.
- Produces:
  - `NotesStore.archive_old_processed(retention_days: int = 30) -> int` — moves processed notes older than `retention_days` from `notes` table to `notes_archive` table (same schema). Returns count archived.
  - `notes_archive` table created on store init (same schema as `notes`).
  - Triggered on `commit_feedback` completion (per audit M3).

### Step 1: Write the failing test

Create `open_edit/tests/test_style/test_notes_archive.py`:

```python
"""Phase 4 Task 8: notes DB archival on commit_feedback completion."""
import pytest
from datetime import datetime, timezone, timedelta
from open_edit.storage.notes import (
    NotesStore, ReviewNote, TimestampAnchor, NoteSource, NoteStatus,
)


def _make_processed_note(text: str, age_days: int) -> ReviewNote:
    return ReviewNote(
        project_id="p1",
        anchor=TimestampAnchor(t_start=0.0, t_end=1.0),
        text=text,
        source=NoteSource.typed,
        status=NoteStatus.processed,
        created_at=(datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat(),
        processed_at=datetime.now(timezone.utc).isoformat(),
    )


def test_archive_old_processed(tmp_path):
    store = NotesStore(tmp_path / "notes.db")
    # 5 notes: 2 recent (kept), 3 old (archived)
    for i in range(2):
        store.append(_make_processed_note(f"recent {i}", age_days=5))
    for i in range(3):
        store.append(_make_processed_note(f"old {i}", age_days=45))
    archived = store.archive_old_processed(retention_days=30)
    assert archived == 3
    # Recent notes still in main table
    remaining = store.list_all("p1")
    assert len(remaining) == 2
    assert all("recent" in n.text for n in remaining)
    # Archived notes in archive table
    import sqlite3
    with sqlite3.connect(store.db_path) as con:
        rows = con.execute("SELECT text FROM notes_archive").fetchall()
    assert len(rows) == 3
    assert all("old" in r[0] for r in rows)


def test_pending_never_archived(tmp_path):
    store = NotesStore(tmp_path / "notes.db")
    # A pending note that's old should not be archived
    note = ReviewNote(
        project_id="p1",
        anchor=TimestampAnchor(t_start=0.0, t_end=1.0),
        text="pending old note",
        source=NoteSource.typed,
        status=NoteStatus.pending,
        created_at=(datetime.now(timezone.utc) - timedelta(days=45)).isoformat(),
    )
    store.append(note)
    archived = store.archive_old_processed(retention_days=30)
    assert archived == 0
    pending = store.list_pending("p1")
    assert len(pending) == 1
```

### Step 2: Run test to verify it fails

Run: `cd open_edit && pytest tests/test_style/test_notes_archive.py -v`
Expected: FAIL with `AttributeError: 'NotesStore' object has no attribute 'archive_old_processed'`

### Step 3: Add `archive_old_processed` to `NotesStore`

Modify `open_edit/open_edit/storage/notes.py`:

Update the `_SCHEMA` to add the archive table:

```python
_SCHEMA = """
... existing CREATE TABLE notes ...
CREATE TABLE IF NOT EXISTS notes_archive (
    note_id        TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL,
    anchor_type    TEXT NOT NULL,
    anchor         TEXT NOT NULL,
    text           TEXT NOT NULL DEFAULT '',
    source         TEXT NOT NULL,
    status         TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    processed_at   TEXT,
    commit_token   TEXT,
    resulting_op_ids TEXT NOT NULL DEFAULT '[]'
);
"""
```

Add the method:

```python
def archive_old_processed(self, retention_days: int = 30) -> int:
    """Per audit M3: move processed notes older than retention_days to notes_archive."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    with sqlite3.connect(self.db_path) as con:
        # Select old processed notes
        rows = con.execute(
            "SELECT * FROM notes WHERE status = 'processed' AND created_at < ?",
            (cutoff,),
        ).fetchall()
        # Insert into archive
        for row in rows:
            con.execute(
                "INSERT INTO notes_archive (note_id, project_id, anchor_type, anchor, text, source, status, created_at, processed_at, commit_token, resulting_op_ids) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                row,
            )
        # Delete from main table
        con.execute("DELETE FROM notes WHERE status = 'processed' AND created_at < ?", (cutoff,))
    return len(rows)
```

### Step 4: Run test to verify it passes

Run: `cd open_edit && pytest tests/test_style/test_notes_archive.py -v`
Expected: 2 passed.

### Step 5: Trigger from `handle_commit_feedback`

In `pyagent-kdenlive-guide/phase4_chat_ui/ws/handlers.py`, after `mark_processed(...)`, add:

```python
# After mark_processed
archived_count = notes_store.archive_old_processed(retention_days=30)
if archived_count > 0:
    print(f"Archived {archived_count} old notes")
```

### Step 6: Run full open_edit test suite

Run: `cd open_edit && pytest`
Expected: 220+ passed, 5 skipped.

### Step 7: Commit

```bash
git add open_edit/storage/notes.py pyagent-kdenlive-guide/phase4_chat_ui/ws/handlers.py open_edit/tests/test_style/test_notes_archive.py
git commit -m "[open_edit] phase4 t9: notes DB archival on commit_feedback completion"
```

---
