## 2026-07-23T10:47:36Z
You are a Worker assigned to fix the 2 pre-existing test regressions in `/home/ah64/apps/mlt-pipeline/open_edit`.

Context:
Full test suite review revealed 966/968 passed, with 2 pre-existing test failures caused by commit `eda0dfc`:
1. `FAILED tests/test_history_compaction.py::test_remove_tool_only_assistant`:
   - Assertion `assert len(compacted) == 1` fails (actual: 2) because `compact_history` in `open_edit/serve/context_budget.py` keeps `tool_result` user messages unmerged to preserve Anthropic API pairing.
   - Task: Update `test_remove_tool_only_assistant` in `tests/test_history_compaction.py` (or `compact_history`) to align test assertions with the tool_result isolation contract.
2. `FAILED tests/test_render/test_golden_fixtures.py::test_golden_expected_timeline_matches_derive`:
   - Expected timeline golden fixture `tests/testdata/golden_11clip/expected_timeline.json` has `out_point_sec: 1.5` for trimmed clips, but the fixed transition math in `open_edit/ir/apply.py` calculates `1.75`.
   - Task: Update `tests/testdata/golden_11clip/expected_timeline.json` (or regenerate golden fixture) to update `out_point_sec` from `1.5` to `1.75` for the affected trimmed clips.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Work in `/home/ah64/apps/mlt-pipeline/open_edit`. Your metadata directory is `/home/ah64/apps/mlt-pipeline/open_edit/.agents/worker_m4_fix`.
Run `python3 -m pytest tests/` to verify all 968 tests pass cleanly (0 failures, 0 errors).
Document all fixes and test results in `/home/ah64/apps/mlt-pipeline/open_edit/.agents/worker_m4_fix/handoff.md` and send a message back to parent.
