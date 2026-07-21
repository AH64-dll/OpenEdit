# Milestone 3 Handoff Report: Operation Replay & Derived State Architecture

**Author**: Explorer 3  
**Target Audience**: Worker 3 / Orchestrator  
**Date**: 2026-07-21  

---

## 1. Observation

### Observation 1.1: State Derivation Architecture (`derive_timeline` & Operational Log)
- **File**: `open_edit/ir/apply.py` (lines 344–356)
```python
def derive_timeline(project: Project) -> Timeline:
    """Replay all non-reverted, applied operations in sequence order."""
    timeline = Timeline()
    for op in project.edit_graph:
        timeline = apply_operation(timeline, op)
    max_end = 0.0
    for track in timeline.tracks:
        for clip in track.clips:
            end = clip.position_sec + (clip.out_point_sec - clip.in_point_sec)
            if end > max_end:
                max_end = end
    timeline.duration_sec = max_end
    return timeline
```
- **File**: `open_edit/storage/edit_graph.py` (lines 91–102)
```python
    def load_all(self) -> list[OperationUnion]:
        """Load all operations in sequence_num order."""
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT payload, status FROM edits ORDER BY sequence_num"
            )
            ops: list[OperationUnion] = []
            for row in cur.fetchall():
                op = TypeAdapter(OperationUnion).validate_json(row[0])
                op.status = row[1]
                ops.append(op)
            return ops
```
- **File**: `open_edit/storage/schema.sql` (lines 11–21)
```sql
CREATE TABLE IF NOT EXISTS edits (
    edit_id      TEXT PRIMARY KEY,
    parent_id    TEXT,
    kind         TEXT NOT NULL,
    author       TEXT NOT NULL,
    timestamp    TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('applied', 'reverted', 'superseded')),
    sequence_num INTEGER NOT NULL,
    payload      TEXT NOT NULL,
    FOREIGN KEY (parent_id) REFERENCES edits(edit_id)
);
```
- **Finding**: State derivation operates on an append-only operational log (`edits` table in SQLite `edit_graph.db`). Operations are loaded strictly sorted by integer `sequence_num`, deserialized into Pydantic models (`OperationUnion`), assigned to `project.edit_graph`, and replayed sequentially via `apply_operation` starting from a fresh `Timeline()` instance.

---

### Observation 1.2: Immutability and Purity Invariants
- **File**: `open_edit/ir/apply.py` (lines 67–71)
```python
def apply_operation(timeline: Timeline, op: OperationUnion) -> Timeline:
    """Apply a single operation to a timeline. Returns a new timeline.

    Pure function. Does not mutate the input.
    """
```
- **File**: `open_edit/ir/apply.py` (lines 75–83, 84–95, 106–108, 148–172, 245–251, 294, 312)
  - `AddClipOp` (lines 76, 78):
    ```python
    track = _get_or_create_track(timeline, op.track_id, op.track_kind) # appends to timeline.tracks in-place
    track.clips.append(_make_clip(op, out_val))                         # appends to track.clips in-place
    ```
  - `RemoveClipOp` (line 82):
    ```python
    track.clips = [c for c in track.clips if c.clip_id != op.clip_id]   # mutates track.clips in-place
    ```
  - `MoveClipOp` (lines 88, 94):
    ```python
    track.clips.pop(i)                                                  # mutates track.clips in-place
    new_track.clips.append(moved)                                       # mutates new_track.clips in-place
    ```
  - `TrimClipOp` (line 107):
    ```python
    track.clips[i] = new_clip                                           # mutates track.clips list element in-place
    ```
  - `AddTransitionOp` (lines 247–250):
    ```python
    track.clips[i] = new_clip_a / new_clip_b                            # mutates track.clips in-place
    ```
  - `NormalizeAudioOp` (line 170):
    ```python
    timeline.tracks[idx] = new_track                                    # mutates timeline.tracks in-place
    ```
- **Finding**: Despite the docstring explicitly asserting `"Pure function. Does not mutate the input"`, `apply_operation` **mutates the input `timeline` instance in-place**. `derive_timeline` works because it passes a freshly instantiated `Timeline()` object, but callers passing an existing `Timeline` projection will have their instance mutated.

---

### Observation 1.3: Handling of Status Flags (`'applied'`, `'reverted'`, `'superseded'`)
- **File**: `open_edit/ir/apply.py` (line 72)
```python
    if op.status != "applied":
        return timeline
```
- **File**: `open_edit/ir/validate.py` (line 76)
```python
    if op.status != "applied":
        return errors
```
- **File**: `open_edit/ir/validate.py` (lines 43–47)
```python
def _known_clip_ids(project: Project) -> set[str]:
    known: set[str] = set()
    for op in project.edit_graph:
        if isinstance(op, AddClipOp) and op.status == "applied":
            known.add(op.clip_id)
        elif isinstance(op, RemoveClipOp) and op.status == "applied":
            known.discard(op.clip_id)
    return known
```
- **Finding**:
  - `apply_operation` checks `op.status != "applied"` and immediately returns `timeline` unchanged for any non-applied status (`reverted` or `superseded`).
  - OpenEdit relies on full replay from the operational log rather than inverse operation undo stacks. Reverting an edit changes its `status` in SQLite (`EditGraphStore.update_status`), causing subsequent `derive_timeline` calls to omit the operation cleanly.

---

### Observation 1.4: 13 Operations Unhandled in `apply_operation`
- **File**: `open_edit/ir/types.py` (lines 263–276)
  `OperationUnion` defines 24 concrete operation classes.
- **File**: `open_edit/ir/apply.py` (lines 75–124)
  `apply_operation` contains `if isinstance(...)` branches for ONLY 11 operation classes (`AddClipOp`, `RemoveClipOp`, `MoveClipOp`, `TrimClipOp`, `AddTransitionOp`, `AddEffectOp`, `SetKeyframeOp`, `SetAudioGainOp`, `NormalizeAudioOp`, `GroupEditsOp`, `FreeFormCodeOp`).
- **Missing Operation Handlers** (13 operations fall through to `return timeline` without performing any action):
  1. `RemoveTransitionOp`
  2. `SetTransitionPropertyOp`
  3. `RemoveEffectOp`
  4. `SetEffectParamOp`
  5. `RemoveKeyframeOp`
  6. `SlipClipOp`
  7. `RippleDeleteClipOp`
  8. `ChangeClipSpeedOp`
  9. `SplitClipOp`
  10. `ReplaceClipSourceOp`
  11. `SetClipSpeedRampOp`
  12. `UngroupEditsOp`
  13. `RawMltXmlOp`
- **Finding**: High-level editing operations supported by `open_edit.ir.api.IR` (such as `split_clip`, `slip_clip`, `remove_effect`, `set_effect_param`, `change_clip_speed`, `replace_clip_source`, `ripple_delete_clip`) are saved to `edit_graph.db` and pass validation in `sandbox_bridge.py`, but are **silently ignored** during timeline state derivation.

---

### Observation 1.5: Edge Cases in State Derivation
- **Ops Out of Order / Reordering**:
  - In `apply_operation`: if a `TrimClipOp`, `MoveClipOp`, or `AddEffectOp` occurs in `edit_graph` before the `AddClipOp` that creates the target `clip_id`, `_find_clip` returns `None`. The operation silently returns `timeline` without raising an error. The edit is ignored, and when `AddClipOp` runs later, the clip is added in its untrimmed/unmoved default state.
- **Missing Target Clips/Tracks**:
  - Most operations (`RemoveClipOp`, `MoveClipOp`, `TrimClipOp`, `AddEffectOp`, `SetKeyframeOp`, `SetAudioGainOp`, `NormalizeAudioOp`) silently ignore missing targets and return `timeline` unchanged.
  - **Exception**: `AddTransitionOp` in `_apply_add_transition` (lines 205–231) checks clip bounds and asset range inversions, raising a hard **`ValueError`** if the transition duration exceeds clip bounds or causes negative asset ranges. This inconsistency causes `derive_timeline` to crash on bad transitions while silently ignoring other missing targets.
- **Duplicate Operations**:
  - Duplicate `clip_id`s in `AddClipOp`: neither `types.py` nor `validate_op` checks for duplicate `clip_id`s. If two `AddClipOp`s use the same `clip_id`, `apply_operation` appends both clips to `track.clips`. Subsequent `_find_clip` calls will always resolve to the first clip, leaving the duplicate clip inaccessible to targeted ops.
  - Duplicate `edit_id`s: prevented at the database level by `PRIMARY KEY (edit_id)` in `schema.sql`.
- **Invalid Schema / Parameter Constraints**:
  - `types.py` models lack field validation bounds for numeric fields (e.g. `position_sec`, `in_point_sec` are unconstrained floats without `Field(ge=0)`). If an operation with negative position or inverted in/out points bypasses `validate_op` and enters `apply_operation`, it creates corrupted `Clip` objects on the timeline.

---

## 2. Logic Chain

1. **Replay Determinism**:
   - `derive_timeline` relies on sequential iteration over `project.edit_graph` ordered by SQLite `sequence_num`.
   - Because `load_all()` uses `ORDER BY sequence_num`, operational log replay is deterministic across project reopens.
   - However, because 13 op types fall through `apply_operation` without handling, any project containing high-level ops (e.g. `split_clip`, `slip_clip`, `remove_effect`) will produce an incomplete derived timeline state.

2. **Purity / Immutability Risk**:
   - Callers (such as speculative agent preview tools or test harnesses) might assume `apply_operation(current_timeline, proposed_op)` is pure and returns a new timeline while leaving `current_timeline` untouched.
   - Because `apply_operation` mutates `timeline.tracks` and `track.clips` in-place, speculative execution will corrupt `current_timeline`.
   - Therefore, `apply_operation` must either perform a structural deep copy (`timeline.model_copy(deep=True)` or list copying) to satisfy its purity contract, OR the contract/docstring must be explicitly changed to document in-place mutation.

3. **Status Flag Consistency**:
   - Filtering on `op.status == "applied"` in `apply_operation` and `validate_op` correctly ignores `reverted` and `superseded` ops during replay.
   - However, when an operation creating a target (e.g. `AddClipOp`) is marked `reverted`, subsequent applied operations targeting that `clip_id` (e.g. `TrimClipOp`) find `_find_clip(...) == None` and silently no-op. While safe from crashing, this leaves orphaned applied ops in `edit_graph`.

4. **Edge Case Handling Inconsistency**:
   - Most operations silently ignore missing target clips or tracks, returning `timeline` unmodified.
   - In contrast, `AddTransitionOp` raises a hard `ValueError` when transition bounds are invalid.
   - This asymmetry means that missing clip errors fail silently, whereas bad transition parameters crash `derive_timeline`.

---

## 3. Caveats

- **No Caveats**: All 5 requested tasks have been fully investigated across `open_edit/ir/types.py`, `open_edit/storage/edit_graph.py`, `open_edit/ir/apply.py`, `open_edit/ir/validate.py`, `open_edit/ir/api.py`, and `open_edit/agent/sandbox_bridge.py`.

---

## 4. Conclusion & Recommendations for Worker 3

### Summary Assessment
The state derivation mechanism via `derive_timeline` and `EditGraphStore` provides a clean, WAL-backed SQLite operational log replay architecture. However, 13 operations defined in `OperationUnion` are currently unhandled in `apply_operation`, `apply_operation` violates its purity/immutability docstring contract by mutating inputs in-place, and edge case error handling is inconsistent between silent no-ops and hard `ValueError` exceptions.

### Actionable Design & Implementation Guidelines for Worker 3

1. **Implement Missing 13 Operation Handlers in `apply_operation`**:
   - `RemoveTransitionOp`: Remove transition effect with matching `transition_id` from `clip_a.effects`.
   - `SetTransitionPropertyOp`: Update property in transition effect `params`.
   - `RemoveEffectOp`: Remove effect at `effect_index` from target clip's `effects` list.
   - `SetEffectParamOp`: Update `eff.params[op.param_name] = op.value` for target effect on clip.
   - `RemoveKeyframeOp`: Discard keyframe entry at `op.frame` from `eff.keyframes[op.param]`.
   - `SlipClipOp`: Adjust asset `in_point_sec` and `out_point_sec` by `delta_sec` while keeping `position_sec` unchanged.
   - `RippleDeleteClipOp`: Remove clip and shift all subsequent clips on the same track to the left by `(out_point_sec - in_point_sec)`.
   - `ChangeClipSpeedOp`: Adjust clip duration / playback rate (`rate`).
   - `SplitClipOp`: Replace original clip with two clips (`left_clip_id` spanning `[in, in + at_sec]`, `right_clip_id` spanning `[in + at_sec, out]`).
   - `ReplaceClipSourceOp`: Update clip's `asset_hash` to `new_asset_hash`.
   - `SetClipSpeedRampOp`: Store speed ramp keyframes on clip metadata.
   - `UngroupEditsOp`: Metadata no-op (return `timeline`).
   - `RawMltXmlOp`: Passthrough or raw filter tag on clip/track.

2. **Enforce Immutability in `apply_operation`**:
   - Either make `apply_operation` truly pure by creating fresh `Timeline`, `Track`, and `Clip` copies via `model_copy(deep=True)` / list comprehensions, OR update documentation if in-place mutation is explicitly intended for performance during `derive_timeline`.

3. **Standardize Error Handling Strategy for Edge Cases**:
   - Decide whether invalid operation parameters should raise `ApplyError` / `ValueError` OR fail gracefully (logging a warning and returning unmodified `timeline`).
   - Wrap `AddTransitionOp` bounds errors in `ApplyError` or handle them consistently with other operations.

4. **Add Duplicate `clip_id` & Numeric Bound Validations**:
   - Enforce non-negative numeric constraints on `position_sec` and `in_point_sec` in `types.py` (e.g. `Field(ge=0.0)`).
   - Add duplicate `clip_id` check in `validate_op` when `AddClipOp` is processed.

---

## 5. Verification Method

To independently verify all findings and validate any upcoming implementation by Worker 3:

1. **Run Full Test Suite**:
   ```bash
   pytest open_edit/tests/test_ir/
   ```
   *Expected result*: 81 tests pass.

2. **Inspect Unhandled Operations in `apply.py`**:
   Run grep for handled operation types vs `OperationUnion`:
   ```bash
   grep -n "isinstance(op," open_edit/open_edit/ir/apply.py
   ```
   *Verification*: Observe that 13 classes (`SplitClipOp`, `SlipClipOp`, `RemoveEffectOp`, etc.) have no `isinstance` branch in `apply_operation`.

3. **Verify In-Place Mutation Behavior**:
   Execute Python snippet:
   ```python
   from open_edit.ir.types import Timeline, AddClipOp
   from open_edit.ir.apply import apply_operation

   t1 = Timeline()
   op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
   t2 = apply_operation(t1, op)
   assert t1 is t2  # True: t1 was mutated in-place
   assert len(t1.tracks) == 1  # True: input object modified
   ```

4. **Invalidation Conditions**:
   - If `apply_operation` is modified to implement structural copy, `t1 is not t2` and `len(t1.tracks) == 0` will hold.
   - If missing 13 operation handlers are added to `apply.py`, `pytest` on new operational replay tests will pass.
