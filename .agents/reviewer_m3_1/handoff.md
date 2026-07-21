# Milestone 3 Review Handoff Report & Detailed Audit

**Working Directory**: `/home/ah64/apps/mlt-pipeline/.agents/reviewer_m3_1`  
**Review Target**: `open_edit/open_edit/ir/apply.py` & `open_edit/tests/test_ir/test_apply.py`  
**Verdict**: **FAIL (REQUEST_CHANGES)**

---

## 1. Observation

### Test Execution
Command executed:
```bash
PYTHONPATH=open_edit python3 -m unittest discover -s open_edit/tests
```
Output:
```
Ran 123 tests in 0.512s
OK
```
All 123 unit tests pass, including the 36 tests in `open_edit/tests/test_ir/test_apply.py`.

---

### OperationUnion Coverage
Inspected `open_edit/open_edit/ir/types.py` (lines 263-276). All 24 operation types in `OperationUnion` are present:
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

In `open_edit/open_edit/ir/apply.py`, `apply_operation` (lines 80-157) contains explicit handling or delegation for all 24 operation types.

---

### Key Findings & Defects Observed

#### Finding 1 [Major]: In-Place Mutation Violating Immutability Docstring Contract
- **Location**: `open_edit/open_edit/ir/apply.py`, lines 81-84 & internal helpers (`_get_or_create_track`, `MoveClipOp`, `TrimClipOp`, `_apply_add_clip`, etc.)
- **Docstring Claim**:
  ```python
  def apply_operation(timeline: Timeline, op: OperationUnion) -> Timeline:
      """Apply a single operation to a timeline. Returns a new timeline.

      Pure function. Does not mutate the input.
      """
  ```
- **Observed Behavior**:
  Running the following snippet:
  ```python
  from open_edit.ir.apply import apply_operation
  from open_edit.ir.types import AddClipOp, Timeline

  t1 = Timeline()
  op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
  t2 = apply_operation(t1, op)
  print(t1 is t2)  # Output: True
  print(len(t1.tracks))  # Output: 1
```
  `apply_operation` mutates `t1.tracks` and clip lists in place rather than returning a new copied `Timeline`. `t1 is t2` evaluates to `True`.

---

#### Finding 2 [Major]: `SetKeyframeOp` Ignores Track-Level Effects
- **Location**: `open_edit/open_edit/ir/apply.py`, lines 530-544 (`_apply_set_keyframe`)
- **Observed Code**:
  ```python
  def _apply_set_keyframe(timeline: Timeline, op: SetKeyframeOp) -> Timeline:
      for track in timeline.tracks:
          for i, clip in enumerate(track.clips):
              for j, eff in enumerate(clip.effects):
                  if eff.effect_id == op.effect_id:
                      ...
                      return timeline
      return timeline
```
- **Contrast with `_apply_remove_keyframe`** (lines 250-263):
  `_apply_remove_keyframe` checks both `clip.effects` AND `track.effects`.
- **Observed Behavior**:
  When an effect is added to a track via `AddEffectOp(target_kind="track")` or `NormalizeAudioOp(target_kind="track")`, `SetKeyframeOp` targeting `effect_id` on `track.effects` fails to find the effect and silently does nothing.
- **Verification snippet result**:
  ```python
  t = Timeline(
      tracks=[
          Track(
              track_id="t1",
              kind="video",
              effects=[Effect(effect_id="eff_track", effect_type="volume")],
          )
      ]
  )
  op = SetKeyframeOp(
      author="user",
      effect_id="eff_track",
      param="gain",
      keyframes=[(0.0, 1.0, "linear")],
  )
  t2 = apply_operation(t, op)
  # t2.tracks[0].effects[0].keyframes remains {}
```

---

#### Finding 3 [Minor]: Missing Test Coverage for Track-Level Keyframes & Deep Hierarchy
- **Location**: `open_edit/tests/test_ir/test_apply.py`
- **Observed**: `test_apply.py` lacks unit tests for track-level keyframing (`SetKeyframeOp` on track effects) and multi-level parent operation status hierarchy resolution (e.g. grandparent reverted -> parent applied -> child applied).

---

## 2. Logic Chain

1. **Task 1 & Test Suite**: `PYTHONPATH=open_edit python3 -m unittest discover -s open_edit/tests` passed with 123 tests OK. Inspection confirmed all 24 operation types in `OperationUnion` are handled by `apply_operation`.
2. **Task 2 (Structural Purity & Immutability)**: The interface contract in `apply_operation` promises structural purity ("Does not mutate the input"). However, step-by-step tracing and execution revealed in-place list modification (`tracks.append`, `clips.pop`, `clips[i] = ...`). This violates immutability and can cause subtle bugs when caller code expects input timelines to remain immutable snapshots.
3. **Task 2 (Effect Target Handling)**: `SetKeyframeOp` has no `clip_id` field (only `effect_id`). Track-level effects created via `target_kind="track"` store their effects in `track.effects`. In `_apply_set_keyframe`, only `clip.effects` is searched, leaving `track.effects` unhandled.
4. **Task 3 (derive_timeline Status & Hierarchy)**: `derive_timeline` filters `op.status != "applied"` (excluding both `"reverted"` and `"superseded"`) and traverses the `parent_id` chain. If any ancestor is non-applied, the child op is skipped. The status filtering logic is correct.
5. **Verdict**: Because Finding 1 breaks the structural purity contract and Finding 2 causes functional silent failure for track-level keyframing, the verdict is **FAIL (REQUEST_CHANGES)**.

---

## 3. Caveats

- `GroupEditsOp`, `UngroupEditsOp`, `RawMltXmlOp`, and `FreeFormCodeOp` are no-ops in `apply_operation` for timeline derivation because they represent organizational metadata or code blocks expanded at build time (`FreeFormCodeOp` child ops are generated via `_apply_free_form_code` and replayed). This design is intended and sound.
- No external network access or modifications were performed on the source code (Review-only mode strictly maintained).

---

## 4. Conclusion

- **Verdict**: **FAIL (REQUEST_CHANGES)**
- **Required Fixes**:
  1. Update `apply_operation` to ensure input `timeline` is not mutated in-place (e.g. `timeline = timeline.model_copy(deep=True)` at entry, or rebuild `tracks` / `clips` immutably).
  2. Update `_apply_set_keyframe` in `apply.py` to search `track.effects` in addition to `clip.effects` (matching `_apply_remove_keyframe`).
  3. Add corresponding unit tests in `test_apply.py` covering track-level `SetKeyframeOp` and multi-level parent op hierarchy.

---

## 5. Verification Method

To verify these findings independently:

1. **Immutability Verification**:
   ```bash
   PYTHONPATH=open_edit python3 -c "
   from open_edit.ir.types import Timeline, AddClipOp
   from open_edit.ir.apply import apply_operation
   t1 = Timeline()
   op = AddClipOp(author='user', asset_hash='a', track_id='v1', position_sec=0.0)
   t2 = apply_operation(t1, op)
   assert t1 is not t2, 'Purity violation: t1 and t2 are same instance'
   assert len(t1.tracks) == 0, 'Purity violation: t1 was mutated in-place'
   "
   ```

2. **Track-Level SetKeyframe Verification**:
   ```bash
   PYTHONPATH=open_edit python3 -c "
   from open_edit.ir.types import Timeline, Track, Effect, SetKeyframeOp
   from open_edit.ir.apply import apply_operation
   t = Timeline(tracks=[Track(track_id='t1', kind='video', effects=[Effect(effect_id='eff_track', effect_type='volume')])])
   op = SetKeyframeOp(author='user', effect_id='eff_track', param='gain', keyframes=[(0.0, 1.0, 'linear')])
   t2 = apply_operation(t, op)
   assert 'gain' in t2.tracks[0].effects[0].keyframes, 'Track-level keyframe not applied'
   "
   ```

3. **Full Test Suite Execution**:
   ```bash
   PYTHONPATH=open_edit python3 -m unittest discover -s open_edit/tests
   ```
