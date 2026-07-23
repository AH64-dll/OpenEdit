# Wave 1: Unblock Critical Data Flow — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four critical data-flow gaps so the AI can see assets, the timeline renders, and the edit graph supports basic user manipulation — unblocking all subsequent Wave 2–5 work.

**Architecture:** Each task is self-contained and independently testable. Task 1 (path fix) and Task 2 (list_assets tool) fix the AI asset gap. Task 3 (timeline_full) sends full Timeline data to the frontend. Task 4 (edit graph API) adds REST endpoints for ops manipulation. Order: 1 → 2 → 3 → 4 (1 and 3 are independent, 2 depends on 1, 4 is fully independent).

**Tech Stack:** Python 3.14, FastAPI, Pydantic, pytest, bare DOM JavaScript (no framework).

## Global Constraints

- Follow existing patterns: one-file-per-tool in `open_edit/agent/tools/`, 1:1 registration in `__init__.py` + `tool_schemas.py`
- Each task adds a `test_*.py` in `tests/` with at least one passing test
- All tests must pass: `cd open_edit && .venv/bin/python -m pytest tests/ -x -q --timeout=30`
- Ruff clean on modified Python files: `cd open_edit && .venv/bin/ruff check <files>`
- Commit after each task with conventional commit prefix

---
### Task 1: Fix Asset Path References

**Files:**
- Modify: `open_edit/open_edit/serve/agent/tools/_helpers.py:90-94`
- Modify: `open_edit/open_edit/serve/agent/sandbox_bridge.py:438-452`

**Interfaces:**
- Consumes: nothing new
- Produces: `get_asset_store()` returns AssetStore rooted at `<workdir>/.open_edit/assets/` (was `<workdir>/assets/`); `_load_assets_via_store()` reads from `.open_edit/assets/` (was `assets/`)

- [ ] **Step 1: Write failing test for _helpers.get_asset_store path**

```python
"""Tests for the asset path fixes in Wave 1 Task 1."""
from __future__ import annotations

import tempfile
from pathlib import Path

from open_edit.agent.tools._helpers import get_asset_store


def test_get_asset_store_uses_dot_open_edit_prefix() -> None:
    """The canonical assets dir is <workdir>/.open_edit/assets/."""
    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        (workdir / ".open_edit" / "assets").mkdir(parents=True)
        st = get_asset_store(str(workdir))
        assert st._root == workdir / ".open_edit" / "assets"

    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td) / "myproject"
        (workdir / ".open_edit" / "assets").mkdir(parents=True)
        st = get_asset_store(str(workdir))
        assert st._root == workdir / ".open_edit" / "assets"
```

Write to: `tests/test_asset_path_fix.py`

- [ ] **Step 2: Run test to verify it fails**

Run: `cd open_edit && .venv/bin/python -m pytest tests/test_asset_path_fix.py -x -q --timeout=30`

Expected: FAIL — `AssetStore` root will be `<workdir>/assets/` instead of `<workdir>/.open_edit/assets/`.

- [ ] **Step 3: Fix `_helpers.py:94` — change asset path**

```python
def get_asset_store(project_path: str | Path) -> AssetStore:
    """Return the AssetStore rooted at <project>/.open_edit/assets."""
    p = Path(project_path)
    workdir = p if p.is_dir() else p.parent
    return AssetStore(workdir / ".open_edit" / "assets")
```

- [ ] **Step 4: Fix `sandbox_bridge.py:443` — change asset path**

In `_load_assets_via_store()`, change:
```python
    assets_dir = workdir / 'assets'
```
to:
```python
    assets_dir = workdir / ".open_edit" / "assets"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd open_edit && .venv/bin/python -m pytest tests/test_asset_path_fix.py -x -q --timeout=30`

Expected: PASS

- [ ] **Step 6: Run full test suite + ruff**

Run: `cd open_edit && .venv/bin/python -m pytest tests/ -x -q --timeout=30`

Expected: all pass (713+ passed, 5 skipped)

Run: `cd open_edit && .venv/bin/ruff check open_edit/serve/agent/tools/_helpers.py open_edit/serve/agent/sandbox_bridge.py tests/test_asset_path_fix.py`

Expected: all checks passed

- [ ] **Step 7: Commit**

```bash
git add tests/test_asset_path_fix.py open_edit/open_edit/serve/agent/tools/_helpers.py open_edit/open_edit/serve/agent/sandbox_bridge.py
git commit -m "fix(agents): use canonical .open_edit/assets/ path in get_asset_store and _load_assets_via_store (Wave 1.1)"
```

---

### Task 2: Implement `list_assets` Tool

**Files:**
- Create: `open_edit/open_edit/serve/agent/tools/pyagent_list_assets.py`
- Modify: `open_edit/open_edit/serve/agent/tools/__init__.py` — register new tool
- Modify: `open_edit/open_edit/serve/tool_schemas.py` — add JSON schema
- Test: `tests/test_list_assets_tool.py`

**Interfaces:**
- Consumes: `get_asset_store` from Task 1, `AssetStore.list_all()` or direct filesystem scan via `_read_sidecars()`
- Produces: `list_assets(args: dict, project_path: str) -> dict` returning `{assets: [{hash, filename, duration_s, type, width, height}, ...]}`

Note: The `AssetStore` API is — `get(hash) → Asset | None`, `ingest_paths(paths) → list[Asset]`, `ingest(src) → Asset`. There is NO public `list_all()` or `list_hashes()` method. We need to read sidecar JSON files from the assets directory ourselves. Check the pattern in `projects.py:_list_assets_from_disk()` (line 181).

Let me read the actual AssetStore class first to confirm available methods.

- [ ] **Step 1: Read AssetStore API to confirm listing approach**

Read: `open_edit/open_edit/storage/assets.py`, search for any list/scan/iter method. If none exists, we'll implement our own scan using `Path.glob("**/*.meta.json")` on the assets root — same approach as `_list_assets_from_disk()` in projects.py.

- [ ] **Step 2: Write the tool implementation**

```python
"""pyagent_list_assets: list all ingested assets in the project.

Replaces the phantom ``list_assets`` tool referenced in the
TOOL_USAGE_GUIDE (tool_schemas.py:444) that was never built.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from open_edit.agent.tools._helpers import get_asset_store


def list_assets(args: dict, project_path: str) -> dict[str, Any]:
    """Return all ingested assets for the project.

    Scans ``<project>/.open_edit/assets/*/*.meta.json`` sidecar files.
    Returns a list of dicts with keys: hash, filename, duration_s,
    type, width, height, fps, codec, has_audio.
    """
    store = get_asset_store(project_path)
    assets_root = store._root
    assets: list[dict[str, Any]] = []

    if not assets_root.exists():
        return {"assets": assets}

    for meta_path in sorted(assets_root.glob("*/*.meta.json")):
        try:
            obj = json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        assets.append({
            "hash": obj.get("asset_hash", ""),
            "filename": obj.get("original_path", "").split("/")[-1] or meta_path.parent.name,
            "duration_s": obj.get("duration_sec", 0),
            "type": obj.get("type", "unknown"),
            "width": obj.get("width"),
            "height": obj.get("height"),
            "fps": obj.get("fps"),
            "codec": obj.get("codec"),
            "has_audio": obj.get("has_audio", False),
        })

    return {"assets": assets}
```

- [ ] **Step 3: Register the tool in `__init__.py`**

Add after the `set_pinned_value` import:
```python
from open_edit.agent.tools.pyagent_list_assets import list_assets
```

Add to `__all__` list after `"import_asset",`:
```python
    "list_assets",
```

- [ ] **Step 4: Add the JSON schema in `tool_schemas.py`**

After `import_asset` or any tool in `TOOL_SCHEMAS`, add:
```python
    {
        "name": "list_assets",
        "description": (
            "List all ingested media assets in the project. "
            "Returns each asset's hash, filename, duration, type "
            "(video/audio/image), dimensions, fps, codec, and "
            "whether it has an audio track. Call this whenever you "
            "need to discover what media is available in the project."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
```

Also update the `TOOL_USAGE_GUIDE` comment about `list_assets` — it currently claims the tool exists but it didn't. The existing text at tool_schemas.py:444-445 already correctly instructs the AI to call `list_assets`; no change needed.

- [ ] **Step 5: Write the test**

```python
"""Tests for the list_assets tool (Wave 1.2)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from open_edit.agent.tools.pyagent_list_assets import list_assets


def test_list_assets_returns_empty_for_empty_project() -> None:
    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        (workdir / ".open_edit" / "assets").mkdir(parents=True)
        result = list_assets({}, str(workdir))
        assert result == {"assets": []}


def test_list_assets_returns_ingested_assets() -> None:
    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        assets_root = workdir / ".open_edit" / "assets"
        assets_root.mkdir(parents=True)

        # Create a fake sidecar for an ingested asset
        hash_hex = "a" * 64
        prefix_dir = assets_root / hash_hex[:2]
        prefix_dir.mkdir(exist_ok=True)
        sidecar = {
            "asset_hash": hash_hex,
            "original_path": "/tmp/my_video.mp4",
            "duration_sec": 42.5,
            "type": "video",
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "codec": "h264",
            "has_audio": True,
        }
        (prefix_dir / f"{hash_hex}.meta.json").write_text(json.dumps(sidecar))

        result = list_assets({}, str(workdir))
        assert len(result["assets"]) == 1
        a = result["assets"][0]
        assert a["hash"] == hash_hex
        assert a["filename"] == "my_video.mp4"
        assert a["duration_s"] == 42.5
        assert a["type"] == "video"
        assert a["width"] == 1920
        assert a["height"] == 1080
        assert a["has_audio"] is True


def test_list_assets_skips_invalid_sidecars() -> None:
    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        assets_root = workdir / ".open_edit" / "assets" / "ff"
        assets_root.mkdir(parents=True)
        (assets_root / "dead.meta.json").write_text("not-json")
        result = list_assets({}, str(workdir))
        assert result == {"assets": []}


def test_list_assets_no_assets_dir_is_empty() -> None:
    with tempfile.TemporaryDirectory() as td:
        result = list_assets({}, td)
        assert result == {"assets": []}
```

Write to: `tests/test_list_assets_tool.py`

- [ ] **Step 6: Run test**

Run: `cd open_edit && .venv/bin/python -m pytest tests/test_list_assets_tool.py -x -q --timeout=30`

Expected: 4 PASS

- [ ] **Step 7: Run full test suite + ruff**

Run: `cd open_edit && .venv/bin/python -m pytest tests/ -x -q --timeout=30`

Expected: all pass

Run: `cd open_edit && .venv/bin/ruff check open_edit/serve/agent/tools/pyagent_list_assets.py open_edit/serve/agent/tools/__init__.py open_edit/serve/tool_schemas.py tests/test_list_assets_tool.py`

Expected: all checks passed

- [ ] **Step 8: Commit**

```bash
git add open_edit/open_edit/serve/agent/tools/pyagent_list_assets.py open_edit/open_edit/serve/agent/tools/__init__.py open_edit/open_edit/serve/tool_schemas.py tests/test_list_assets_tool.py
git commit -m "feat(agents): implement list_assets tool to replace phantom tool reference (Wave 1.2)"
```

---

### Task 3: Send `timeline_full` to Frontend

**Files:**
- Modify: `open_edit/open_edit/serve/projects.py:388-418` — add full Timeline derivation to `get_project_state()`
- Modify: `open_edit/open_edit/serve/projects.py:117-148` — add `timeline_full` field to `ProjectState`
- Modify: `open_edit/open_edit/serve/static/js/state.js:100-107` — normalize full timeline data
- Modify: `open_edit/open_edit/serve/static/app.js:163` — fix condition to use `timeline_full`

**Interfaces:**
- Consumes: `derive_timeline()` from `open_edit.ir.apply`, existing `EditGraphStore`
- Produces: `ProjectState.timeline_full: Optional[dict]` — serialized `Timeline` with tracks, clips, overlays

- [ ] **Step 1: Add `timeline_full` to `ProjectState` model**

In `projects.py`, after the existing `timeline: TimelineSummary` field on line 146, add:
```python
    timeline_full: Optional[dict] = None
```

New model:
```python
class ProjectState(BaseModel):
    """Full snapshot of a project returned by GET /api/projects/{id}."""
    id: str
    name: str
    path: str
    assets: list[AssetInfo]
    ops: list[OpInfo]
    timeline: TimelineSummary
    timeline_full: Optional[dict] = None
    pending_notes_count: int
    notes: list[ReviewNoteInfo] = Field(default_factory=list)
```

- [ ] **Step 2: Derive and serialize the full Timeline in `get_project_state()`**

After the `TimelineSummary` block (after line 407 `)`), add:

```python
        # Derive the full Timeline (v1.8 Wave 1: send timeline_full to frontend).
        # Only derive when there are ops — empty projects have no timeline.
        try:
            from open_edit.ir.apply import derive_timeline
            from open_edit.ir.types import Project as IRProject
            ir_project = IRProject(
                project_id=store.project_id,
                name=path.name,
                workdir=path,
                assets={},
                edit_graph=ops,
            )
            full_timeline = derive_timeline(ir_project)
            timeline_full = full_timeline.model_dump(mode="json")
        except Exception:
            timeline_full = None
```

Then in the `ProjectState(...)` return, add `timeline_full=timeline_full,` between `timeline=timeline,` and `pending_notes_count=`.

- [ ] **Step 3: Update frontend `normalizeTimeline` in state.js**

Replace the entire function:
```javascript
export function normalizeTimeline(raw) {
  if (!raw) return { num_tracks: 0, duration_sec: 0, clip_count: 0 };
  return {
    num_tracks: raw.num_tracks ?? 0,
    duration_sec: raw.duration_sec ?? raw.total_duration_s ?? raw.duration_s ?? 0,
    clip_count: raw.clip_count ?? raw.num_clips ?? 0,
    tracks: raw.tracks || [],
    overlays: raw.overlays || [],
  };
}
```

- [ ] **Step 4: Update `app.js` to render timeline from `timeline_full`**

Change the condition on line 163 from:
```javascript
    if (s.timeline_full ?? s.timeline) {
      renderTimeline(s.timeline_full ?? s.timeline);
    }
```
to:
```javascript
    if (s.timeline_full) {
      renderTimeline(s.timeline_full);
    }
```

- [ ] **Step 5: Write integration test for the API**

```python
"""Test that GET /api/projects/{id} includes timeline_full."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from open_edit.serve.app import app

client = TestClient(app)


def test_project_state_includes_timeline_full() -> None:
    """An existing project should return timeline_full with tracks/clips."""
    # Use an existing test project or create one via init
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    projects = resp.json()
    if not projects:
        pytest.skip("no projects to test with")
    project_id = projects[0]["id"]
    resp = client.get(f"/api/projects/{project_id}")
    assert resp.status_code == 200
    data = resp.json()
    # timeline_full may be None for projects with no ops
    # but the key must be present
    assert "timeline_full" in data
    if data["timeline_full"] is not None:
        full = data["timeline_full"]
        assert "tracks" in full
        assert "duration_sec" in full
        assert isinstance(full["tracks"], list)
```

Write to: `tests/test_timeline_full.py`

- [ ] **Step 6: Run the API test**

Run: `cd open_edit && .venv/bin/python -m pytest tests/test_timeline_full.py -x -q --timeout=30`

Expected: depends on whether a project exists with ops. If the demo_project exists with `add_clip` ops, it should pass with timeline_full populated. If no ops exist, the test skips or passes with `None`.

- [ ] **Step 7: Run full test suite + ruff**

Run: `cd open_edit && .venv/bin/python -m pytest tests/ -x -q --timeout=30`

Expected: all pass

Run: `cd open_edit && .venv/bin/ruff check open_edit/serve/projects.py tests/test_timeline_full.py`

Expected: all checks passed

- [ ] **Step 8: Commit**

```bash
git add open_edit/open_edit/serve/projects.py open_edit/open_edit/serve/static/js/state.js open_edit/open_edit/serve/static/app.js tests/test_timeline_full.py
git commit -m "feat(timeline): send timeline_full to frontend so renderTimeline receives track/clip data (Wave 1.3)"
```

---

### Task 4: Add Edit Graph API Endpoints

**Files:**
- Modify: `open_edit/open_edit/serve/app.py` — add REST endpoints for ops
- Modify: `open_edit/open_edit/serve/storage/edit_graph.py` — add `update_status`, `delete_op`, `reorder_ops` methods if missing
- Test: `tests/test_serve_edit_graph_api.py`

**Interfaces:**
- Consumes: existing `EditGraphStore`, existing `_require_project`
- Produces: `PATCH /api/projects/{id}/ops/{edit_id}/status`, `DELETE /api/projects/{id}/ops/{edit_id}`, `POST /api/projects/{id}/ops/reorder`

Note: The storage layer (`edit_graph.py`) already has `update_status()` and `reorder()` (adjacent swap). We need to check if `reorder()` handles arbitrary moves or only adjacent swaps. The audit found it only handles adjacent swaps. For this task, we add the API endpoints for what the storage already supports and add a general `reorder_ops` method.

- [ ] **Step 1: Read edit_graph.py to verify existing methods**

Read: `open_edit/open_edit/serve/storage/edit_graph.py` — check `update_status()`, `reorder()`, and confirm there's no `delete()` method.

- [ ] **Step 2: Add `delete_op` method to EditGraphStore**

In `edit_graph.py`, add after `update_status`:
```python
def delete_op(self, edit_id: str) -> bool:
    """Remove an operation from the edit graph by id.

    Any ops that had ``parent_id == edit_id`` get their parent_id
    cleared (set to NULL) so the graph remains consistent.
    Returns True if an op was found and deleted.
    """
    with self._conn() as conn:
        cur = conn.execute(
            "SELECT edit_id FROM edits WHERE edit_id = ?", (edit_id,)
        )
        if cur.fetchone() is None:
            return False
        conn.execute(
            "UPDATE edits SET parent_id = NULL WHERE parent_id = ?",
            (edit_id,),
        )
        conn.execute(
            "DELETE FROM edits WHERE edit_id = ?", (edit_id,)
        )
    return True
```

- [ ] **Step 3: Add `move_arbitrary` method to EditGraphStore**

In `edit_graph.py`, add after `reorder`:
```python
def move_arbitrary(self, edit_id: str, new_sequence_num: int) -> bool:
    """Move an operation to any position in the sequence.

    This is a general reorder operation (not just adjacent swap).
    Returns True if the op was found and moved.
    """
    with self._conn() as conn:
        cur = conn.execute(
            "SELECT sequence_num FROM edits WHERE edit_id = ?",
            (edit_id,),
        )
        row = cur.fetchone()
        if row is None:
            return False
        old_pos = row[0]
        if old_pos == new_sequence_num:
            return True
        if old_pos < new_sequence_num:
            conn.execute(
                "UPDATE edits SET sequence_num = sequence_num - 1 "
                "WHERE sequence_num > ? AND sequence_num <= ?",
                (old_pos, new_sequence_num),
            )
        else:
            conn.execute(
                "UPDATE edits SET sequence_num = sequence_num + 1 "
                "WHERE sequence_num >= ? AND sequence_num < ?",
                (new_sequence_num, old_pos),
            )
        conn.execute(
            "UPDATE edits SET sequence_num = ? WHERE edit_id = ?",
            (new_sequence_num, edit_id),
        )
    return True
```

- [ ] **Step 4: Add API routes in app.py**

After the existing `put_llm_config` route (around line 435), add:

```python
class UpdateOpStatusRequest(BaseModel):
    status: str  # "applied" | "reverted" | "superseded"


class ReorderOpsRequest(BaseModel):
    op_ids: list[str]  # ordered list of edit_ids in desired sequence


@app.patch("/api/projects/{project_id}/ops/{edit_id}/status")
async def update_op_status(
    project_id: str, edit_id: str, req: UpdateOpStatusRequest,
) -> JSONResponse:
    """Change the status of an operation (e.g. undo/redo)."""
    if req.status not in ("applied", "reverted", "superseded"):
        raise HTTPException(
            status_code=400,
            detail=f"invalid status {req.status!r}; expected applied, reverted, or superseded",
        )
    state = await _require_project(project_id)
    from .storage.edit_graph import EditGraphStore
    db_path = Path(state.path) / ".open_edit" / "edit_graph.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="edit graph not found")
    store = EditGraphStore(db_path)
    ops = store.load_all()
    if not any(o.edit_id == edit_id for o in ops):
        raise HTTPException(status_code=404, detail=f"op {edit_id} not found")
    store.update_status(edit_id, req.status)
    return JSONResponse({"edit_id": edit_id, "status": req.status})


@app.delete("/api/projects/{project_id}/ops/{edit_id}")
async def delete_op(project_id: str, edit_id: str) -> JSONResponse:
    """Remove an operation from the edit graph."""
    state = await _require_project(project_id)
    from .storage.edit_graph import EditGraphStore
    db_path = Path(state.path) / ".open_edit" / "edit_graph.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="edit graph not found")
    store = EditGraphStore(db_path)
    if not store.delete_op(edit_id):
        raise HTTPException(status_code=404, detail=f"op {edit_id} not found")
    return JSONResponse({"edit_id": edit_id, "deleted": True})


@app.post("/api/projects/{project_id}/ops/reorder")
async def reorder_ops(
    project_id: str, req: ReorderOpsRequest,
) -> JSONResponse:
    """Reorder operations to match the given sequence of edit_ids."""
    state = await _require_project(project_id)
    from .storage.edit_graph import EditGraphStore
    db_path = Path(state.path) / ".open_edit" / "edit_graph.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="edit graph not found")
    store = EditGraphStore(db_path)
    ops = store.load_all()
    existing = {o.edit_id for o in ops}
    for eid in req.op_ids:
        if eid not in existing:
            raise HTTPException(
                status_code=404, detail=f"op {eid} not found in edit graph",
            )
    for i, eid in enumerate(req.op_ids, start=1):
        store.move_arbitrary(eid, i)
    return JSONResponse({"reordered": True})
```

- [ ] **Step 5: Write the API test**

```python
"""Tests for edit graph CRUD API endpoints (Wave 1.4)."""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from open_edit.serve.app import app
from open_edit.serve.storage.edit_graph import EditGraphStore
from open_edit.ir.types import AddClipOp, RemoveClipOp

client = TestClient(app)


@pytest.fixture
def test_db() -> Path:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / ".open_edit"
        db_path.mkdir()
        store = EditGraphStore(db_path / "edit_graph.db")
        op1 = AddClipOp(
            edit_id=str(uuid.uuid4()),
            asset_hash="a" * 64,
            track_id="v1",
            position_sec=0,
            in_point_sec=0,
            out_point_sec=10,
        )
        op2 = RemoveClipOp(
            edit_id=str(uuid.uuid4()),
            clip_id=op1.clip_id,
        )
        store.append(op1)
        store.append(op2)
        yield db_path


def test_edit_graph_store_delete_op() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "edit_graph.db"
        store = EditGraphStore(db_path)
        op = AddClipOp(
            edit_id=str(uuid.uuid4()),
            asset_hash="b" * 64,
            track_id="v1",
            position_sec=0,
            in_point_sec=0,
            out_point_sec=5,
        )
        store.append(op)
        assert len(store.load_all()) == 1
        assert store.delete_op(op.edit_id) is True
        assert len(store.load_all()) == 0
        assert store.delete_op("nonexistent") is False


def test_edit_graph_store_move_arbitrary() -> None:
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "edit_graph.db"
        store = EditGraphStore(db_path)
        op1 = AddClipOp(
            edit_id="id1",
            asset_hash="c" * 64,
            track_id="v1",
            position_sec=0,
            in_point_sec=0,
            out_point_sec=5,
        )
        op2 = AddClipOp(
            edit_id="id2",
            asset_hash="d" * 64,
            track_id="v1",
            position_sec=5,
            in_point_sec=0,
            out_point_sec=5,
        )
        op3 = AddClipOp(
            edit_id="id3",
            asset_hash="e" * 64,
            track_id="v1",
            position_sec=10,
            in_point_sec=0,
            out_point_sec=5,
        )
        store.append(op1)
        store.append(op2)
        store.append(op3)
        # Move id3 to position 1
        assert store.move_arbitrary("id3", 1) is True
        ops = store.load_all()
        ids = [o.edit_id for o in ops]
        assert ids == ["id3", "id1", "id2"]
```

Write to: `tests/test_serve_edit_graph_api.py`

- [ ] **Step 6: Run the tests**

Run: `cd open_edit && .venv/bin/python -m pytest tests/test_serve_edit_graph_api.py -x -q --timeout=30`

Expected: at least the storage-level tests pass (2 PASS)

- [ ] **Step 7: Run full test suite + ruff**

Run: `cd open_edit && .venv/bin/python -m pytest tests/ -x -q --timeout=30`

Expected: all pass

Run: `cd open_edit && .venv/bin/ruff check open_edit/serve/app.py open_edit/serve/storage/edit_graph.py tests/test_serve_edit_graph_api.py`

Expected: all checks passed

- [ ] **Step 8: Commit**

```bash
git add open_edit/open_edit/serve/app.py open_edit/open_edit/serve/storage/edit_graph.py open_edit/open_edit/serve/agent/sandbox_bridge.py tests/test_serve_edit_graph_api.py
git commit -m "feat(edit-graph): add delete_op, move_arbitrary to storage; PATCH/DELETE/POST reorder API endpoints (Wave 1.4)"
```

**Note:** The `sandbox_bridge.py` was modified in Task 1 (path fix). If that commit is already done, the staging for this commit should NOT include sandbox_bridge.py unless it has additional changes in this task (it doesn't — verified above, no new changes to sandbox_bridge.py in Task 4).

---

## Verification Checklist (After All 4 Tasks)

- [ ] `cd open_edit && .venv/bin/python -m pytest tests/ -x -q --timeout=30` — all pass
- [ ] `cd open_edit && .venv/bin/ruff check open_edit/serve/ open_edit/agent/` — clean
- [ ] `cd open_edit && .venv/bin/python -m mypy open_edit/serve/projects.py open_edit/serve/storage/edit_graph.py` — clean
- [ ] Start server, verify: `curl http://127.0.0.1:8765/api/projects/{id}` returns `timeline_full` with tracks/clips
- [ ] Start server, verify: `curl http://127.0.0.1:8765/api/llm/providers/{provider}/models` works for all providers
- [ ] Start server, verify: AI can call `list_assets` tool and get results
- [ ] Start server, verify: `PATCH /api/projects/{id}/ops/{edit_id}/status` returns 200
