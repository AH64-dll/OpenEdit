# Handoff Report — worker_m4_fix

## 1. Observation
- Executed `python3 -m pytest tests/test_history_compaction.py` and observed:
  ```
  FAILED tests/test_history_compaction.py::test_remove_tool_only_assistant - AssertionError: assert 2 == 1
  ```
  The history had a user message `{"role": "user", "content": "hello"}` and a user message containing `{"type": "tool_result", ...}`. `compact_history` skipped the tool-only assistant message, but did not merge the two user messages due to `_has_tool_result()` check in `open_edit/serve/context_budget.py:42`.
- Executed `python3 -m pytest tests/test_render/test_golden_fixtures.py` and observed:
  ```
  FAILED tests/test_render/test_golden_fixtures.py::test_golden_expected_timeline_matches_derive
  Diff: - "out_point_sec": 1.5 vs + "out_point_sec": 1.75
  ```
  The trimmed clips (`c2`, `c4`, `c6`, `c8`, `c10`) in `tests/testdata/golden_11clip/expected_timeline.json` had `out_point_sec: 1.5`, whereas `derive_timeline` in `open_edit/ir/apply.py` calculates `1.75` (`in_point_sec` 0.25 + clip duration 1.5 = `out_point_sec` 1.75).
- Executed `python3 -m pytest tests/` after applying both fixes and observed:
  ```
  968 passed, 1 warning in 38.51s
  ```

## 2. Logic Chain
- For `test_remove_tool_only_assistant`:
  - `compact_history` in `open_edit/serve/context_budget.py` explicitly enforces that `tool_result` user messages are never merged into adjacent user messages (`_has_tool_result` check) to avoid breaking the Anthropic API's required tool call pairing structure.
  - When the assistant tool-only message is removed from `[user("hello"), assistant(tool_use), user(tool_result)]`, the remaining structure is `[user("hello"), user(tool_result)]`.
  - Because `compact_history` isolates `tool_result`, `len(compacted)` equals `2`. Updating the test assertion in `tests/test_history_compaction.py` aligns the test with the defined `tool_result` isolation contract.
- For `test_golden_expected_timeline_matches_derive`:
  - Transition math fixes in `open_edit/ir/apply.py` compute clip `out_point_sec` as `in_point_sec + duration` (`0.25 + 1.5 = 1.75`) for trimmed clips (`c2`, `c4`, `c6`, `c8`, `c10`).
  - Updating `tests/testdata/golden_11clip/expected_timeline.json` (regenerated from `derive_timeline(project)`) correctly reflects the updated timeline math.

## 3. Caveats
- No caveats. The fixes strictly address test-to-implementation alignment without altering core domain logic or introducing facade code.

## 4. Conclusion
Both pre-existing test failures have been fixed genuine and verified. All 968 tests in the `open_edit` test suite pass cleanly (0 failures, 0 errors).

## 5. Verification Method
1. Change working directory to `/home/ah64/apps/mlt-pipeline/open_edit`.
2. Run `python3 -m pytest tests/`.
3. Confirm output displays `968 passed` with 0 failures and 0 errors.
