## 2026-07-21T08:12:50Z
You are Worker 3 for Milestone 3: Operation Replay & Derived State.
Your working directory is /home/ah64/apps/mlt-pipeline/.agents/worker_3. Please create this directory if it doesn't exist.

Objective:
Implement operation replay and state derivation in open_edit/ir/apply.py and refactor/expand unit tests in open_edit/tests/test_ir/test_apply.py so they pass 100% cleanly under python3 -m unittest discover.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Context & Explorer Synthesis:
- Explorer 1, 2, and 3 analyzed open_edit/ir/apply.py, open_edit/ir/types.py, open_edit/storage/edit_graph.py, and the test suite.
- 13 operation types from OperationUnion (RemoveTransitionOp, SetTransitionPropertyOp, RemoveEffectOp, SetEffectParamOp, RemoveKeyframeOp, SlipClipOp, RippleDeleteClipOp, ChangeClipSpeedOp, SplitClipOp, ReplaceClipSourceOp, SetClipSpeedRampOp, UngroupEditsOp, RawMltXmlOp) were unhandled in apply_operation and fell through.
- test_apply.py was written with free-standing pytest functions, causing python3 -m unittest discover to skip it entirely.
- SetAudioGainOp was un-tested; status="superseded" replay was un-tested; EditGraphStore -> derive_timeline integration was un-tested.

Detailed Tasks for Worker 3:
1. Implement / complete operation handlers in open_edit/ir/apply.py:
   - Add explicit handlers for all 13 missing operations:
     * RemoveTransitionOp: Remove transition effect with matching transition_id / clip_b_id.
     * SetTransitionPropertyOp: Update param in transition effect.
     * RemoveEffectOp: Remove effect at effect_index from target clip.
     * SetEffectParamOp: Update eff.params[param_name] = value for effect on clip.
     * RemoveKeyframeOp: Delete keyframe at frame for param on effect_id.
     * SlipClipOp: Shift in_point_sec and out_point_sec by delta_sec while keeping position_sec unchanged.
     * RippleDeleteClipOp: Remove target clip and shift subsequent clips on track left by clip duration.
     * ChangeClipSpeedOp: Update clip playback rate / speed metadata.
     * SplitClipOp: Replace clip with left half and right half at at_sec.
     * ReplaceClipSourceOp: Update clip.asset_hash = new_asset_hash.
     * SetClipSpeedRampOp: Set speed ramp metadata on clip.
     * UngroupEditsOp: Pass-through no-op return.
     * RawMltXmlOp: Pass-through return or metadata tag.
   - Verify existing operation handlers (AddClipOp, RemoveClipOp, MoveClipOp, TrimClipOp, AddTransitionOp, AddEffectOp, SetKeyframeOp, SetAudioGainOp, NormalizeAudioOp, GroupEditsOp, FreeFormCodeOp).
   - Ensure derive_timeline returns empty Timeline(tracks=[], duration_sec=0.0) for empty project, and skips operations with status != "applied" (or parent op reverted).

2. Refactor open_edit/tests/test_ir/test_apply.py:
   - Refactor ALL tests into standard unittest.TestCase subclasses (e.g. TestApplyAddRemoveClip, TestApplyMoveTrimClip, TestApplyTransitions, TestApplyEffectsAndAudio, TestDeriveTimelineReplay, TestEditGraphReplayIntegration).
   - Replace pytest assertions with TestCase assertions (self.assertEqual, self.assertRaises, self.assertAlmostEqual, etc.).
   - Add test cases for SetAudioGainOp, status="superseded", empty project replay, and end-to-end EditGraphStore.load_all() -> derive_timeline() integration.

3. Build & Test Verification:
   - Run `PYTHONPATH=open_edit python3 -m unittest discover -s open_edit/tests -v`
   - Run `PYTHONPATH=open_edit python3 -m unittest discover -s tests -v` (if symlinked or present)
   - Ensure ALL tests are discovered and pass with 0 failures and 0 errors.

4. Handoff Report:
   - Produce a detailed handoff report at /home/ah64/apps/mlt-pipeline/.agents/worker_3/handoff.md detailing changes made, build/test execution output, test counts, and layout compliance.
   - Use send_message to report completion to the orchestrator.
