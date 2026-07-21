# Handoff Report: Milestone 3 — Operation Replay & Derived State Investigation

**Agent**: Explorer 1 (`explorer_m3_1`)  
**Target File**: `/home/ah64/apps/mlt-pipeline/.agents/explorer_m3_1/handoff.md`  
**Date**: 2026-07-21  

---

## 1. Observation

### 1.1 Project Structure & File Locations
The Open Edit core python package is located at `/home/ah64/apps/mlt-pipeline/open_edit/open_edit/`. Key files investigated:
- `open_edit/open_edit/ir/apply.py` (357 lines): Functions `apply_operation`, `derive_timeline`, `_apply_free_form_code`, and helper functions `_apply_add_transition`, `_apply_add_effect`, `_apply_set_keyframe`, `_apply_set_audio_gain`, `_apply_normalize_audio`.
- `open_edit/open_edit/ir/types.py` (286 lines): Definitions for `Timeline`, `Track`, `Clip`, `Effect`, `Asset`, `Project`, base `Operation`, and 24 concrete operation subclasses forming `OperationUnion`.
- `open_edit/open_edit/storage/edit_graph.py` (141 lines): SQLite-backed operation graph store (`EditGraphStore`) managing operation persistence, sequence ordering, and status updates.
- `open_edit/open_edit/storage/schema.sql` (37 lines): SQLite table schema (`edits` table with `status IN ('applied', 'reverted', 'superseded')` and `sequence_num`).
- `open_edit/open_edit/ir/validate.py` (179 lines): Operation validation rules against project state.
- `open_edit/open_edit/ir/api.py` (415 lines): Free-form Python IR API used by AI agent sandbox.
- `open_edit/tests/test_ir/test_apply.py` (382 lines): Test suite for `apply.py`.
- `open_edit/tests/test_ir/test_types.py` (203 lines): Test suite for Pydantic operation types.

### 1.2 Test Suite Execution
Executed `pytest open_edit/tests/test_ir/` in working directory `/home/ah64/apps/mlt-pipeline`:
- **Result**: 81 passed in 0.36s.

### 1.3 Operation Coverage Analysis
`open_edit/open_edit/ir/types.py` defines 24 distinct operation subclasses of `Operation` included in `OperationUnion`:
1. `AddClipOp`
2. `RemoveClipOp`
3. `MoveClipOp`
4. `TrimClipOp`
5. `AddTransitionOp`
6. `RemoveTransitionOp`
7. `SetTransitionPropertyOp`
8. `AddEffectOp`
9. `RemoveEffectOp`
10. `SetEffectParamOp`
11. `SetKeyframeOp`
12. `RemoveKeyframeOp`
13. `SlipClipOp`
14. `RippleDeleteClipOp`
15. `ChangeClipSpeedOp`
16. `SplitClipOp`
17. `ReplaceClipSourceOp`
18. `SetClipSpeedRampOp`
19. `SetAudioGainOp`
20. `NormalizeAudioOp`
21. `GroupEditsOp`
22. `UngroupEditsOp`
23. `RawMltXmlOp`
24. `FreeFormCodeOp`

Examining `apply_operation` in `open_edit/open_edit/ir/apply.py` (lines 75-124):
- **Currently Handled (11 ops)**: `AddClipOp`, `RemoveClipOp`, `MoveClipOp`, `TrimClipOp`, `AddTransitionOp`, `AddEffectOp`, `SetKeyframeOp`, `SetAudioGainOp`, `NormalizeAudioOp`, `GroupEditsOp` (no-op pass-through), `FreeFormCodeOp` (no-op pass-through).
- **Unhandled / Fallthrough No-Op (13 ops)**: `RemoveTransitionOp`, `SetTransitionPropertyOp`, `RemoveEffectOp`, `SetEffectParamOp`, `RemoveKeyframeOp`, `SlipClipOp`, `RippleDeleteClipOp`, `ChangeClipSpeedOp`, `SplitClipOp`, `ReplaceClipSourceOp`, `SetClipSpeedRampOp`, `UngroupEditsOp`, `RawMltXmlOp`.

### 1.4 Code Snippets & Status Handling
- **Status Filtering (`apply.py:72-73`)**:
  ```python
  if op.status != "applied":
      return timeline
  ```
- **Timeline Derivation (`apply.py:344-356`)**:
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
- **Database Ordering (`edit_graph.py:91-102`)**:
  ```python
  def load_all(self) -> list[OperationUnion]:
      """Load all operations in sequence_num order."""
      with self._conn() as conn:
          cur = conn.execute(
              "SELECT payload, status FROM edits ORDER BY sequence_num"
          )
          ...
  ```

---

## 2. Logic Chain

1. **Observation**: `open_edit/ir/types.py` defines 24 operation subclasses in `OperationUnion`, but `open_edit/ir/apply.py:75-124` only contains `if isinstance(...)` handlers for 11 operation types.
   - **Reasoning**: Unhandled operation types fall through to `return timeline` on line 124. When `derive_timeline` replays an edit graph containing any of these 13 operation types, the operations are silently ignored and produce no state change in the derived `Timeline`.
   - **Conclusion**: Handlers for all 13 missing operations must be added to `apply.py`.

2. **Observation**: `apply_operation` docstring (`apply.py:68-70`) claims: `"Pure function. Does not mutate the input."` However, lines 78 (`track.clips.append`), 88 (`track.clips.pop`), 107 (`track.clips[i] = new_clip`), 148, 169 mutate `timeline.tracks` and `track.clips` in place.
   - **Reasoning**: In-place mutation works inside `derive_timeline` because `timeline = Timeline()` instantiates a fresh timeline at the start of replay. However, callers outside `derive_timeline` passing an existing `Timeline` object will have their input object mutated.
   - **Conclusion**: `apply_operation` should either make deep/model copies of tracks/clips when modifying state, or docstrings should be updated to clarify in-place mutation semantics during replay.

3. **Observation**: Revert/undo filtering relies on `if op.status != "applied": return timeline` (line 72).
   - **Reasoning**: When an operation's status is changed to `"reverted"` in SQLite via `store.update_status(edit_id, "reverted")`, `load_all()` loads the updated status. During `derive_timeline` replay, `apply_operation` skips all reverted ops. Since replay starts from an empty `Timeline()`, skipping reverted operations cleanly reconstructs the timeline state without needing inverse delta operations.
   - **Sub-Reasoning (Bug/Edge Case)**: Parent-child operations (such as `FreeFormCodeOp` spawning child `AddClipOp`s with `parent_id = free_form_op.edit_id`) pose a risk if only the parent op's status is updated to `"reverted"`. If child ops retain `status == "applied"`, `apply_operation` currently checks only `op.status` and will continue to apply the child ops during replay.
   - **Conclusion**: `derive_timeline` or `apply_operation` must verify parent op status (or `update_status` must recursively update child ops) to prevent orphaned child ops from executing when a parent container op is reverted.

4. **Observation**: Baseline empty project handling in `derive_timeline`:
   - **Reasoning**: When `project.edit_graph` is empty, `derive_timeline` returns `Timeline(tracks=[], duration_sec=0.0)`.
   - **Edge Case**: `AddClipOp` has `out_point_sec: Optional[float] = None`. Line 77 in `apply.py` converts `None` to `0.0`: `out_val = op.out_point_sec if op.out_point_sec is not None else 0.0`. If a clip is added without an explicit `out_point_sec`, clip duration defaults to 0.0s unless asset metadata (duration) is supplied or `out_point_sec` is required.

---

## 3. Caveats

- **Read-Only Investigation**: No source code files were modified during this investigation.
- **Renderer Dependencies**: Speed operations (`ChangeClipSpeedOp`, `SetClipSpeedRampOp`) and raw MLT XML operations (`RawMltXmlOp`) require coordination with Phase 4 MLT render emitter logic.
- **Commutativity Reordering**: Operation reordering tests rely on `open_edit/ir/commutativity.py`. Adding new operation handlers to `apply.py` will require extending `commutativity.py` and `validate.py` as well.

---

## 4. Conclusion & Recommended Implementation Steps for Worker 3

### 4.1 Summary of Findings
1. `apply.py` is missing handlers for 13 operation types.
2. Status filtering for revert/undo works cleanly via full sequence replay, but parent-child cascading reverts require parent status checking.
3. Empty baseline projects return a clean 0-duration empty timeline.
4. In-place mutation in `apply_operation` diverges from its purity docstring.

### 4.2 Recommended Implementation Steps for Worker 3

1. **Implement Missing 13 Operation Handlers in `open_edit/open_edit/ir/apply.py`**:
   - `RemoveTransitionOp`: Locate clip with matching transition effect (`effect_id` or `params["clip_b_id"]`) and remove transition effect.
   - `SetTransitionPropertyOp`: Find transition effect by `transition_id`, update parameter `prop_name` to `value`.
   - `RemoveEffectOp`: Locate clip/track `clip_id`, remove effect at `effect_index`.
   - `SetEffectParamOp`: Update parameter `param_name = value` for effect at `effect_index` or matching `effect_id` on target clip.
   - `RemoveKeyframeOp`: Remove keyframe at `frame` for `param` on `effect_id`.
   - `SlipClipOp`: Shift media range (`in_point_sec += delta_sec`, `out_point_sec += delta_sec`) while keeping timeline `position_sec` and clip duration unchanged.
   - `RippleDeleteClipOp`: Remove target clip and shift all subsequent clips on the same track left by `(out_point_sec - in_point_sec)`.
   - `ChangeClipSpeedOp`: Adjust playback speed multiplier on clip.
   - `SplitClipOp`: Split clip at `at_sec` into `left_clip_id` and `right_clip_id`, replacing original clip with left and right clip halves.
   - `ReplaceClipSourceOp`: Update `clip.asset_hash = op.new_asset_hash`.
   - `SetClipSpeedRampOp`: Attach or update speed ramp keyframes.
   - `UngroupEditsOp`: Explicit pass-through no-op return.
   - `RawMltXmlOp`: Pass-through no-op return (or store in timeline metadata).

2. **Fix Parent-Child Revert Handling**:
   - In `derive_timeline`, maintain a set of reverted/superseded parent operation IDs.
   - If an operation has `parent_id` matching a reverted/superseded parent op, skip it during replay.

3. **Update Validation (`validate.py`) and Commutativity (`commutativity.py`)**:
   - Ensure `validate_op` has validation branches for all new operations.
   - Ensure `can_swap` in `commutativity.py` handles new operation types safely.

4. **Expand Test Suite (`open_edit/tests/test_ir/test_apply.py`)**:
   - Add unit tests for every newly implemented operation handler.
   - Add test for parent-child cascading revert in `derive_timeline`.
   - Add test for empty project baseline replay.

---

## 5. Verification Method

To independently verify the implementation:

1. **Run Full Test Suite**:
   ```bash
   pytest open_edit/tests/test_ir/
   pytest open_edit/tests/test_e2e.py
   ```
2. **Verify Operation Coverage**:
   Ensure all 24 concrete operation classes in `open_edit/open_edit/ir/types.py` are explicitly handled in `open_edit/open_edit/ir/apply.py` without falling through to default `return timeline`.
3. **Invalidation Conditions**:
   - If any `pytest` test fails.
   - If calling `derive_timeline` on a project with `RemoveEffectOp`, `SplitClipOp`, or `RippleDeleteClipOp` fails to update `Timeline` state.
