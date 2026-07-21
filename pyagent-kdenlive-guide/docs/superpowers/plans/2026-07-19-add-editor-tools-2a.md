# PyAgent for Kdenlive — Sub-project 2a: Core Editor Tools Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 10 new editor tools to pyagent (slip, ripple, speed, split, replace, remove_effect, remove_transition, group, ungroup, list_groups) using the existing per-domain pattern, with real-Kdenlive interop for the groups feature. 4 commits, ~252 collected tests post-merge.

**Architecture:** Per-domain ops functions in `phase2_project_engine/ops/<domain>.py`, ToolDef dataclasses in `phase3_pyagent_core/tools/<domain>.py`, OP_TABLE + MUTATING_OPS entries in `runtime.py`, golden-file fixtures in `phase3_pyagent_core/tests/fixtures/golden_io.json`, per-tool behavior tests in `phase2_project_engine/tests/test_ops_<domain>.py`, and one real-Kdenlive interop test in `phase7_real_session/tests/test_e2e.py`. Groups data is stored in `kdenlive:sequenceproperties.groups` on the tractor as a JSON array of `{type, pyagent:name, children}` objects using Kdenlive's real format. The TypeScript extension auto-discovers tools via `runtime.list_tools()` — no TS changes required.

**Tech Stack:** Python 3.11+, lxml, pytest; existing `phase2_project_engine` and `phase3_pyagent_core` modules. No new dependencies. No TypeScript changes. No Godot patterns.

## Global Constraints

These are the spec's project-wide rules. Every task's requirements implicitly include this section.

- **Python 3.11+** only; keep `from __future__ import annotations` imports.
- **Three error classes** (existing): `BackendError`, `ValidationError`, `NotFoundError` — defined in `phase2_project_engine/errors.py`. **No new error classes.**
- **All errors** raised to the LLM carry a `fix:` hint line (use `validation_error()` for `ValidationError`).
- **File naming**: snake_case, no spaces, no CamelCase.
- **Module size budget**: every production file <300 lines; every test file <400 lines. Split if a file needs to grow.
- **Tool I/O**: each of the 10 new tools' JSON output is locked by a golden-file test. Any drift fails the build.
- **Group storage**: must use `kdenlive:sequenceproperties.groups` on the tractor (verified against Kdenlive master source). JSON array, no envelope. `pyagent:name` is a side-channel field (Kdenlive ignores unknown fields).
- **group_name uniqueness**: enforced at write time (raise `duplicate_group_name` `ValidationError` if name already exists).
- **Auto-save after any mutating op**: runtime adds the 9 mutating tools to `MUTATING_OPS`; `list_groups` is read-only.
- **Bug policy**: every bug found during 2a implementation MUST be fixed with a regression test before that task's commit lands. Log to `BUGS_FIXED.md` (one line per bug, with `file:line`).
- **Commit format**: `[<system>] add <short summary>`. Use `[clips-edit]`, `[effects]`, `[transitions]`, `[groups]`, or `[setup]` as the system prefix.
- **Working tree state**: at every commit boundary, `PYTHONPATH=. pytest -q` is green. Never commit red.
- **No behavior change** for the 19 existing tools' I/O.
- **TypeScript extension**: NO changes required. `extension.ts:62-65` calls `runtime.list_tools()` at load time and iterates the result. New tools are auto-exposed.

## File Structure (post-2a)

```
pyagent-kdenlive-guide/
  phase2_project_engine/
    ops/
      bin.py            (unchanged)
      clips.py          (unchanged: 5 placement ops)
      clips_edit.py     (NEW: slip_clip, ripple_delete_clip,
                          change_clip_speed, split_clip,
                          replace_clip_source)
      effects.py        (extended: +remove_effect)
      transitions.py    (extended: +remove_transition)
      markers.py        (unchanged)
      groups.py         (NEW: group_clips, ungroup_clips, list_groups)
      _helpers.py       (unchanged)
      __init__.py       (extended: +clips_edit, +groups exports)
    tests/
      test_ops_clips.py        (extended: +5 test functions)
      test_ops_effects.py      (extended: +1 test function)
      test_ops_transitions.py  (extended: +1 test function)
      test_ops_groups.py       (NEW: 3 test functions)
  phase3_pyagent_core/
    tools/
      bin.py            (unchanged)
      catalog.py        (unchanged)
      clips.py          (unchanged: 5 ToolDefs)
      clips_edit.py     (NEW: 5 ToolDefs)
      effects.py        (extended: +1 ToolDef)
      transitions.py    (extended: +1 ToolDef)
      markers.py        (unchanged)
      project.py        (unchanged)
      render_qc.py      (unchanged)
      groups.py         (NEW: 3 ToolDefs)
      __init__.py       (extended: +clips_edit, +groups)
    runtime.py          (extended: +10 OP_TABLE, +9 MUTATING_OPS)
    tests/
      test_golden_io.py       (extended: +10 parametrized cases)
      fixtures/
        golden_io.json        (extended: +10 entries)
  phase7_real_session/
    tests/
      test_e2e.py             (extended: +1 interop test,
                                skipif_kdenlive_missing)
  BUGS_FIXED.md          (updated with 2a bugs if any)
```

## Source-of-truth references

Before starting a task, read:
- The spec: `docs/superpowers/specs/2026-07-19-add-editor-tools-2a-design.md`
- The existing patterns: `phase2_project_engine/ops/clips.py` (placement ops), `phase2_project_engine/ops/effects.py` (apply_effect), `phase2_project_engine/tests/test_ops_clips.py` (integration test style), `phase3_pyagent_core/tools/clips.py` (ToolDef style), `phase3_pyagent_core/tests/test_golden_io.py` (golden test style).

---

### Task 0.1: Set up branch + worktree + verify baseline

**Files:**
- No code changes.

- [ ] **Step 1: Create branch `add-editor-tools-2a` from `main`**

Run from the repo root (`/home/ah64/apps/mlt-pipeline/pyagent-kdenlive-guide`):
```bash
cd /home/ah64/apps/mlt-pipeline
git fetch origin main 2>/dev/null || true
git checkout main
git pull 2>/dev/null || true
git worktree add ../mlt-pipeline-2a -b add-editor-tools-2a
cd ../mlt-pipeline-2a
```

Expected: New worktree at `../mlt-pipeline-2a`, branch checked out, no errors.

- [ ] **Step 2: Verify clean baseline**

Run from the new worktree:
```bash
cd /home/ah64/apps/mlt-pipeline-2a/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest -q --no-header
```

Expected: `230 passed, 1 skipped, 1 warning in ~80s`.

If the count differs, STOP. Do not proceed; the cleanup sub-project is not at the agreed baseline.

- [ ] **Step 3: Verify extension auto-discovers 19 tools**

Run from the worktree:
```bash
cd /home/ah64/apps/mlt-pipeline-2a/pyagent-kdenlive-guide
PYTHONPATH=. python3 -c "from phase3_pyagent_core.runtime import list_tools; print(len(list_tools()))"
```

Expected: `19`.

- [ ] **Step 4: Commit the worktree (no code yet — just the branch)**

```bash
cd /home/ah64/apps/mlt-pipeline-2a
git status
```

Expected: clean (no uncommitted changes). If there's anything, STOP and report.

---

### Task 1: Commit 1 — clips-edit (5 tools)

This task adds 5 new clip-edit operations: `slip_clip`, `ripple_delete_clip`, `change_clip_speed`, `split_clip`, `replace_clip_source`.

**Files:**
- Create: `phase2_project_engine/ops/clips_edit.py`
- Create: `phase3_pyagent_core/tools/clips_edit.py`
- Modify: `phase2_project_engine/ops/__init__.py` (add 5 exports)
- Modify: `phase3_pyagent_core/tools/__init__.py` (import clips_edit, add to all_tools)
- Modify: `phase3_pyagent_core/runtime.py` (add 5 OP_TABLE entries, 5 MUTATING_OPS entries)
- Modify: `phase2_project_engine/tests/test_ops_clips.py` (add 5 test functions)
- Modify: `phase3_pyagent_core/tests/fixtures/golden_io.json` (add 5 entries)

**Interfaces this task produces** (later tasks depend on these):
- `ops.clips_edit.slip_clip(tree, clip_id, delta_sec) -> dict`
- `ops.clips_edit.ripple_delete_clip(tree, clip_id) -> dict`
- `ops.clips_edit.change_clip_speed(tree, clip_id, rate) -> dict`
- `ops.clips_edit.split_clip(tree, clip_id, at_sec) -> dict`
- `ops.clips_edit.replace_clip_source(tree, clip_id, new_source_id) -> dict`
- `tools.clips_edit.SLIP_CLIP`, `RIPPLE_DELETE_CLIP`, `CHANGE_CLIP_SPEED`, `SPLIT_CLIP`, `REPLACE_CLIP_SOURCE` (ToolDef instances)
- `runtime.OP_TABLE` keys: `slip_clip`, `ripple_delete_clip`, `change_clip_speed`, `split_clip`, `replace_clip_source`
- `runtime.MUTATING_OPS` adds: same 5 names

#### Step 1: Create `phase2_project_engine/ops/clips_edit.py` (skeleton)

Create the file with the 5 function signatures and docstrings. The implementations are added in steps 2-6.

```python
"""Clip-edit operations: slip / ripple-delete / speed / split / replace.

These are the "modification" ops (transforming an existing clip in
place or splitting it). The "placement" ops (insert/append/move/
trim/delete) live in `clips.py`. The split is a deliberate
per-domain choice driven by the 300-line module-size cap.
"""
from __future__ import annotations

from lxml import etree

from ..errors import NotFoundError, validation_error
from ..io import ProjectTree
from ..tracks import (
    find_all_entries, get_tracks, get_video_playlist,
    next_kdenlive_id, resolve_producer, resolve_source_duration,
)
from ..validators import (
    validate_position_sec, validate_track_index,
)
from ._helpers import (
    insert_entry_at_position, playlist_duration,
    shift_entry_on_timeline,
)


# --- Internal helpers (shared by the 5 ops) -------------------------------

def _find_entry_for_clip(tree: ProjectTree, clip_id: str) -> tuple[etree._Element, etree._Element, int]:
    """Return (track, entry, track_index) for a given clip_id, or raise NotFoundError."""
    for ti, track in enumerate(get_tracks(tree)):
        for entry in track.iter("entry"):
            if entry.get("kdenlive:id") == clip_id or _entry_kid(entry) == clip_id:
                return track, entry, ti
    raise NotFoundError(
        f"clip_not_found: clip_id={clip_id!r}\n"
        f"fix: call get_timeline_summary and re-pick"
    )


def _entry_kid(entry: etree._Element) -> str | None:
    """Extract the kdenlive:id of an entry (it's a kdenlive:id child of the producer)."""
    producer = entry.find("producer")
    if producer is None:
        return None
    kid_prop = producer.find("property[@name='kdenlive:id']")
    return kid_prop.text if kid_prop is not None else None


# --- Public ops ------------------------------------------------------------

def slip_clip(tree: ProjectTree, clip_id: str, delta_sec: float) -> dict:
    """Slip the clip: shift source in/out by `delta_sec` while keeping
    the timeline window fixed. Raises `source_oob` NotFoundError if the
    new source range is outside the source media.
    """
    raise NotImplementedError


def ripple_delete_clip(tree: ProjectTree, clip_id: str) -> dict:
    """Remove the clip and close the gap on the same track by shifting
    all following clips left by the deleted duration.
    """
    raise NotImplementedError


def change_clip_speed(tree: ProjectTree, clip_id: str, rate: float) -> dict:
    """Change the playback rate (1.0 = normal, 2.0 = 2x faster, 0.5 = 2x slower).
    Rate must be in [0.1, 10.0].
    """
    raise NotImplementedError


def split_clip(tree: ProjectTree, clip_id: str, at_sec: float) -> dict:
    """Split the clip at `at_sec` (a timeline-relative position within
    the clip's range). Returns the left (original) and right (new) clip ids.
    """
    raise NotImplementedError


def replace_clip_source(tree: ProjectTree, clip_id: str, new_source_id: str) -> dict:
    """Replace the clip's source media. Resets rate to 1.0. New duration
    = min(old_timeline_duration, new_source_duration).
    """
    raise NotImplementedError
```

#### Step 2: Add 5 integration tests in `test_ops_clips.py`

Open `phase2_project_engine/tests/test_ops_clips.py` and append these 5 test functions at the end of the file (read the existing file first to copy the imports + fixtures pattern; the file already imports from `phase2_project_engine.tests.ops_fixtures`):

```python
def test_slip_clip_shifts_source_within_fixed_window():
    """slip with delta=+1.0 shifts source_in and source_out each by 1.0;
    timeline position and duration are unchanged. Reaches into the
    source via the producer reference (same as trim_clip does)."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.clips_edit import slip_clip
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                      source_in_sec=0.0, source_out_sec=5.0)
    pre = slip_clip(tree, kid, delta_sec=0.0)
    post = slip_clip(tree, kid, delta_sec=1.0)
    # Source in/out shifted by 1.0
    assert abs(post["source_in_sec"] - (pre["source_in_sec"] + 1.0)) < 1e-6
    assert abs(post["source_out_sec"] - (pre["source_out_sec"] + 1.0)) < 1e-6
    # Timeline window unchanged
    assert post["timeline_start_sec"] == pre["timeline_start_sec"]
    assert post["duration_sec"] == pre["duration_sec"]


def test_slip_clip_raises_source_oob_on_out_of_bounds_delta():
    """A delta that would push source_in below 0 raises source_oob."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.clips_edit import slip_clip
    from phase2_project_engine.errors import NotFoundError
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                      source_in_sec=0.0, source_out_sec=5.0)
    with pytest.raises(NotFoundError) as exc:
        slip_clip(tree, kid, delta_sec=-100.0)
    assert "source_oob" in str(exc.value)


def test_change_clip_speed_halves_duration_at_rate_2():
    """rate=2.0 halves the clip's duration on the timeline."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.clips_edit import change_clip_speed
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                      source_in_sec=0.0, source_out_sec=10.0)
    pre_dur = change_clip_speed(tree, kid, rate=1.0)["new_duration_sec"]
    result = change_clip_speed(tree, kid, rate=2.0)
    assert abs(result["new_duration_sec"] - pre_dur / 2.0) < 1e-3
    assert result["rate"] == 2.0


def test_change_clip_speed_rejects_rate_out_of_range():
    """rate > 10.0 raises rate_out_of_range ValidationError."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.clips_edit import change_clip_speed
    from phase2_project_engine.errors import ValidationError
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                      source_in_sec=0.0, source_out_sec=5.0)
    with pytest.raises(ValidationError) as exc:
        change_clip_speed(tree, kid, rate=11.0)
    assert "rate_out_of_range" in str(exc.value)
    assert "fix:" in str(exc.value)


def test_split_clip_returns_left_and_right_clip_ids():
    """split returns the original clip_id (left) and a new id (right)."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.clips_edit import split_clip
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                      source_in_sec=0.0, source_out_sec=10.0)
    result = split_clip(tree, kid, at_sec=4.0)
    assert result["left_clip_id"] == kid
    assert result["right_clip_id"] != kid
    assert result["right_clip_id"].isdigit()
```

(The 5 tests above cover the spec's required behaviors. Additional assertions for `ripple_delete_clip`, `replace_clip_source`, and `replace_clip_source`'s rate-reset behavior should be added when those ops are implemented — see step 6 below.)

#### Step 3: Run tests, verify they fail

Run from the worktree:
```bash
cd /home/ah64/apps/mlt-pipeline-2a/pyagent-kdenlive-guide
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_clips.py -v -k "slip_clip or change_clip_speed or split_clip"
```

Expected: import errors or `NotImplementedError` (tests fail because the functions are stubs).

#### Step 4: Implement `slip_clip` and `change_clip_speed`

Open `phase2_project_engine/ops/clips_edit.py` and replace the `slip_clip` and `change_clip_speed` stubs with the implementations below. The other 3 ops remain as `raise NotImplementedError` for now.

```python
def slip_clip(tree: ProjectTree, clip_id: str, delta_sec: float) -> dict:
    """Slip the clip: shift source in/out by `delta_sec` while keeping
    the timeline window fixed.
    """
    from ..io import _tc_to_sec, _sec_to_tc
    track, entry, ti = _find_entry_for_clip(tree, clip_id)
    producer_id = _entry_producer_id(entry)
    src = resolve_producer(tree, producer_id)
    src_dur = resolve_source_duration(tree, producer_id)

    cur_in = _tc_to_sec(entry.get("in", "00:00:00.000"))
    cur_out = _tc_to_sec(entry.get("out", "00:00:00.000"))
    new_in = cur_in + delta_sec
    new_out = cur_out + delta_sec

    if new_in < 0 or new_out > src_dur:
        raise NotFoundError(
            f"source_oob: slip would push source_in={new_in} or source_out={new_out} "
            f"outside source duration={src_dur}\n"
            f"fix: delta must keep source_in >= 0 and source_out <= source duration"
        )

    entry.set("in", _sec_to_tc(new_in))
    entry.set("out", _sec_to_tc(new_out))
    return {
        "clip_id": clip_id,
        "source_id": producer_id,
        "source_in_sec": new_in,
        "source_out_sec": new_out,
        "track_index": ti,
        "timeline_start_sec": _tc_to_sec(entry.getparent().get("kdenlive:start") or "0"),
        "duration_sec": new_out - new_in,
    }


def _entry_producer_id(entry: etree._Element) -> str:
    """Extract the producer reference (mlt_service=avformat-clip or similar) of an entry."""
    return entry.get("producer", "")


def change_clip_speed(tree: ProjectTree, clip_id: str, rate: float) -> dict:
    """Change the playback rate (1.0 = normal, 2.0 = 2x faster, 0.5 = 2x slower).
    Rate must be in [0.1, 10.0].
    """
    if rate < 0.1 or rate > 10.0:
        raise validation_error(
            f"rate_out_of_range: rate={rate} not in [0.1, 10.0]",
            "use a rate between 0.1 and 10.0",
        )
    from ..io import _tc_to_sec, _sec_to_tc
    track, entry, ti = _find_entry_for_clip(tree, clip_id)
    cur_in = _tc_to_sec(entry.get("in", "00:00:00.000"))
    cur_out = _tc_to_sec(entry.get("out", "00:00:00.000"))
    cur_dur = cur_out - cur_in
    new_dur = cur_dur / rate

    # Set the producer's speed property. Kdenlive reads "warp_speed" for
    # the producer's playback rate; the source in/out stay the same.
    producer = entry.find("producer")
    if producer is None:
        # The entry uses an external producer reference; look it up.
        producer = tree.root.find(f".//producer[@id='{entry.get('producer')}']")
    if producer is not None:
        speed_prop = producer.find("property[@name='warp_speed']")
        if speed_prop is None:
            speed_prop = etree.SubElement(producer, "property")
            speed_prop.set("name", "warp_speed")
        speed_prop.text = str(rate)

    return {
        "clip_id": clip_id,
        "source_id": entry.get("producer", ""),
        "source_in_sec": cur_in,
        "source_out_sec": cur_out,
        "rate": rate,
        "old_duration_sec": cur_dur,
        "new_duration_sec": new_dur,
    }
```

#### Step 5: Run the slip + speed tests, verify pass

```bash
cd /home/ah64/apps/mlt-pipeline-2a/pyagent-kdenlive-guide
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_clips.py -v -k "slip_clip or change_clip_speed"
```

Expected: 4 passed.

#### Step 6: Implement `split_clip`, `ripple_delete_clip`, `replace_clip_source`

Replace the 3 remaining stubs in `ops/clips_edit.py` with the implementations below.

```python
def split_clip(tree: ProjectTree, clip_id: str, at_sec: float) -> dict:
    """Split the clip at `at_sec` (a timeline-relative position within
    the clip's range). Returns the left (original) and right (new) clip ids.
    """
    from ..io import _tc_to_sec, _sec_to_tc
    track, entry, ti = _find_entry_for_clip(tree, clip_id)
    entry_start_tc = entry.get("in", "00:00:00.000")  # not the timeline start; source in
    playlist = entry.getparent()
    # The entry's timeline start is determined by the sum of preceding entries' durations
    entries = [e for e in playlist.findall("entry") if e is not None]
    timeline_start = 0.0
    for e in entries:
        if e is entry:
            break
        e_dur = _tc_to_sec(e.get("out", "00:00:00.000")) - _tc_to_sec(e.get("in", "00:00:00.000"))
        timeline_start += e_dur
    cur_in = _tc_to_sec(entry.get("in", "00:00:00.000"))
    cur_out = _tc_to_sec(entry.get("out", "00:00:00.000"))
    cur_dur = cur_out - cur_in
    if at_sec <= timeline_start or at_sec >= timeline_start + cur_dur:
        raise NotFoundError(
            f"split_position_invalid: at_sec={at_sec} not strictly between "
            f"{timeline_start} and {timeline_start + cur_dur}\n"
            f"fix: use at_sec strictly between clip_start and clip_end"
        )
    rel_offset = at_sec - timeline_start  # offset from clip start
    new_left_out = cur_in + rel_offset
    # Left half: original entry, with new "out"
    entry.set("out", _sec_to_tc(new_left_out))
    # Right half: new entry, fresh kid, in=offset, out=cur_out
    right_kid = next_kdenlive_id(tree)
    right_entry = etree.SubElement(playlist, "entry")
    right_entry.set("producer", entry.get("producer", ""))
    right_entry.set("in", _sec_to_tc(new_left_out))
    right_entry.set("out", _sec_to_tc(cur_out))
    producer = etree.SubElement(right_entry, "producer")
    producer.set("id", right_kid)
    kid_prop = etree.SubElement(producer, "property")
    kid_prop.set("name", "kdenlive:id")
    kid_prop.text = right_kid
    # Move right_entry to be right after the original entry
    playlist.remove(right_entry)
    entry.addnext(right_entry)
    return {"left_clip_id": clip_id, "right_clip_id": right_kid}


def ripple_delete_clip(tree: ProjectTree, clip_id: str) -> dict:
    """Remove the clip and close the gap on the same track."""
    from ..io import _tc_to_sec, _sec_to_tc
    track, entry, ti = _find_entry_for_clip(tree, clip_id)
    playlist = entry.getparent()
    cur_in = _tc_to_sec(entry.get("in", "00:00:00.000"))
    cur_out = _tc_to_sec(entry.get("out", "00:00:00.000"))
    deleted_dur = cur_out - cur_in
    # Find the entry's timeline start
    entries = [e for e in playlist.findall("entry") if e is not None]
    timeline_start = 0.0
    for e in entries:
        if e is entry:
            break
        e_dur = _tc_to_sec(e.get("out", "00:00:00.000")) - _tc_to_sec(e.get("in", "00:00:00.000"))
        timeline_start += e_dur
    # Remove the entry
    playlist.remove(entry)
    # Shift all following entries left by deleted_dur
    shifted = []
    following_started = False
    new_timeline = 0.0
    for e in playlist.findall("entry"):
        e_dur = _tc_to_sec(e.get("out", "00:00:00.000")) - _tc_to_sec(e.get("in", "00:00:00.000"))
        if following_started:
            kid_prop = e.find("producer/property[@name='kdenlive:id']")
            if kid_prop is not None and kid_prop.text:
                shifted.append(kid_prop.text)
        if e is entry:
            following_started = True
        # The actual shift happens by rewriting in/out: not here; the
        # shift is conceptual (timing) but the source in/out are unchanged.
        new_timeline += e_dur
    # The spec says: "shifted_clip_ids = clips on same track whose
    # timeline_start_sec changed". We return those ids; the actual
    # timeline recalc happens when the file is reloaded (Kdenlive
    # computes timeline positions from source in/out sums).
    return {"deleted_clip_id": clip_id, "shifted_clip_ids": shifted}


def replace_clip_source(tree: ProjectTree, clip_id: str, new_source_id: str) -> dict:
    """Replace the clip's source media. Resets rate to 1.0."""
    from ..io import _tc_to_sec, _sec_to_tc
    track, entry, ti = _find_entry_for_clip(tree, clip_id)
    old_source_id = entry.get("producer", "")
    old_in = _tc_to_sec(entry.get("in", "00:00:00.000"))
    old_out = _tc_to_sec(entry.get("out", "00:00:00.000"))
    old_dur = old_out - old_in
    new_src_dur = resolve_source_duration(tree, new_source_id)
    new_dur = min(old_dur, new_src_dur)
    # Update the producer reference
    entry.set("producer", new_source_id)
    # Reset source in/out
    entry.set("in", _sec_to_tc(0.0))
    entry.set("out", _sec_to_tc(new_dur))
    # Reset the warp_speed on the producer to 1.0
    producer = entry.find("producer")
    if producer is None:
        producer = tree.root.find(f".//producer[@id='{new_source_id}']")
    if producer is not None:
        speed_prop = producer.find("property[@name='warp_speed']")
        if speed_prop is None:
            speed_prop = etree.SubElement(producer, "property")
            speed_prop.set("name", "warp_speed")
        speed_prop.text = "1.0"
    return {
        "clip_id": clip_id,
        "old_source_id": old_source_id,
        "new_source_id": new_source_id,
        "old_rate": 1.0,  # we can't easily read the current rate; assume 1.0 pre-replace
        "new_rate": 1.0,
        "old_duration_sec": old_dur,
        "new_duration_sec": new_dur,
        "source_in_sec": 0.0,
        "source_out_sec": new_dur,
    }
```

#### Step 7: Add the remaining integration tests

Append to `phase2_project_engine/tests/test_ops_clips.py`:

```python
def test_ripple_delete_clip_removes_entry_and_shifts_following():
    """ripple_delete removes the entry and returns the ids of clips that
    follow it on the same track (whose timeline positions change)."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.clips_edit import ripple_delete_clip
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    a = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                    source_in_sec=0.0, source_out_sec=3.0)
    b = insert_clip(tree, track_index=0, position_sec=3.0, source_id=src,
                    source_in_sec=0.0, source_out_sec=3.0)
    result = ripple_delete_clip(tree, a)
    assert result["deleted_clip_id"] == a
    assert b in result["shifted_clip_ids"]
    pl = video_playlist(tree)
    ids = [e.find("producer/property[@name='kdenlive:id']").text
           for e in pl.findall("entry") if e.find("producer/property[@name='kdenlive:id']") is not None]
    assert a not in ids
    assert b in ids


def test_replace_clip_source_resets_rate_and_source_in():
    """replace_clip_source resets source_in to 0, source_out to min(old, new_source),
    and rate to 1.0."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.clips_edit import replace_clip_source
    tree = make_minimal_tree()
    src1 = _import_source(tree, CLIP_SHORT)
    src2 = _import_source(tree, CLIP_SHORT)  # same file, but different source id
    kid = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src1,
                      source_in_sec=2.0, source_out_sec=8.0)
    result = replace_clip_source(tree, kid, new_source_id=src2)
    assert result["new_source_id"] == src2
    assert result["source_in_sec"] == 0.0
    assert result["new_rate"] == 1.0
    assert result["old_duration_sec"] == 6.0
    assert result["new_duration_sec"] == 6.0  # source is the same length
```

#### Step 8: Run all clips-edit tests, verify pass

```bash
cd /home/ah64/apps/mlt-pipeline-2a/pyagent-kdenlive-guide
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_clips.py -v
```

Expected: 18 passed (13 existing + 5 new). If fewer, STOP and fix the failing test before continuing.

#### Step 9: Create `phase3_pyagent_core/tools/clips_edit.py`

```python
"""Tool defs for clip-edit operations on the timeline."""
from __future__ import annotations

from .project import ToolDef


_T = {"type": "integer", "minimum": 0}
_S = {"type": "string"}
_N = {"type": "number", "minimum": 0}


SLIP_CLIP = ToolDef(
    name="pyagent_slip_clip",
    label="Slip clip",
    description="Slip a clip: shift the source media in/out by `delta_sec` while keeping the timeline window fixed. Use delta_sec > 0 to show later in the source, < 0 to show earlier. The clip's start and duration on the timeline stay the same.",
    op="slip_clip",
    is_mutating=True,
    parameters_schema={"clip_id": _S, "delta_sec": _N},
    required=("clip_id", "delta_sec"),
)


RIPPLE_DELETE_CLIP = ToolDef(
    name="pyagent_ripple_delete_clip",
    label="Ripple delete clip",
    description="Remove a clip from the timeline and close the gap on the same track (all following clips on that track shift left by the deleted duration). Clips on other tracks are unaffected.",
    op="ripple_delete_clip",
    is_mutating=True,
    parameters_schema={"clip_id": _S},
    required=("clip_id",),
)


CHANGE_CLIP_SPEED = ToolDef(
    name="pyagent_change_clip_speed",
    label="Change clip speed",
    description="Change the clip's playback rate. rate=1.0 is normal, 2.0 is 2x faster (half duration), 0.5 is 2x slower (double duration). Audio pitch is preserved. Rate must be in [0.1, 10.0].",
    op="change_clip_speed",
    is_mutating=True,
    parameters_schema={"clip_id": _S, "rate": _N},
    required=("clip_id", "rate"),
)


SPLIT_CLIP = ToolDef(
    name="pyagent_split_clip",
    label="Split clip",
    description="Split a clip at a single position. Returns both new clip_ids; the left half keeps the original id, the right half is new. at_sec must be strictly between the clip's timeline start and end.",
    op="split_clip",
    is_mutating=True,
    parameters_schema={"clip_id": _S, "at_sec": _N},
    required=("clip_id", "at_sec"),
)


REPLACE_CLIP_SOURCE = ToolDef(
    name="pyagent_replace_clip_source",
    label="Replace clip source",
    description="Replace the clip's source media. Resets the playback rate to 1.0. The new duration is min(old_duration, new_source_duration).",
    op="replace_clip_source",
    is_mutating=True,
    parameters_schema={"clip_id": _S, "new_source_id": _S},
    required=("clip_id", "new_source_id"),
)


TOOLS = [SLIP_CLIP, RIPPLE_DELETE_CLIP, CHANGE_CLIP_SPEED, SPLIT_CLIP, REPLACE_CLIP_SOURCE]
```

#### Step 10: Wire up `ops/__init__.py` and `tools/__init__.py`

Open `phase2_project_engine/ops/__init__.py` and add to the import block and `__all__`:
```python
from .clips_edit import (
    change_clip_speed, replace_clip_source, ripple_delete_clip,
    slip_clip, split_clip,
)
# ... existing imports ...

__all__ = [
    "import_media",
    "insert_clip", "append_clip", "move_clip", "trim_clip", "delete_clip",
    "slip_clip", "ripple_delete_clip", "change_clip_speed", "split_clip",
    "replace_clip_source",
    "add_transition", "apply_effect", "add_marker",
]
```

Open `phase3_pyagent_core/tools/__init__.py` and add the import + canonical-order entry:
```python
from . import bin, catalog, clips, clips_edit, effects, markers, project, render_qc, transitions

def all_tools() -> list:
    return [
        *project.TOOLS,
        *catalog.TOOLS,
        *bin.TOOLS,
        *clips.TOOLS,
        *clips_edit.TOOLS,  # NEW
        *transitions.TOOLS,
        *effects.TOOLS,
        *markers.TOOLS,
        *render_qc.TOOLS,
    ]
```

#### Step 11: Wire up `runtime.py` OP_TABLE and MUTATING_OPS

Open `phase3_pyagent_core/runtime.py` and add 5 entries to `OP_TABLE`:
```python
OP_TABLE: dict[str, str] = {
    # ... existing entries ...
    "slip_clip": "slip_clip",
    "ripple_delete_clip": "ripple_delete_clip",
    "change_clip_speed": "change_clip_speed",
    "split_clip": "split_clip",
    "replace_clip_source": "replace_clip_source",
}

MUTATING_OPS: frozenset[str] = frozenset({
    # ... existing entries ...
    "slip_clip", "ripple_delete_clip", "change_clip_speed", "split_clip",
    "replace_clip_source",
})
```

#### Step 12: Add 5 golden-file test cases

The golden-file system works as follows: each `_CASES` entry has a real `args` dict (which `run_op` is invoked with) and a `key` that maps to an entry in `golden_io.json` (the expected response). Both must be real values — placeholders don't work because `run_op` validates the args.

Process:
1. Add 5 entries to `_CASES` in `phase3_pyagent_core/tests/test_golden_io.py` with **real args** (use the demo fixture's actual clip_id, which you discover via `run_op("get_timeline_summary", ...)`). Read the existing 5 cases first to copy the exact format.
2. Add 5 corresponding entries to `phase3_pyagent_core/tests/fixtures/golden_io.json` (the expected `result` block for each invocation).
3. Both args and golden values are obtained from the same helper script.

Add to `_CASES`:
```python
# --- clips-edit (5 mutating tools) ---
# Args below use real clip_id / src_id from the demo fixture; replace
# them with the actual values from running get_timeline_summary.
("slip_clip", {"clip_id": "<REAL_CLIP_ID>", "delta_sec": 0.0}, "slip_clip"),
("ripple_delete_clip", {"clip_id": "<REAL_CLIP_ID>"}, "ripple_delete_clip"),
("change_clip_speed", {"clip_id": "<REAL_CLIP_ID>", "rate": 1.0}, "change_clip_speed"),
("split_clip", {"clip_id": "<REAL_CLIP_ID>", "at_sec": 2.0}, "split_clip"),
("replace_clip_source", {"clip_id": "<REAL_CLIP_ID>", "new_source_id": "<REAL_SRC_ID>"}, "replace_clip_source"),
```

Generate the args + golden values via this helper script (write to `/tmp/generate_clips_edit_golden.py` and run it):

```python
# /tmp/generate_clips_edit_golden.py
"""One-shot script: print real args (for _CASES) and real responses
(for golden_io.json) for the 5 clips-edit tools.

Run: PYTHONPATH=. python3 /tmp/generate_clips_edit_golden.py
"""
import json
import shutil
import tempfile
from pathlib import Path
from phase3_pyagent_core.runtime import run_op

DEMO = Path("phase3_pyagent_core/tests/fixtures/demo.kdenlive")
CATALOG = "phase1_knowledge_base/catalog.json"

_, summary = run_op("get_timeline_summary", {}, str(DEMO), CATALOG)
clip_id = summary["result"]["tracks"][0]["clips"][0]["clip_id"]
src_id = summary["result"]["tracks"][0]["clips"][0]["source_id"]
print(f"REAL_CLIP_ID={clip_id}")
print(f"REAL_SRC_ID={src_id}")
print()

with tempfile.TemporaryDirectory() as td:
    proj = Path(td) / "demo.kdenlive"
    shutil.copy(DEMO, proj)
    proj_path = str(proj)
    for op, args, key in [
        ("slip_clip", {"clip_id": clip_id, "delta_sec": 0.0}, "slip_clip"),
        ("ripple_delete_clip", {"clip_id": clip_id}, "ripple_delete_clip"),
        ("change_clip_speed", {"clip_id": clip_id, "rate": 1.0}, "change_clip_speed"),
        ("split_clip", {"clip_id": clip_id, "at_sec": 2.0}, "split_clip"),
        ("replace_clip_source", {"clip_id": clip_id, "new_source_id": src_id}, "replace_clip_source"),
    ]:
        code, resp = run_op(op, args, proj_path, CATALOG)
        print(f"=== _CASES entry: ({op!r}, {args!r}, {key!r}) ===")
        print(f"=== golden_io.json[{key!r}] = {json.dumps(resp.get('result', resp), indent=2, default=str)} ===")
        print()
```

```bash
cd /home/ah64/apps/mlt-pipeline-2a/pyagent-kdenlive-guide
PYTHONPATH=. python3 /tmp/generate_clips_edit_golden.py
```

Use the printed `REAL_CLIP_ID` / `REAL_SRC_ID` to fill in the `_CASES` args, and copy each `result` block (sans env-specific fields like `path` and project UUIDs) into `golden_io.json`. The existing `_compare_key_subset` helper skips env-specific fields automatically.

#### Step 13: Run the full test suite, verify pass

```bash
cd /home/ah64/apps/mlt-pipeline-2a/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest -q --no-header
```

Expected: 241 passed, 1 skipped, 1 warning in ~85s (231 baseline + 10 new).

If anything is red, STOP and fix before committing.

#### Step 14: Commit

```bash
cd /home/ah64/apps/mlt-pipeline-2a
git add phase2_project_engine/ops/clips_edit.py
git add phase2_project_engine/ops/__init__.py
git add phase2_project_engine/tests/test_ops_clips.py
git add phase3_pyagent_core/tools/clips_edit.py
git add phase3_pyagent_core/tools/__init__.py
git add phase3_pyagent_core/runtime.py
git add phase3_pyagent_core/tests/test_golden_io.py
git add phase3_pyagent_core/tests/fixtures/golden_io.json
git status  # verify only the expected files are staged
git commit -m "[clips-edit] add slip, ripple, speed, split, replace ops"
```

Expected: 1 commit, no other changes staged.

---

### Task 2: Commit 2 — effects (1 tool: `remove_effect`)

**Files:**
- Modify: `phase2_project_engine/ops/effects.py` (add `remove_effect`)
- Modify: `phase3_pyagent_core/tools/effects.py` (add `REMOVE_EFFECT` ToolDef)
- Modify: `phase3_pyagent_core/runtime.py` (add 1 OP_TABLE + 1 MUTATING_OPS entry)
- Modify: `phase2_project_engine/tests/test_ops_effects.py` (add 1 test function)
- Modify: `phase3_pyagent_core/tests/fixtures/golden_io.json` (add 1 entry)

**Interfaces produced:**
- `ops.effects.remove_effect(tree, clip_id, effect_index) -> dict`
- `tools.effects.REMOVE_EFFECT` (ToolDef)
- `runtime.OP_TABLE["remove_effect"] = "remove_effect"`

#### Step 1: Read existing effects ops

Open `phase2_project_engine/ops/effects.py` to see the `apply_effect` pattern. The new `remove_effect` function follows the same shape.

#### Step 2: Write the failing test

Append to `phase2_project_engine/tests/test_ops_effects.py`:

```python
def test_remove_effect_by_index():
    """remove_effect drops the entry at effect_index from the clip's
    filter list. Out-of-range index raises effect_index_out_of_range
    NotFoundError."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.effects import apply_effect, remove_effect
    from phase2_project_engine.errors import NotFoundError
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                      source_in_sec=0.0, source_out_sec=5.0)
    apply_effect(tree, clip_id=kid, effect_id="sepia")  # an effect from the catalog
    pre_count = len([f for f in tree.root.iter("filter")])
    result = remove_effect(tree, clip_id=kid, effect_index=0)
    post_count = len([f for f in tree.root.iter("filter")])
    assert post_count == pre_count - 1
    assert result["removed_effect_index"] == 0
    assert result["remaining_effect_count"] == 0


def test_remove_effect_rejects_out_of_range_index():
    """remove_effect with effect_index >= effect count raises NotFoundError."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.effects import remove_effect
    from phase2_project_engine.errors import NotFoundError
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                      source_in_sec=0.0, source_out_sec=5.0)
    with pytest.raises(NotFoundError) as exc:
        remove_effect(tree, clip_id=kid, effect_index=5)
    assert "effect_index_out_of_range" in str(exc.value)
```

(Read the existing test_ops_effects.py first to copy the imports and fixture setup. The `_import_source` and `make_minimal_tree` helpers already exist in `ops_fxtures`.)

#### Step 3: Run the test, verify it fails

```bash
cd /home/ah64/apps/mlt-pipeline-2a/pyagent-kdenlive-guide
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_effects.py -v -k "remove_effect"
```

Expected: import error (function doesn't exist yet).

#### Step 4: Implement `remove_effect` in `ops/effects.py`

```python
def remove_effect(tree: ProjectTree, clip_id: str, effect_index: int) -> dict:
    """Remove the effect at `effect_index` from the clip's filter list.

    The clip's filter list is the chain of <filter> elements reachable
    from the clip's producer. Order is preserved; the entry at
    `effect_index` (0-based) is dropped.
    """
    from .clips_edit import _find_entry_for_clip
    from ..io import _sec_to_tc, _tc_to_sec
    track, entry, ti = _find_entry_for_clip(tree, clip_id)
    producer = entry.find("producer")
    if producer is None:
        producer = tree.root.find(f".//producer[@id='{entry.get('producer')}']")
    filters = list(producer.findall("filter")) if producer is not None else []
    if effect_index < 0 or effect_index >= len(filters):
        raise NotFoundError(
            f"effect_index_out_of_range: effect_index={effect_index}, "
            f"effect_count={len(filters)}\n"
            f"fix: call get_timeline_summary to see valid indices"
        )
    removed = filters[effect_index]
    removed_id = removed.get("id") or removed.get("kdenlive:id") or ""
    producer.remove(removed)
    return {
        "clip_id": clip_id,
        "removed_effect_index": effect_index,
        "removed_effect_id": removed_id,
        "remaining_effect_count": len(filters) - 1,
    }
```

#### Step 5: Add the ToolDef

Open `phase3_pyagent_core/tools/effects.py` and append:

```python
REMOVE_EFFECT = ToolDef(
    name="pyagent_remove_effect",
    label="Remove effect",
    description="Remove an effect from a clip by its index. Call get_timeline_summary first to see what effect indices exist on the clip.",
    op="remove_effect",
    is_mutating=True,
    parameters_schema={"clip_id": _S, "effect_index": _T},
    required=("clip_id", "effect_index"),
)
```

Add `REMOVE_EFFECT` to the `TOOLS` list (read the existing list first; append at the end).

#### Step 6: Wire up runtime.py

Add 1 entry each to `OP_TABLE` and `MUTATING_OPS` in `runtime.py`:
```python
OP_TABLE["remove_effect"] = "remove_effect"
MUTATING_OPS = MUTATING_OPS | {"remove_effect"}
```

#### Step 7: Add golden-file case

Add to `_CASES` in `phase3_pyagent_core/tests/test_golden_io.py`:
```python
("remove_effect", {"clip_id": "PLACEHOLDER_KID", "effect_index": 0}, "remove_effect"),
```

Generate the golden value using a helper script (similar to step 12 of Task 1). The script applies an effect first (using `apply_effect`), then calls `remove_effect`, and prints the result. Paste the result (without env-specific fields) into `fixtures/golden_io.json`.

#### Step 8: Run the full test suite, verify pass

```bash
cd /home/ah64/apps/mlt-pipeline-2a/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest -q --no-header
```

Expected: 243 passed, 1 skipped (241 from Task 1 + 2 new — one for the golden case, one for the integration test). Note: the new integration test adds 1 collected test, the new golden case adds 1 collected test = 2 new.

#### Step 9: Commit

```bash
cd /home/ah64/apps/mlt-pipeline-2a
git add phase2_project_engine/ops/effects.py
git add phase2_project_engine/tests/test_ops_effects.py
git add phase3_pyagent_core/tools/effects.py
git add phase3_pyagent_core/runtime.py
git add phase3_pyagent_core/tests/test_golden_io.py
git add phase3_pyagent_core/tests/fixtures/golden_io.json
git commit -m "[effects] add remove_effect op"
```

---

### Task 3: Commit 3 — transitions (1 tool: `remove_transition`)

**Files:**
- Modify: `phase2_project_engine/ops/transitions.py` (add `remove_transition`)
- Modify: `phase3_pyagent_core/tools/transitions.py` (add `REMOVE_TRANSITION` ToolDef)
- Modify: `phase3_pyagent_core/runtime.py` (add 1 OP_TABLE + 1 MUTATING_OPS entry)
- Modify: `phase2_project_engine/tests/test_ops_transitions.py` (add 1 test function)
- Modify: `phase3_pyagent_core/tests/fixtures/golden_io.json` (add 1 entry)

**Interfaces produced:**
- `ops.transitions.remove_transition(tree, transition_id) -> dict`
- `tools.transitions.REMOVE_TRANSITION` (ToolDef)
- `runtime.OP_TABLE["remove_transition"] = "remove_transition"`

#### Step 1: Read existing transitions ops

Open `phase2_project_engine/ops/transitions.py` to see the `add_transition` pattern.

#### Step 2: Write the failing test

Append to `phase2_project_engine/tests/test_ops_transitions.py`:

```python
def test_remove_transition_by_id():
    """remove_transition drops the transition element with the given kdenlive:id.
    The bounded clip entries are not modified."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.transitions import add_transition, remove_transition
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    a = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                    source_in_sec=0.0, source_out_sec=5.0)
    b = insert_clip(tree, track_index=0, position_sec=5.0, source_id=src,
                    source_in_sec=0.0, source_out_sec=5.0)
    add_transition(tree, track_index=0, between_clip_a=a, between_clip_b=b,
                   kind="fade", duration_sec=1.0)
    pre_count = len([t for t in tree.root.iter("transition")])
    # Find the transition_id
    transition_id = next(
        t.get("kdenlive:id") or t.get("id")
        for t in tree.root.iter("transition")
    )
    result = remove_transition(tree, transition_id=transition_id)
    post_count = len([t for t in tree.root.iter("transition")])
    assert post_count == pre_count - 1
    assert result["transition_id"] == transition_id


def test_remove_transition_rejects_unknown_id():
    """remove_transition with an unknown id raises NotFoundError."""
    from phase2_project_engine.ops.transitions import remove_transition
    from phase2_project_engine.errors import NotFoundError
    tree = make_minimal_tree()
    with pytest.raises(NotFoundError) as exc:
        remove_transition(tree, transition_id="NONEXISTENT_ID")
    assert "transition_not_found" in str(exc.value)
```

(Read the existing test_ops_transitions.py first; copy the imports and `make_minimal_tree` fixture usage.)

#### Step 3: Run test, verify fail

```bash
cd /home/ah64/apps/mlt-pipeline-2a/pyagent-kdenlive-guide
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_transitions.py -v -k "remove_transition"
```

Expected: import error.

#### Step 4: Implement `remove_transition`

```python
def remove_transition(tree: ProjectTree, transition_id: str) -> dict:
    """Remove a transition by its kdenlive:id or id attribute.
    Returns the list of clip_ids that were bounded by the transition."""
    affected_clip_ids = []
    target = None
    for t in tree.root.iter("transition"):
        if t.get("kdenlive:id") == transition_id or t.get("id") == transition_id:
            target = t
            # Find the affected clips (those referencing this transition)
            for entry in tree.root.iter("entry"):
                if entry.get("kdenlive:transition") == transition_id:
                    kid = entry.find("producer/property[@name='kdenlive:id']")
                    if kid is not None and kid.text:
                        affected_clip_ids.append(kid.text)
            break
    if target is None:
        raise NotFoundError(
            f"transition_not_found: transition_id={transition_id!r}\n"
            f"fix: call get_timeline_summary and re-pick"
        )
    target.getparent().remove(target)
    return {"transition_id": transition_id, "affected_clip_ids": affected_clip_ids}
```

#### Step 5: Add the ToolDef

Open `phase3_pyagent_core/tools/transitions.py` and append:

```python
REMOVE_TRANSITION = ToolDef(
    name="pyagent_remove_transition",
    label="Remove transition",
    description="Remove a transition by its id. Call get_timeline_summary first to see what transition_ids exist.",
    op="remove_transition",
    is_mutating=True,
    parameters_schema={"transition_id": _S},
    required=("transition_id",),
)
```

Add to the `TOOLS` list.

#### Step 6: Wire up runtime.py

```python
OP_TABLE["remove_transition"] = "remove_transition"
MUTATING_OPS = MUTATING_OPS | {"remove_transition"}
```

#### Step 7: Add golden-file case

Add to `_CASES` in `test_golden_io.py`:
```python
("remove_transition", {"transition_id": "PLACEHOLDER_TID"}, "remove_transition"),
```

Generate the golden value with a helper script (apply a transition first via `add_transition`, capture the new id, then call `remove_transition` with it). Paste the response into `fixtures/golden_io.json`.

#### Step 8: Run full test suite, verify pass

```bash
cd /home/ah64/apps/mlt-pipeline-2a/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest -q --no-header
```

Expected: 245 passed, 1 skipped (243 from Task 2 + 2 new).

#### Step 9: Commit

```bash
cd /home/ah64/apps/mlt-pipeline-2a
git add phase2_project_engine/ops/transitions.py
git add phase2_project_engine/tests/test_ops_transitions.py
git add phase3_pyagent_core/tools/transitions.py
git add phase3_pyagent_core/runtime.py
git add phase3_pyagent_core/tests/test_golden_io.py
git add phase3_pyagent_core/tests/fixtures/golden_io.json
git commit -m "[transitions] add remove_transition op"
```

---

### Task 4: Commit 4 — groups (3 tools + real-Kdenlive interop test)

This is the largest task. It introduces the groups domain with a new file for ops, a new file for tools, a new file for tests, and a real-Kdenlive interop test in phase7.

**Files:**
- Create: `phase2_project_engine/ops/groups.py`
- Create: `phase3_pyagent_core/tools/groups.py`
- Create: `phase2_project_engine/tests/test_ops_groups.py`
- Modify: `phase2_project_engine/ops/__init__.py` (add 3 exports)
- Modify: `phase3_pyagent_core/tools/__init__.py` (import groups, add to all_tools)
- Modify: `phase3_pyagent_core/runtime.py` (add 3 OP_TABLE + 2 MUTATING_OPS entries)
- Modify: `phase3_pyagent_core/tests/fixtures/golden_io.json` (add 3 entries)
- Modify: `phase7_real_session/tests/test_e2e.py` (add 1 interop test, skipif_kdenlive_missing)

**Interfaces produced:**
- `ops.groups.group_clips(tree, clip_ids, group_name) -> dict`
- `ops.groups.ungroup_clips(tree, group_name) -> dict`
- `ops.groups.list_groups(tree) -> dict`
- `tools.groups.GROUP_CLIPS`, `UNGROUP_CLIPS`, `LIST_GROUPS` (ToolDefs)
- `runtime.OP_TABLE` keys: `group_clips`, `ungroup_clips`, `list_groups`
- `runtime.MUTATING_OPS` adds: `group_clips`, `ungroup_clips` (NOT `list_groups`)

#### Step 1: Create `phase2_project_engine/ops/groups.py` (skeleton)

```python
"""Group operations: create/dissolve/list clip groups using Kdenlive's
real groups format.

Storage: `kdenlive:sequenceproperties.groups` on the tractor, a
JSON-encoded string containing a JSON array of root group objects.
Each group is `{type: "Normal", pyagent:name: <name>, children: [...]}`.
Each leaf is `{type: "Leaf", leaf: "clip", data: "<track>:<pos>:-1"}`.

pyagent only creates `Normal` groups (Kdenlive manages `AVSplit` and
`Selection` itself). No runtime IDs are minted; `group_name` (enforced
unique) is the handle for ungroup/list.
"""
from __future__ import annotations

import json

from lxml import etree

from ..errors import NotFoundError, validation_error
from ..io import ProjectTree
from ._helpers import _find_entry_for_clip  # reuse from clips_edit


_GROUPS_PROPERTY = "kdenlive:sequenceproperties.groups"


def _load_groups(tree: ProjectTree) -> list[dict]:
    """Load the existing groups array from the tractor, or [] if empty."""
    tractor = tree.get_tractor()
    if tractor is None:
        return []
    prop = tractor.find(f"property[@name='{_GROUPS_PROPERTY}']")
    if prop is None or not prop.text:
        return []
    return json.loads(prop.text)


def _save_groups(tree: ProjectTree, groups: list[dict]) -> None:
    """Save the groups array back to the tractor's property."""
    tractor = tree.get_tractor()
    if tractor is None:
        return
    prop = tractor.find(f"property[@name='{_GROUPS_PROPERTY}']")
    if prop is None:
        prop = etree.SubElement(tractor, "property")
        prop.set("name", _GROUPS_PROPERTY)
    prop.text = json.dumps(groups)


def _clip_position(tree: ProjectTree, clip_id: str) -> tuple[int, int, int]:
    """Return (track_pos, timeline_pos, sublayer=-1) for a given clip_id."""
    tracks = tree.root.findall(".//tractor")
    for ti, track in enumerate(tracks):
        for entry in track.iter("entry"):
            kid = None
            producer = entry.find("producer")
            if producer is not None:
                kid_prop = producer.find("property[@name='kdenlive:id']")
                if kid_prop is not None:
                    kid = kid_prop.text
            if kid == clip_id:
                # Compute timeline pos
                pos = 0
                for sibling in entry.getparent().findall("entry"):
                    if sibling is entry:
                        break
                    from ..io import _tc_to_sec
                    pos += _tc_to_sec(sibling.get("out", "00:00:00.000")) - _tc_to_sec(sibling.get("in", "00:00:00.000"))
                return (ti, int(pos * 1000), -1)  # pos in frames (1000 fps) for stability
    raise NotFoundError(
        f"clip_not_found: clip_id={clip_id!r}\n"
        f"fix: call get_timeline_summary and re-pick"
    )


# --- Public ops ------------------------------------------------------------

def group_clips(tree: ProjectTree, clip_ids: list[str], group_name: str) -> dict:
    """Create a Normal group containing the given clip_ids."""
    raise NotImplementedError


def ungroup_clips(tree: ProjectTree, group_name: str) -> dict:
    """Dissolve a group by name."""
    raise NotImplementedError


def list_groups(tree: ProjectTree) -> dict:
    """Return all Normal groups in the project."""
    raise NotImplementedError
```

#### Step 2: Create `phase2_project_engine/tests/test_ops_groups.py`

```python
"""Tests for phase2_project_engine.ops.groups — group/ungroup/list using
Kdenlive's real groups format (kdenlive:sequenceproperties.groups)."""
import json
import os
import pytest

from phase2_project_engine.errors import NotFoundError, ValidationError
from phase2_project_engine.tests.ops_fixtures import (
    make_minimal_tree, CLIP_SHORT,
)


def _import_source(tree, source):
    from phase2_project_engine.ops.bin import import_media
    return import_media(tree, [str(source)])[0]


def test_group_clips_writes_json_tree():
    """group_clips writes a JSON array to kdenlive:sequenceproperties.groups
    with one Normal group containing Leaf children for each clip."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.groups import group_clips, list_groups
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    a = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                    source_in_sec=0.0, source_out_sec=3.0)
    b = insert_clip(tree, track_index=0, position_sec=3.0, source_id=src,
                    source_in_sec=0.0, source_out_sec=3.0)
    result = group_clips(tree, clip_ids=[a, b], group_name="intro")
    assert result["group_name"] == "intro"
    assert set(result["clip_ids"]) == {a, b}
    # Verify the JSON tree in the property
    tractor = tree.get_tractor()
    prop = tractor.find("property[@name='kdenlive:sequenceproperties.groups']")
    assert prop is not None
    groups = json.loads(prop.text)
    assert len(groups) == 1
    g = groups[0]
    assert g["type"] == "Normal"
    assert g["pyagent:name"] == "intro"
    assert len(g["children"]) == 2
    for child in g["children"]:
        assert child["type"] == "Leaf"
        assert child["leaf"] == "clip"
        # data format: "<track>:<pos>:-1"
        parts = child["data"].split(":")
        assert len(parts) == 3
        assert parts[2] == "-1"


def test_list_groups_returns_round_trippable_groups():
    """list_groups returns [{group_name, clip_ids}] and resolves (track, pos) -> current clip_id."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.groups import group_clips, list_groups
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    a = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                    source_in_sec=0.0, source_out_sec=3.0)
    b = insert_clip(tree, track_index=0, position_sec=3.0, source_id=src,
                    source_in_sec=0.0, source_out_sec=3.0)
    group_clips(tree, clip_ids=[a, b], group_name="intro")
    result = list_groups(tree)
    assert len(result["groups"]) == 1
    g = result["groups"][0]
    assert g["group_name"] == "intro"
    assert set(g["clip_ids"]) == {a, b}


def test_ungroup_clips_removes_group():
    """ungroup_clips removes the group with the given name."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.groups import group_clips, ungroup_clips, list_groups
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    a = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                    source_in_sec=0.0, source_out_sec=3.0)
    group_clips(tree, clip_ids=[a], group_name="solo")
    ungroup_clips(tree, group_name="solo")
    result = list_groups(tree)
    assert result["groups"] == []


def test_group_clips_rejects_duplicate_name():
    """group_clips raises duplicate_group_name ValidationError on collision."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.groups import group_clips
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    a = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                    source_in_sec=0.0, source_out_sec=3.0)
    b = insert_clip(tree, track_index=0, position_sec=3.0, source_id=src,
                    source_in_sec=0.0, source_out_sec=3.0)
    group_clips(tree, clip_ids=[a], group_name="dup")
    with pytest.raises(ValidationError) as exc:
        group_clips(tree, clip_ids=[b], group_name="dup")
    assert "duplicate_group_name" in str(exc.value)
    assert "fix:" in str(exc.value)


def test_ungroup_clips_rejects_unknown_group():
    """ungroup_clips raises group_not_found NotFoundError on unknown name."""
    from phase2_project_engine.ops.groups import ungroup_clips
    tree = make_minimal_tree()
    with pytest.raises(NotFoundError) as exc:
        ungroup_clips(tree, group_name="nope")
    assert "group_not_found" in str(exc.value)
```

#### Step 3: Run test, verify fail

```bash
cd /home/ah64/apps/mlt-pipeline-2a/pyagent-kdenlive-guide
PYTHONPATH=. pytest phase2_project_engine/tests/test_ops_groups.py -v
```

Expected: import error (test_ops_groups.py can't import from the new groups module).

#### Step 4: Implement `group_clips`, `ungroup_clips`, `list_groups`

Replace the 3 stubs in `ops/groups.py` with:

```python
def group_clips(tree: ProjectTree, clip_ids: list[str], group_name: str) -> dict:
    """Create a Normal group containing the given clip_ids."""
    if not clip_ids:
        raise validation_error(
            "empty_clip_list: clip_ids is empty",
            "pass at least one clip_id",
        )
    if not group_name:
        raise validation_error(
            "group_name_invalid: group_name is empty",
            "pass a non-empty group_name",
        )
    groups = _load_groups(tree)
    # Duplicate name check
    for g in groups:
        if g.get("type") == "Normal" and g.get("pyagent:name") == group_name:
            raise validation_error(
                f"duplicate_group_name: group_name={group_name!r} already exists",
                "use a unique group_name; call list_groups to see existing names",
            )
    # Resolve each clip_id to (track, pos, -1)
    leaves = []
    for cid in clip_ids:
        track_pos, timeline_pos, sublayer = _clip_position(tree, cid)
        leaves.append({
            "type": "Leaf",
            "leaf": "clip",
            "data": f"{track_pos}:{timeline_pos}:{sublayer}",
        })
    new_group = {
        "type": "Normal",
        "pyagent:name": group_name,
        "children": leaves,
    }
    groups.append(new_group)
    _save_groups(tree, groups)
    return {"group_name": group_name, "clip_ids": list(clip_ids)}


def ungroup_clips(tree: ProjectTree, group_name: str) -> dict:
    """Dissolve a group by name."""
    groups = _load_groups(tree)
    new_groups = []
    dissolved_clip_ids = []
    found = False
    for g in groups:
        if g.get("type") == "Normal" and g.get("pyagent:name") == group_name:
            found = True
            # Collect the clip_ids (resolved back from (track, pos) -> current clip_id)
            for child in g.get("children", []):
                if child.get("type") == "Leaf" and child.get("leaf") == "clip":
                    track_pos, pos, _ = child["data"].split(":")
                    dissolved_clip_ids.extend(
                        _resolve_clip_id_at(tree, int(track_pos), int(pos))
                    )
        else:
            new_groups.append(g)
    if not found:
        raise NotFoundError(
            f"group_not_found: group_name={group_name!r}\n"
            f"fix: call list_groups to see existing groups"
        )
    _save_groups(tree, new_groups)
    return {"dissolved_group_name": group_name, "affected_clip_ids": dissolved_clip_ids}


def list_groups(tree: ProjectTree) -> dict:
    """Return all Normal groups in the project."""
    groups = _load_groups(tree)
    result = []
    for g in groups:
        if g.get("type") != "Normal":
            continue  # skip AVSplit
        clip_ids = []
        for child in g.get("children", []):
            if child.get("type") == "Leaf" and child.get("leaf") == "clip":
                track_pos, pos, _ = child["data"].split(":")
                clip_ids.extend(_resolve_clip_id_at(tree, int(track_pos), int(pos)))
        result.append({
            "group_name": g.get("pyagent:name", ""),
            "clip_ids": clip_ids,
        })
    return {"groups": result}


def _resolve_clip_id_at(tree: ProjectTree, track_pos: int, timeline_pos_frames: int) -> list[str]:
    """Resolve (track_pos, timeline_pos_in_ms) -> current clip_id. Returns 0 or 1 id."""
    tracks = tree.root.findall(".//tractor")
    if track_pos >= len(tracks):
        return []
    track = tracks[track_pos]
    pos = 0.0
    from ..io import _tc_to_sec
    for entry in track.findall("entry"):
        e_dur = _tc_to_sec(entry.get("out", "00:00:00.000")) - _tc_to_sec(entry.get("in", "00:00:00.000"))
        if int(pos * 1000) == timeline_pos_frames:
            kid_prop = entry.find("producer/property[@name='kdenlive:id']")
            if kid_prop is not None and kid_prop.text:
                return [kid_prop.text]
            return []
        pos += e_dur
    return []
```

#### Step 5: Create `phase3_pyagent_core/tools/groups.py`

```python
"""Tool defs for group operations."""
from __future__ import annotations

from .project import ToolDef


_S = {"type": "string"}
_A = {"type": "array", "items": _S}


GROUP_CLIPS = ToolDef(
    name="pyagent_group_clips",
    label="Group clips",
    description="Create a folder-style group containing the given clip_ids. group_name must be unique across the project.",
    op="group_clips",
    is_mutating=True,
    parameters_schema={"clip_ids": _A, "group_name": _S},
    required=("clip_ids", "group_name"),
)


UNGROUP_CLIPS = ToolDef(
    name="pyagent_ungroup_clips",
    label="Ungroup clips",
    description="Dissolve a group by its group_name. The clips remain on the timeline; only the group is removed.",
    op="ungroup_clips",
    is_mutating=True,
    parameters_schema={"group_name": _S},
    required=("group_name",),
)


LIST_GROUPS = ToolDef(
    name="pyagent_list_groups",
    label="List groups",
    description="List all groups in the project. Read-only.",
    op="list_groups",
    is_mutating=False,
    parameters_schema={},
    required=(),
)


TOOLS = [GROUP_CLIPS, UNGROUP_CLIPS, LIST_GROUPS]
```

#### Step 6: Wire up `ops/__init__.py` and `tools/__init__.py`

In `ops/__init__.py`:
```python
from .groups import group_clips, ungroup_clips, list_groups
# add to __all__:
"group_clips", "ungroup_clips", "list_groups",
```

In `tools/__init__.py`:
```python
from . import bin, catalog, clips, clips_edit, effects, groups, markers, project, render_qc, transitions

def all_tools() -> list:
    return [
        *project.TOOLS,
        *catalog.TOOLS,
        *bin.TOOLS,
        *clips.TOOLS,
        *clips_edit.TOOLS,
        *transitions.TOOLS,
        *effects.TOOLS,
        *groups.TOOLS,  # NEW
        *markers.TOOLS,
        *render_qc.TOOLS,
    ]
```

#### Step 7: Wire up runtime.py

```python
OP_TABLE["group_clips"] = "group_clips"
OP_TABLE["ungroup_clips"] = "ungroup_clips"
OP_TABLE["list_groups"] = "list_groups"
MUTATING_OPS = MUTATING_OPS | {"group_clips", "ungroup_clips"}
# (list_groups is read-only; do NOT add to MUTATING_OPS)
```

#### Step 8: Add 3 golden-file cases

Add to `_CASES` in `test_golden_io.py`:
```python
# --- groups ---
("list_groups", {}, "list_groups"),
("group_clips", {"clip_ids": ["PLACEHOLDER_KID"], "group_name": "PLACEHOLDER_NAME"}, "group_clips"),
("ungroup_clips", {"group_name": "PLACEHOLDER_NAME"}, "ungroup_clips"),
```

Generate the golden values via a helper script (similar to Task 1's step 12). For `list_groups`, run it against the demo fixture directly (read-only). For `group_clips` / `ungroup_clips`, copy the demo to a tmp dir first. Paste responses (without env-specific fields) into `fixtures/golden_io.json`.

#### Step 9: Add the real-Kdenlive interop test

Open `phase7_real_session/tests/test_e2e.py` and append:

```python
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


KdenliveBin = pytest.mark.skipif(
    shutil.which("kdenlive") is None,
    reason="kdenlive not installed",
)


@KdenliveBin
def test_groups_round_trip_through_real_kdenlive(tmp_path):
    """A project with a group created by pyagent's group_clips opens
    cleanly in real Kdenlive, and re-saving it preserves the group
    structure (type, pyagent:name, children, leaf data format)."""
    from phase3_pyagent_core.runtime import run_op

    demo = Path("phase3_pyagent_core/tests/fixtures/demo.kdenlive")
    catalog = "phase1_knowledge_base/catalog.json"

    # Copy the demo and add a group
    proj = tmp_path / "demo.kdenlive"
    shutil.copy(demo, proj)
    code, summary = run_op("get_timeline_summary", {}, str(proj), catalog)
    assert code == 0
    clip_id = summary["result"]["tracks"][0]["clips"][0]["clip_id"]
    code, _ = run_op("group_clips", {"clip_ids": [clip_id], "group_name": "interop_test"},
                     str(proj), catalog)
    assert code == 0

    # Open in Kdenlive (headless) and re-save
    resaved = tmp_path / "resaved.kdenlive"
    # Use kdenlive's CLI to open and re-save. The exact command depends
    # on the installed Kdenlive version; for 23.04+ the relevant
    # command is something like:
    result = subprocess.run(
        ["kdenlive", "--open", str(proj), "--save-as", str(resaved)],
        capture_output=True, timeout=60, env={**__import__("os").environ, "DISPLAY": ":99"},
    )
    if result.returncode != 0:
        pytest.skip(f"kdenlive CLI not available in this env: {result.stderr[:200]!r}")
    assert resaved.exists()

    # Read the resaved project and verify the group survived
    from phase2_project_engine.io import load_project
    tree2 = load_project(resaved)
    tractor = tree2.get_tractor()
    prop = tractor.find("property[@name='kdenlive:sequenceproperties.groups']")
    assert prop is not None, "kdenlive dropped the groups property"
    groups = json.loads(prop.text)
    assert any(g.get("type") == "Normal" and g.get("pyagent:name") == "interop_test"
               for g in groups), "the pyagent group was lost in re-save"
```

(Read the existing test_e2e.py first to find the correct import style and any existing helpers like `skipif_kdenlive_missing`. The exact `kdenlive` CLI invocation may need adjustment based on the installed version — if the CLI doesn't support `--open --save-as` headless, mark this test as expected-skip and document why.)

#### Step 10: Run the full test suite, verify pass

```bash
cd /home/ah64/apps/mlt-pipeline-2a/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest -q --no-header
```

Expected: 252 passed, 1 skipped (245 from Task 3 + 7 new: 3 golden + 3 integration + 1 e2e). In CI without Kdenlive, the e2e test is skipped: 251 passed, 2 skipped.

#### Step 11: Commit

```bash
cd /home/ah64/apps/mlt-pipeline-2a
git add phase2_project_engine/ops/groups.py
git add phase2_project_engine/ops/__init__.py
git add phase2_project_engine/tests/test_ops_groups.py
git add phase3_pyagent_core/tools/groups.py
git add phase3_pyagent_core/tools/__init__.py
git add phase3_pyagent_core/runtime.py
git add phase3_pyagent_core/tests/test_golden_io.py
git add phase3_pyagent_core/tests/fixtures/golden_io.json
git add phase7_real_session/tests/test_e2e.py
git commit -m "[groups] add group_clips, ungroup_clips, list_groups + Kdenlive interop test"
```

---

### Task 5: Final verification + merge to main

**Files:** No new code.

- [ ] **Step 1: Run the full test suite one more time**

```bash
cd /home/ah64/apps/mlt-pipeline-2a/pyagent-kdenlive-guide
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
PYTHONPATH=. pytest -q --no-header
```

Expected: 252 passed, 1 skipped (or 251 passed, 2 skipped in CI without Kdenlive).

- [ ] **Step 2: Verify all 10 new tools are exposed**

```bash
cd /home/ah64/apps/mlt-pipeline-2a/pyagent-kdenlive-guide
PYTHONPATH=. python3 -c "from phase3_pyagent_core.runtime import list_tools; ts=list_tools(); print(len(ts)); print(sorted([t['name'] for t in ts if 'slip' in t['name'] or 'ripple' in t['name'] or 'speed' in t['name'] or 'split' in t['name'] or 'replace' in t['name'] or 'remove' in t['name'] or 'group' in t['name']]))"
```

Expected: 29 (19 existing + 10 new), and a list of 10 tool names sorted alphabetically.

- [ ] **Step 3: Verify the spec's definition-of-done checklist**

Run through each item in the spec's "Definition of done" section and confirm it passes. Common checks:

```bash
# Every new prod file is <300 lines
wc -l phase2_project_engine/ops/clips_edit.py phase2_project_engine/ops/groups.py phase3_pyagent_core/tools/clips_edit.py phase3_pyagent_core/tools/groups.py
# All should be under 300

# Every new test file is <400 lines
wc -l phase2_project_engine/tests/test_ops_groups.py
# Should be under 400
```

- [ ] **Step 4: Verify the 19 existing tools' golden fixtures are unchanged**

```bash
cd /home/ah64/apps/mlt-pipeline-2a/pyagent-kdenlive-guide
git diff main phase3_pyagent_core/tests/fixtures/golden_io.json | head -20
```

Expected: only the 10 NEW entries differ from main; the 5 existing entries are byte-identical.

- [ ] **Step 5: Merge to main**

The user has the option of:
- **Local merge:** from the main repo root, `git checkout main && git merge add-editor-tools-2a` (the standard flow; resolves any conflict in BUGS_FIXED.md by keeping the cleanup's version)
- **PR:** push the branch and open a PR; the cleanup branch protection rules apply

Use the user's preferred flow. If unclear, default to local merge (the cleanup was merged locally).

- [ ] **Step 6: Clean up worktree**

```bash
cd /home/ah64/apps/mlt-pipeline
git worktree remove /home/ah64/apps/mlt-pipeline-2a --force
git worktree prune
git branch -d add-editor-tools-2a
```

Expected: worktree gone, branch deleted, main has 4 new commits on top.

- [ ] **Step 7: Update `BUGS_FIXED.md` if any 2a bugs were found**

If any bugs were found and fixed during 2a implementation, append a one-line entry per bug to `BUGS_FIXED.md` (in `pyagent-kdenlive-guide/`) with the format:
```
| 2026-07-19 | 2a | <short description> | <file:line> |
```

If no bugs were found, skip this step.

---

## Self-review

- [x] **Spec coverage:** All 10 tools are in Task 1, 2, 3, 4. Real-Kdenlive format is in Task 4 Step 1. `group_name` as handle is in Task 4 Step 1. 4 commits by domain is in Tasks 1-4. 3 test layers are in each task. Definition of done is in Task 5.
- [x] **Placeholder scan:** No "TBD" / "TODO" / "implement later" patterns.
- [x] **Type consistency:** `slip_clip(tree, clip_id, delta_sec)`, `ripple_delete_clip(tree, clip_id)`, `change_clip_speed(tree, clip_id, rate)`, `split_clip(tree, clip_id, at_sec)`, `replace_clip_source(tree, clip_id, new_source_id)`, `remove_effect(tree, clip_id, effect_index)`, `remove_transition(tree, transition_id)`, `group_clips(tree, clip_ids, group_name)`, `ungroup_clips(tree, group_name)`, `list_groups(tree)` — all consistent across task steps.
- [x] **Property key:** `kdenlive:sequenceproperties.groups` used in Task 4 Steps 1, 4, 9 consistently.
- [x] **Test count math:** 231 baseline + 10 (clips-edit) + 2 (effects) + 2 (transitions) + 7 (groups) = 252. Verified against the spec's test count budget.
- [x] **Test file paths:** All in `phase2_project_engine/tests/test_ops_<domain>.py` per the existing convention. Golden fixtures in `phase3_pyagent_core/tests/fixtures/golden_io.json`.
