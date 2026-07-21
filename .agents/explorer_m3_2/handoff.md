# Milestone 3 Handoff Report — Operation Replay & Derived State Test Suite Investigation

## 1. Observation

### Existing Test Suite Findings
- **Location of tests**: Test files live in `/home/ah64/apps/mlt-pipeline/open_edit/tests/test_ir/`. (Note: `/home/ah64/apps/mlt-pipeline/tests` directory does not exist).
- **Test execution command**: The project standard test command is `python3 -m unittest discover -s open_edit/tests` (or with `PYTHONPATH=open_edit`).
- **`test_apply.py` structure (`open_edit/tests/test_ir/test_apply.py`)**:
  - Contains 382 lines of code with 20 test functions.
  - Written using pytest top-level functions (`def test_...()`), pytest assertions (`assert ...`), pytest context managers (`pytest.raises(...)`), and helpers (`pytest.approx(...)`).
  - **Does NOT inherit from `unittest.TestCase`**.
- **Runner behavior observation**:
  - `python3 -m unittest discover -s open_edit/tests/test_ir -v` executed **26 tests** exclusively from `test_types.py`.
  - `test_apply.py` (and `test_catalog.py`, `test_commutativity.py`, `test_originating_note_id.py`, `test_validate.py`) were **completely skipped** by Python's `unittest` discover runner because standard `unittest.defaultTestLoader.discover()` only discovers subclasses of `unittest.TestCase`.

### Implementation vs Test Coverage Matrix for `open_edit/ir/apply.py` & `ir/types.py`

| IR Operation / Feature (`types.py`) | Handled in `apply_operation` (`apply.py`) | Tested in `test_apply.py` | Missing Coverage / Status |
|-------------------------------------|-------------------------------------------|---------------------------|---------------------------|
| `AddClipOp`                         | Yes (`_make_clip`, line 75)               | Partial                   | Tested basic track creation & positions; missing overlapping clips, multi-track audio/video combinations. |
| `RemoveClipOp`                      | Yes (line 80)                             | Partial                   | Tested simple removal & non-existent clip ID. |
| `MoveClipOp`                        | Yes (line 84)                             | Partial                   | Tested relocating clip to new track; missing moving non-existent clip, moving to existing track with clips. |
| `TrimClipOp`                        | Yes (line 96)                             | Partial                   | Tested basic in/out trim; missing trim beyond clip boundaries, non-existent clip ID. |
| `AddTransitionOp`                   | Yes (`_apply_add_transition`, line 110)   | Good                      | Tested Bug A centering, duration validation, asset range inversion, already-trimmed clips. Missing missing-clip handling. |
| `RemoveTransitionOp`                | **No** (Falls through line 124)           | **No**                    | Not handled in `apply.py` nor tested. |
| `SetTransitionPropertyOp`           | **No** (Falls through line 124)           | **No**                    | Not handled in `apply.py` nor tested. |
| `AddEffectOp`                       | Yes (`_apply_add_effect`, line 112)       | Partial                   | Tested clip target; missing track target and non-existent target ID. |
| `RemoveEffectOp`                    | **No** (Falls through line 124)           | **No**                    | Not handled in `apply.py` nor tested. |
| `SetEffectParamOp`                  | **No** (Falls through line 124)           | **No**                    | Not handled in `apply.py` nor tested. |
| `SetKeyframeOp`                     | Yes (`_apply_set_keyframe`, line 114)     | Partial                   | Tested clip effect keyframes; missing non-existent effect ID / non-existent clip ID. |
| `RemoveKeyframeOp`                  | **No** (Falls through line 124)           | **No**                    | Not handled in `apply.py` nor tested. |
| `SlipClipOp`                        | **No** (Falls through line 124)           | **No**                    | Not handled in `apply.py` nor tested. |
| `RippleDeleteClipOp`                | **No** (Falls through line 124)           | **No**                    | Not handled in `apply.py` nor tested. |
| `ChangeClipSpeedOp`                 | **No** (Falls through line 124)           | **No**                    | Not handled in `apply.py` nor tested. |
| `SplitClipOp`                       | **No** (Falls through line 124)           | **No**                    | Not handled in `apply.py` nor tested. |
| `ReplaceClipSourceOp`               | **No** (Falls through line 124)           | **No**                    | Not handled in `apply.py` nor tested. |
| `SetClipSpeedRampOp`                | **No** (Falls through line 124)           | **No**                    | Not handled in `apply.py` nor tested. |
| `SetAudioGainOp`                    | Yes (`_apply_set_audio_gain`, line 116)   | **No**                    | Handled in code, but **0 unit tests** in `test_apply.py`. |
| `NormalizeAudioOp`                  | Yes (`_apply_normalize_audio`, line 118)  | Good                      | Tested clip, track, unknown target. |
| `GroupEditsOp`                      | Yes (returns timeline, line 120)          | Basic                     | Tested metadata no-op. |
| `UngroupEditsOp`                    | **No** (Falls through line 124)           | **No**                    | Not handled in `apply.py` nor tested. |
| `RawMltXmlOp`                       | **No** (Falls through line 124)           | **No**                    | Not handled in `apply.py` nor tested. |
| `FreeFormCodeOp`                    | Yes (returns timeline, line 122)          | Basic                     | Tested timeline unchanged on replay. |
| `status == "reverted"`              | Yes (line 72)                             | Basic                     | Tested single reverted op skip. |
| `status == "superseded"`            | Yes (line 72)                             | **No**                    | Never explicitly tested. |
| `EditGraphStore` Integration        | Yes (`storage/edit_graph.py`)             | Disconnected              | Tested in `test_edit_graph.py`, but NO tests verify `EditGraphStore.load_all()` -> `derive_timeline()` pipeline. |

---

## 2. Logic Chain

1. **Test Runner Incompatibility**:
   - `python3 -m unittest discover -s open_edit/tests` is the standard project test verification command.
   - `unittest` test discovery checks module attributes for classes inheriting from `unittest.TestCase`.
   - `open_edit/tests/test_ir/test_apply.py` uses free-standing pytest functions (`def test_...()`), `assert`, `pytest.raises`, and `pytest.approx`.
   - Therefore, `unittest discover` completely skips `test_apply.py`.
   - **Conclusion 1**: `test_apply.py` MUST be refactored into `unittest.TestCase` classes so that `python3 -m unittest discover -s open_edit/tests` discovers and runs all replay tests.

2. **Operation Coverage Gap in Replay**:
   - `types.py` defines 24 concrete operation classes.
   - `apply_operation` in `apply.py` handles 11 operations, returning `timeline` unchanged for the rest.
   - `SetAudioGainOp` is implemented in `apply.py` (lines 299–315), but has **zero test coverage** in `test_apply.py`.
   - 11 operations (`RemoveTransitionOp`, `SetTransitionPropertyOp`, `RemoveEffectOp`, `SetEffectParamOp`, `RemoveKeyframeOp`, `SlipClipOp`, `RippleDeleteClipOp`, `ChangeClipSpeedOp`, `SplitClipOp`, `ReplaceClipSourceOp`, `SetClipSpeedRampOp`) are currently unhandled pass-throughs.
   - **Conclusion 2**: Worker 3 must add unit tests for `SetAudioGainOp`, status handling (`superseded`), and all unhandled operation types (verifying either pass-through immutability or implementing their state derivations if required by M3).

3. **Replay State & Integration Gaps**:
   - `derive_timeline(project)` replays `project.edit_graph`.
   - While `test_edit_graph.py` verifies SQLite persistence (`append`, `load_all`, `update_status`, `reorder`), there is no test suite verifying the end-to-end flow:
     `EditGraphStore` -> `load_all()` -> `Project(edit_graph=ops)` -> `derive_timeline()` -> `Timeline`.
   - Revert/Undo behavior (changing status in `EditGraphStore` from `applied` to `reverted` and re-deriving timeline) is not tested as an integrated workflow.
   - Reordering behavior (swapping sequence numbers via `EditGraphStore.reorder()` and re-deriving timeline) is not tested end-to-end.
   - **Conclusion 3**: Worker 3 must write an integration test class (`TestReplayEditGraphIntegration`) testing state replay directly from `EditGraphStore`.

---

## 3. Caveats

- **Scope Boundary**: Free-form python code execution (`FreeFormCodeOp`) executes scripts via `open_edit.agent.sandbox_bridge.run_free_form`. Unit testing of the sandbox itself is covered in `test_sandbox_bridge.py`. In `apply.py`, replaying a `FreeFormCodeOp` from `edit_graph` is intended to be a timeline no-op because child operations produced by the free-form execution are appended to `edit_graph` with `parent_id == op.edit_id`.
- **Unhandled Operations in `apply.py`**: Several advanced operations (such as `SlipClipOp`, `SplitClipOp`, `RippleDeleteClipOp`) are defined in `types.py` as IR operations. If Worker 3 implements derivation logic for these in `apply.py`, corresponding test cases must be added. If they remain no-ops for Phase 1/M3, tests must assert that applying them leaves the timeline unchanged without crashing.

---

## 4. Conclusion

Existing tests for `ir/apply.py` fail to execute under the standard project test runner `python3 -m unittest discover` due to pytest function conventions. Furthermore, critical operation replay scenarios (empty project, `SetAudioGainOp`, `superseded` status, `EditGraphStore` integration, sequence reordering) lack unit tests.

### Recommended Test Architecture for Worker 3

Worker 3 should structure `open_edit/tests/test_ir/test_apply.py` using standard `unittest.TestCase` classes:

1. **`TestApplyAddRemoveClip(unittest.TestCase)`**:
   - `test_add_clip_creates_track`: Verifies track creation and clip insertion.
   - `test_add_clip_uses_position_sec`: Verifies timeline position assignment.
   - `test_add_audio_clip_is_first_class`: Verifies audio track and clip creation (`track_kind="audio"`).
   - `test_remove_clip_removes_from_track`: Verifies clip deletion from track.
   - `test_remove_clip_unknown_id_noop`: Verifies non-existent clip ID leaves timeline unchanged.
   - `test_add_clip_overlapping_positions`: Verifies multi-clip positioning on single track.

2. **`TestApplyMoveTrimClip(unittest.TestCase)`**:
   - `test_move_clip_relocates`: Verifies moving clip between tracks and positions.
   - `test_move_clip_unknown_id_noop`: Verifies moving non-existent clip is safe.
   - `test_trim_clip_updates_in_and_out`: Verifies updating `in_point_sec` and `out_point_sec`.
   - `test_trim_clip_unknown_id_noop`: Verifies trimming non-existent clip is safe.

3. **`TestApplyTransitions(unittest.TestCase)`**:
   - `test_add_transition_centers_on_cut`: Bug A regression test (verifies centering on cut `cut = clip_a.out_point_sec`, back-solving `clip_a.out` and `clip_b.in`).
   - `test_add_transition_duration_too_large`: Asserts `self.assertRaises(ValueError)` when duration exceeds clip bounds.
   - `test_add_transition_appends_effect_to_clip_a`: Verifies transition effect attached to `clip_a`.
   - `test_add_transition_already_trimmed_clip`: Bug-hunt finding verification for pre-trimmed clips.
   - `test_add_transition_missing_clip_noop`: Verifies transition with missing `clip_a_id` or `clip_b_id` returns unmodified timeline.

4. **`TestApplyEffectsAndAudio(unittest.TestCase)`**:
   - `test_add_effect_appends_to_clip`: Verifies effect added to clip.
   - `test_add_effect_appends_to_track`: Verifies effect added to track.
   - `test_set_keyframe_updates_existing_effect`: Verifies keyframe insertion/update on effect.
   - `test_set_audio_gain_op`: **NEW** — Verifies `SetAudioGainOp` converts `gain_db` to linear gain (`10 ** (gain_db / 20)`) and appends `volume` effect to audio clip.
   - `test_normalize_audio_clip`: Verifies `NormalizeAudioOp` tags clip volume effect.
   - `test_normalize_audio_track`: Verifies `NormalizeAudioOp` tags track volume effect.
   - `test_normalize_audio_unknown_target_noop`: Verifies unknown target handling.

5. **`TestDeriveTimelineReplay(unittest.TestCase)`**:
   - `test_derive_timeline_empty_project`: **NEW** — Verifies `Project(name="empty")` derives empty timeline (`tracks=[]`, `duration_sec=0.0`).
   - `test_derive_timeline_replays_all_applied_ops`: Verifies replay of sequential ops and duration calculation.
   - `test_derive_timeline_skips_reverted_ops`: Verifies `status="reverted"` ops are excluded from derived timeline.
   - `test_derive_timeline_skips_superseded_ops`: **NEW** — Verifies `status="superseded"` ops are excluded from derived timeline.
   - `test_derive_timeline_computes_duration_from_max_clip_end`: Verifies `duration_sec` calculation across multiple tracks.

6. **`TestEditGraphReplayIntegration(unittest.TestCase)`**:
   - `test_replay_from_edit_graph_store`: **NEW** — Appends ops to `EditGraphStore`, loads via `load_all()`, passes to `derive_timeline()`, asserts timeline match.
   - `test_replay_after_undo_status_change`: **NEW** — Appends ops, calls `store.update_status(op_id, "reverted")`, re-derives timeline, verifies reverted op effect is undone.
   - `test_replay_after_sequence_reorder`: **NEW** — Appends ops, calls `store.reorder(op1_id, op2_id)`, re-derives timeline, verifies timeline state reflects new order.

---

## 5. Verification Method

To verify the test suite after Worker 3 implementation:

1. **Run Standard Unittest Discovery**:
   ```bash
   python3 -m unittest discover -s open_edit/tests
   ```
   *Expected Result*: All tests in `open_edit/tests/test_ir/test_apply.py` are discovered and pass (total test count should increase by 25+ tests).

2. **Run `test_apply.py` Directly via Unittest**:
   ```bash
   PYTHONPATH=open_edit python3 -m unittest open_edit/tests/test_ir/test_apply.py
   ```
   *Expected Result*: Runs all test cases in `test_apply.py` with 0 failures and 0 errors.

3. **Invalidation Conditions**:
   - Any test using `@pytest.fixture` or `pytest.raises` without `unittest.TestCase` harness.
   - Any test failing under `python3 -m unittest discover -s open_edit/tests`.
   - Missing assertions for `SetAudioGainOp`, `status="superseded"`, empty project, or `EditGraphStore` integration.
