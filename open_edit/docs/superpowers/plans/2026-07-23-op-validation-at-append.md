# Op Validation at the Vault Door — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce op validation at `EditGraphStore.append()` so every persisted edit (from sandbox, `dev`, `bash`, or SQL) is shape-valid, reference-valid, and produces a non-overlapping timeline — while loosening the fs allow-list so the agent can read/write anywhere.

**Architecture:** Move validation into the single DB-write chokepoint (`EditGraphStore.append`) by reusing the existing `open_edit.ir.validate.validate_op` plus a new `validate_timeline` for overlap/duration checks. A new `strict=True` flag on `derive_timeline`/`derive_or_load_timeline` lets the render path catch pre-existing corruption without breaking legacy project loads. The fs allow-list's "under allowed root" restriction is removed; only the functional "contains `edit_graph.db`" check remains.

**Tech Stack:** Python 3.14, Pydantic v2 (`OperationUnion` discriminated union), SQLite (`EditGraphStore`), pytest.

## Global Constraints

- Reuse the existing `open_edit.ir.validate.validate_op(op, project, catalog=None) -> list[str]`; do NOT duplicate its logic.
- `EditGraphStore.append(op, sequence_num=None, command_id=None)` already exists at `open_edit/storage/edit_graph.py:114` — extend it, do not rename.
- `derive_timeline(project)` at `open_edit/ir/apply.py:761` and `derive_or_load_timeline(project, store=None)` at `open_edit/ir/apply.py:816` must keep backward-compatible defaults (`strict=False`) so existing callers (UI, `pi_bridge`, `cli`) are unaffected.
- No new effect types, no raw-MLT escape hatches, no network/resource hardening (per spec).
- Every task ends with a test run and a commit. TDD: write the failing test first.

---

### Task 1: Add validation primitives to `ir/validate.py`

**Files:**
- Modify: `open_edit/ir/validate.py` (import block lines 11-22; append new code after line 178)
- Test: `open_edit/tests/test_ir_validation.py` (create)

**Interfaces:**
- Produces: `OpValidationError(ValueError)`, `TimelineValidationError(ValueError)`, `validate_timeline(timeline: Timeline) -> list[str]`, `validate_op_for_append(op, store) -> list[str]`.
- Consumes: existing `validate_op` (same module), `Timeline`/`Project`/`AddClipOp` from `open_edit.ir.types`, `EditGraphStore`/`AssetStore` (duck-typed, no runtime import to avoid a circular import).

- [ ] **Step 1: Write the failing test**

```python
# open_edit/tests/test_ir_validation.py
from open_edit.ir.types import Timeline, Track, Clip
from open_edit.ir.validate import validate_timeline


def _clip(clip_id, start, in_p, out_p):
    return Clip(
        clip_id=clip_id, asset_hash="h", track_id="V1", track_kind="video",
        position_sec=start, in_point_sec=in_p, out_point_sec=out_p,
    )


def test_validate_timeline_detects_overlap():
    tl = Timeline(tracks=[Track(track_id="V1", kind="video", clips=[
        _clip("a", 0.0, 0.0, 5.0),
        _clip("b", 4.0, 0.0, 5.0),  # starts at 4.0 < a's end 5.0 -> overlap
    ])])
    errs = validate_timeline(tl)
    assert any("Overlap" in e for e in errs), errs


def test_validate_timeline_detects_nonpositive_duration():
    tl = Timeline(tracks=[Track(track_id="V1", kind="video", clips=[
        _clip("a", 0.0, 5.0, 5.0),  # out == in -> zero duration
    ])])
    errs = validate_timeline(tl)
    assert any("duration" in e.lower() for e in errs), errs


def test_validate_timeline_clean():
    tl = Timeline(tracks=[Track(track_id="V1", kind="video", clips=[
        _clip("a", 0.0, 0.0, 5.0),
        _clip("b", 5.0, 0.0, 5.0),  # abuts exactly, no overlap
    ])])
    assert validate_timeline(tl) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ah64/apps/mlt-pipeline/open_edit && .venv/bin/python -m pytest open_edit/tests/test_ir_validation.py -v`
Expected: FAIL — `ImportError` (module `open_edit.tests` may need `__init__.py`) or `AttributeError: validate_timeline`. If collection error about missing package, add `open_edit/tests/__init__.py` (empty) or run pytest from repo root with `python -m pytest tests/...`. Match the existing test layout (see `tests/test_sandbox_bridge.py` location).

- [ ] **Step 3: Write minimal implementation**

Extend the import block (lines 11-22) to include `Timeline` and `Project`:

```python
from open_edit.ir.types import (
    AddClipOp,
    AddEffectOp,
    AddTransitionOp,
    MoveClipOp,
    OperationUnion,
    Project,
    RemoveClipOp,
    SetAudioGainOp,
    SetKeyframeOp,
    Timeline,
    TrimClipOp,
)
```

Append after line 178:

```python
class OpValidationError(ValueError):
    """Raised by EditGraphStore.append when an op fails validation."""


class TimelineValidationError(ValueError):
    """Raised by derive_timeline(strict=True) when the timeline is broken."""


def validate_timeline(timeline: Timeline) -> list[str]:
    """Return timeline-level errors (empty list = valid).

    Detects overlapping clips on the same track and non-positive clip
    durations. Transitions do not create overlaps in the derived timeline
    (they trim clip boundaries to meet at the cut), so a plain interval
    check is correct.
    """
    errors: list[str] = []
    eps = 1e-6
    for track in timeline.tracks:
        clips = sorted(track.clips, key=lambda c: c.position_sec)
        for prev, cur in zip(clips, clips[1:]):
            prev_end = prev.position_sec + (prev.out_point_sec - prev.in_point_sec)
            if prev_end > cur.position_sec + eps:
                errors.append(
                    f"Overlap on track {track.track_id}: clip {prev.clip_id!r} "
                    f"spans [{prev.position_sec:.3f}, {prev_end:.3f}] but clip "
                    f"{cur.clip_id!r} starts at {cur.position_sec:.3f}."
                )
        for c in track.clips:
            dur = c.out_point_sec - c.in_point_sec
            if dur <= 0:
                errors.append(
                    f"Clip {c.clip_id!r} has non-positive duration ({dur:.3f}s)."
                )
    return errors


def validate_op_for_append(op: OperationUnion, store) -> list[str]:
    """Validate one op against the store's current project state.

    Builds a lightweight Project from the store (current ops + assets) and
    delegates to :func:`validate_op`. ``store`` is duck-typed (must expose
    ``load_all()``, ``db_path``, ``project_id``). No runtime import of
    EditGraphStore here to avoid a circular import.
    """
    from open_edit.storage.assets import AssetStore

    ops = store.load_all()
    assets: dict = {}
    db_parent = store.db_path.parent
    direct = db_parent / "assets"
    assets_dir = direct if direct.is_dir() else db_parent / ".open_edit" / "assets"
    if assets_dir.is_dir():
        astore = AssetStore(assets_dir)
        for o in ops:
            if isinstance(o, AddClipOp) and o.asset_hash not in assets:
                a = astore.get(o.asset_hash)
                if a is not None:
                    assets[o.asset_hash] = a
    project = Project(
        project_id=store.project_id,
        name=db_parent.name,
        workdir=db_parent,
        assets=assets,
        edit_graph=ops,
    )
    return validate_op(op, project)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/ah64/apps/mlt-pipeline/open_edit && .venv/bin/python -m pytest open_edit/tests/test_ir_validation.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add open_edit/ir/validate.py open_edit/tests/test_ir_validation.py
git commit -m "feat(ir): add validate_timeline + append-validation helpers"
```

---

### Task 2: Enforce validation in `EditGraphStore.append`

**Files:**
- Modify: `open_edit/storage/edit_graph.py` (add import after line 18; add `import threading` + module lock near top; modify `append` lines 114-145)
- Test: `open_edit/tests/test_edit_graph_append_validation.py` (create)

**Interfaces:**
- Consumes: `open_edit.ir.validate.validate_op_for_append`, `OpValidationError`.
- Produces: `append` now raises `OpValidationError` on invalid ops; otherwise persists as before.

- [ ] **Step 1: Write the failing test**

```python
# open_edit/tests/test_edit_graph_append_validation.py
import pytest
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.ir.validate import OpValidationError
from open_edit.ir.types import TrimClipOp, AddClipOp


def test_append_dangling_reference_rejected(tmp_path):
    store = EditGraphStore(tmp_path / "edit_graph.db")
    # TrimClipOp references a clip_id that does not exist in the project.
    op = TrimClipOp(
        clip_id="does_not_exist", new_in_point_sec=0.0,
        new_out_point_sec=1.0, author="ai",
    )
    with pytest.raises(OpValidationError):
        store.append(op)
    # Nothing was written.
    assert store.load_all() == []


def test_append_valid_op_persists(monkeypatch, tmp_path):
    from open_edit.ir import validate as _v
    # Isolate append's own persist path from asset/catalog checks.
    monkeypatch.setattr(_v, "validate_op_for_append", lambda op, s: [])
    store = EditGraphStore(tmp_path / "edit_graph.db")
    op = AddClipOp(asset_hash="h", track_id="V1", position_sec=0.0, author="ai")
    n = store.append(op)
    assert n == 0
    assert store.load_all()[0].clip_id == op.clip_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ah64/apps/mlt-pipeline/open_edit && .venv/bin/python -m pytest open_edit/tests/test_edit_graph_append_validation.py -v`
Expected: FAIL — `test_append_dangling_reference_rejected` raises nothing (op currently persisted without validation).

- [ ] **Step 3: Write minimal implementation**

Add near the top of `edit_graph.py` (after line 18 `from open_edit.ir.types import OperationUnion, new_id`):

```python
import threading

from open_edit.ir import validate as _ir_validate

_APPEND_LOCK = threading.Lock()
```

Modify `append` (lines 114-145) to validate first and wrap the insert in the lock:

```python
    def append(
        self, op: OperationUnion, sequence_num: int | None = None,
        command_id: str | None = None,
    ) -> int:
        """Append an operation. Returns the assigned sequence_num.

        Validates the op against the current project state (shape +
        references) before persisting. Raises OpValidationError on failure;
        the op is NOT written.
        """
        errors = _ir_validate.validate_op_for_append(op, self)
        if errors:
            raise _ir_validate.OpValidationError("; ".join(errors))
        with _APPEND_LOCK:
            with self._conn() as conn:
                if sequence_num is None:
                    cur = conn.execute(
                        "SELECT COALESCE(MAX(sequence_num), -1) + 1 FROM edits"
                    )
                    sequence_num = cur.fetchone()[0]
                conn.execute(
                    "INSERT INTO edits "
                    "(edit_id, parent_id, kind, author, timestamp, status, "
                    " sequence_num, payload) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        op.edit_id, op.parent_id, op.kind, op.author, op.timestamp,
                        op.status, sequence_num, op.model_dump_json(),
                    ),
                )
                conn.execute(
                    "INSERT INTO edit_status_events "
                    "(event_id, edit_id, from_status, to_status, command_id, "
                    " reason, changed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        new_id(), op.edit_id, None, op.status or "applied",
                        command_id, "append", op.timestamp or self._now_iso(),
                    ),
                )
        return sequence_num
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/ah64/apps/mlt-pipeline/open_edit && .venv/bin/python -m pytest open_edit/tests/test_edit_graph_append_validation.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add open_edit/storage/edit_graph.py open_edit/tests/test_edit_graph_append_validation.py
git commit -m "feat(storage): validate ops at append (vault-door guard)"
```

---

### Task 3: Add `strict` overlap checking to `derive_timeline`

**Files:**
- Modify: `open_edit/ir/apply.py` (`derive_timeline` line 761; `derive_or_load_timeline` line 816)
- Test: extend `open_edit/tests/test_ir_validation.py`

**Interfaces:**
- Consumes: `open_edit.ir.validate.validate_timeline`, `TimelineValidationError`.
- Produces: `derive_timeline(project, strict=False)` and `derive_or_load_timeline(project, store=None, strict=False)`.

- [ ] **Step 1: Write the failing test**

Append to `open_edit/tests/test_ir_validation.py`:

```python
from open_edit.ir.apply import derive_timeline, TimelineValidationError
from open_edit.ir.types import Project


def _overlapping_project():
    # A project whose derived timeline has two overlapping clips on V1.
    from open_edit.ir.types import AddClipOp
    ops = [
        AddClipOp(asset_hash="h", track_id="V1", position_sec=0.0,
                  in_point_sec=0.0, out_point_sec=5.0, author="ai"),
        AddClipOp(asset_hash="h", track_id="V1", position_sec=4.0,
                  in_point_sec=0.0, out_point_sec=5.0, author="ai"),
    ]
    return Project(project_id="p", name="p", workdir="/tmp", assets={}, edit_graph=ops)


def test_derive_timeline_strict_raises_on_overlap():
    with pytest.raises(TimelineValidationError):
        derive_timeline(_overlapping_project(), strict=True)


def test_derive_timeline_lenient_loads_overlap():
    # Default stays lenient so legacy projects still load.
    tl = derive_timeline(_overlapping_project(), strict=False)
    assert any(len(t.clips) == 2 for t in tl.tracks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ah64/apps/mlt-pipeline/open_edit && .venv/bin/python -m pytest open_edit/tests/test_ir_validation.py -v`
Expected: FAIL — `strict=True` does not yet raise.

- [ ] **Step 3: Write minimal implementation**

In `derive_timeline` (line 761), change the signature and add the strict check before `return timeline` (after line 812):

```python
def derive_timeline(project: Project, strict: bool = False) -> Timeline:
    """Replay all non-reverted, applied operations in sequence order.

    When ``strict=True``, raise TimelineValidationError if the resulting
    timeline has overlaps or non-positive-duration clips.
    """
    timeline = Timeline()
    ...
    timeline.duration_sec = max_end
    if strict:
        from open_edit.ir.validate import validate_timeline, TimelineValidationError
        errs = validate_timeline(timeline)
        if errs:
            raise TimelineValidationError("; ".join(errs))
    return timeline
```

In `derive_or_load_timeline` (line 816), add `strict: bool = False` and pass it through at line 838:

```python
def derive_or_load_timeline(project: Project, store=None, strict: bool = False) -> Timeline:
    ...
    tl = derive_timeline(project, strict=strict)
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/ah64/apps/mlt-pipeline/open_edit && .venv/bin/python -m pytest open_edit/tests/test_ir_validation.py -v`
Expected: PASS (all tests in file).

- [ ] **Step 5: Commit**

```bash
git add open_edit/ir/apply.py open_edit/tests/test_ir_validation.py
git commit -m "feat(ir): strict timeline validation on derive"
```

---

### Task 4: Render path uses `strict=True`

**Files:**
- Modify: `open_edit/render/orchestrator.py:83` (`derive_or_load_timeline(project, store)` → `derive_or_load_timeline(project, store, strict=True)`)

**Interfaces:**
- Consumes: `derive_or_load_timeline(..., strict=True)`.
- Produces: broken timelines now fail the render with a `TimelineValidationError` instead of producing a corrupt MLT.

- [ ] **Step 1: Write the failing test**

Add to `open_edit/tests/test_edit_graph_append_validation.py` (or a new render test) — verify the render entry rejects an overlapping project:

```python
from open_edit.ir.apply importderive_or_load_timeline, TimelineValidationError
from open_edit.ir.types import Project, AddClipOp


def test_render_derive_strict_rejects_overlap(tmp_path):
    store = EditGraphStore(tmp_path / "edit_graph.db")
    store.append(AddClipOp(asset_hash="h", track_id="V1", position_sec=0.0,
                           in_point_sec=0.0, out_point_sec=5.0, author="ai"))
    store.append(AddClipOp(asset_hash="h", track_id="V1", position_sec=4.0,
                           in_point_sec=0.0, out_point_sec=5.0, author="ai"))
    ops = store.load_all()
    proj = Project(project_id="p", name="p", workdir=tmp_path, assets={}, edit_graph=ops)
    with pytest.raises(TimelineValidationError):
        derive_or_load_timeline(proj, store, strict=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ah64/apps/mlt-pipeline/open_edit && .venv/bin/python -m pytest open_edit/tests/test_edit_graph_append_validation.py -v`
Expected: FAIL — `derive_or_load_timeline(..., strict=True)` not yet implemented (Task 3) or not invoked; once Task 3 lands this passes without code change here. If Task 3 is merged, this step still documents the wiring.

- [ ] **Step 3: Wire the render path**

In `open_edit/render/orchestrator.py` line 83, change:

```python
    timeline = derive_or_load_timeline(project, store, strict=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/ah64/apps/mlt-pipeline/open_edit && .venv/bin/python -m pytest open_edit/tests/test_edit_graph_append_validation.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add open_edit/render/orchestrator.py open_edit/tests/test_edit_graph_append_validation.py
git commit -m "feat(render): fail render on broken (overlapping) timeline"
```

---

### Task 5: Loosen the fs allow-list

**Files:**
- Modify: `open_edit/agent/sandbox_bridge.py` (`_validate_workdir` lines 196-224; remove `_get_allowed_roots` lines 174-193 and `_is_under` if it becomes unused)
- Test: `open_edit/tests/test_sandbox_bridge.py` (update the assertion around line 350 that expects rejection outside the allowed root)

**Interfaces:**
- Produces: `_validate_workdir` now only checks (a) is a directory, (b) contains `edit_graph.db`. It no longer checks the allowed-root membership.

- [ ] **Step 1: Update the test to the new behavior**

In `open_edit/tests/test_sandbox_bridge.py`, find the test that asserts a workdir outside `OPEN_EDIT_PROJECTS_ROOT` is rejected (around line 350). Change its expectation: a workdir that exists and contains `edit_graph.db` is now accepted regardless of root. Read the test, then replace the `pytest.raises(ValueError)` with an assertion that `_validate_workdir(bad_but_real_project_dir)` returns that path.

- [ ] **Step 2: Run the test to verify it fails (old expectation)**

Run: `cd /home/ah64/apps/mlt-pipeline/open_edit && .venv/bin/python -m pytest open_edit/tests/test_sandbox_bridge.py -v`
Expected: FAIL on the now-outdated rejection assertion.

- [ ] **Step 3: Write minimal implementation**

In `sandbox_bridge.py`, remove `_get_allowed_roots` (lines 174-193) and the root-membership block in `_validate_workdir` (lines 210-216), keeping the directory + `edit_graph.db` checks:

```python
def _validate_workdir(workdir: Path) -> Path:
    """P9: resolve a caller-supplied workdir.

    The AI may operate on any directory; we only require that it is a real
    project (contains ``edit_graph.db``) so the store can locate its DB.
    No root/allow-list restriction is applied.
    """
    workdir = Path(workdir).resolve()
    if not workdir.is_dir():
        raise ValueError(f"workdir {workdir} is not a directory")
    if not (workdir / "edit_graph.db").exists():
        raise ValueError(
            f"workdir {workdir} is not a valid project directory "
            f"(missing edit_graph.db)"
        )
    return workdir
```

Remove `_is_under` if it is now referenced nowhere else (grep first). Remove the now-unused `import` of anything only `_get_allowed_roots` used.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /home/ah64/apps/mlt-pipeline/open_edit && .venv/bin/python -m pytest open_edit/tests/test_sandbox_bridge.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add open_edit/agent/sandbox_bridge.py open_edit/tests/test_sandbox_bridge.py
git commit -m "feat(sandbox): drop fs allow-list root restriction"
```

---

### Task 6: Switch active sandbox backend to `dev` (operational)

**Files:**
- No code change. Configure the running server.

**Interfaces:**
- Sets `OPEN_EDIT_SANDBOX_BACKEND=dev` so free-form code runs without OS isolation (validation + append lock remain).

- [ ] **Step 1: Set the env var for the server and persist it**

Add to your shell rc (e.g. `~/.zshrc` or `~/.bashrc`):

```bash
export OPEN_EDIT_SANDBOX_BACKEND=dev
export OPEN_EDIT_PROJECTS_ROOT=/home/ah64/OpenEditProjects
```

- [ ] **Step 2: Restart the server**

Find and stop the running server, then start it with the new env. The existing live server is on `127.0.0.1:8765`. After restart, confirm a free-form run still produces validated ops and that `dev` is reported in the server log.

- [ ] **Step 3: Smoke-test a free-form edit**

Trigger one agent `edit_project`/free-form action on a test project and confirm in `/tmp/open-edit-server.log` that ops are validated at append (no regressions) and the run completes.

---

## Self-Review Notes

- Spec coverage: shape+reference validation at append (Task 2) ✓; overlap/non-positive-duration detection (Tasks 1, 3) ✓; read-side strict opt-in keeping legacy loads (Task 3 default False) ✓; render uses strict (Task 4) ✓; fs allow-list loosened (Task 5) ✓; minimal non-blocking append lock (Task 2 `_APPEND_LOCK`) ✓; no internet/resource limits added ✓.
- No placeholders; every code step is complete.
- Type consistency: `validate_timeline(timeline)`, `validate_op_for_append(op, store)`, `OpValidationError`, `TimelineValidationError` are defined in Task 1 and consumed in Tasks 2-4 with matching names. `derive_timeline(project, strict=False)` / `derive_or_load_timeline(project, store, strict=False)` signatures match across Task 3 and Task 4.
- The existing `_validate_ops_incrementally` (sandbox_bridge.py) remains as a pre-persist check; `append` adds a second, source-agnostic guard — both use the same underlying reference rules, so behavior is consistent, not contradictory.
