# Challenger 1 Report: Milestone 3 — Operation Replay & Derived State

**Verdict**: **REJECTED**

---

## 1. Observation

- **Unit Test Command**: `PYTHONPATH=open_edit python3 -m unittest discover -s open_edit/tests`
  - **Result**: 123 tests passed in 0.550s (100% clean pass rate for existing test suite).

- **Stress Test Harness Command**: `python3 /home/ah64/apps/mlt-pipeline/.agents/challenger_m3_1/stress_test.py`
  - **Result**: Failed on 2 test dimensions out of 6.

- **Edge Case Test Harness Command**: `python3 /home/ah64/apps/mlt-pipeline/.agents/challenger_m3_1/test_edge_cases.py`
  - **Result**: Uncovered 4 boundary/state anomalies.

### Key Verbatim Observations

1. **Infinite Loop in `derive_timeline` on Parent Cycle** (`open_edit/ir/apply.py:599-609`):
   ```python
   599:         curr_parent = op.parent_id
   600:         parent_reverted = False
   601:         while curr_parent:
   602:             parent_op = op_by_id.get(curr_parent)
   603:             if parent_op is not None and parent_op.status != "applied":
   604:                 parent_reverted = True
   605:                 break
   606:             curr_parent = parent_op.parent_id if parent_op else None
   ```
   When `op1.parent_id == "op2"` and `op2.parent_id == "op1"`, `curr_parent` toggles endlessly between `"op1"` and `"op2"`. The `while` loop has no cycle detection (e.g. `visited` set or recursion cap), leading to an unrecoverable infinite loop / process hang.

2. **Uncaught Exception in `derive_timeline` on Invalid `AddTransitionOp`** (`open_edit/ir/apply.py:452,458,467,473`):
   ```python
   467:     if new_a_out < clip_a.in_point_sec:
   468:         raise ValueError(
   469:             f"AddTransitionOp: clip_a asset range would invert "
   470:             f"(in={clip_a.in_point_sec}, new_out={new_a_out}). "
   471:             f"fix: shorten duration_sec or trim clip_a less."
   472:         )
   ```
   During random sequence replay (fuzzing 2000 ops), when an `AddTransitionOp` is evaluated after clip boundaries have shifted, `_apply_add_transition` raises `ValueError`. `derive_timeline` does not catch this exception, causing full replay failure (`ValueError`) for the entire project.

3. **Inverted Trim & Negative Clip Duration** (`open_edit/ir/apply.py:113-115`):
   Executing `TrimClipOp(new_in_point_sec=15.0, new_out_point_sec=5.0)` sets `clip.in_point_sec = 15.0` and `clip.out_point_sec = 5.0`.
   `clip.out_point_sec - clip.in_point_sec` yields `-10.0` seconds. In `derive_timeline:617`, `end = position_sec + (out_point_sec - in_point_sec)` subtracts 10s from position, corrupting `timeline.duration_sec`.

4. **Negative Asset Points via Slip Clip** (`open_edit/ir/apply.py:271-274`):
   Executing `SlipClipOp(delta_sec=-10.0)` on a clip with `in_point_sec=1.0` sets `in_point_sec = -9.0` and `out_point_sec = -5.0`. No validation bounds asset points to `>= 0.0`.

5. **Track Kind Pollution on `MoveClipOp`** (`open_edit/ir/apply.py:102`):
   ```python
   102: new_track = _get_or_create_track(timeline, op.new_track_id, clip.track_kind)
   ```
   When moving a video clip (`clip.track_kind="video"`) to a new track `a1` (intended for audio), `_get_or_create_track` creates track `a1` with `kind="video"`.

---

## 2. Logic Chain

1. **Observation 1** demonstrates that any cycle in `parent_id` pointers in `project.edit_graph` causes `derive_timeline` to loop infinitely in `while curr_parent:`. Because operations can be constructed programmatically or ingested from external/free-form sources, an invalid parent graph locks up the process. This is a Critical Denial of Service flaw.
2. **Observation 2** shows that `derive_timeline` expects every operation in `edit_graph` to succeed without raising exceptions. However, `_apply_add_transition` raises `ValueError` when transition constraints are violated. Because `derive_timeline` does not catch or handle `ValueError` gracefully, an invalid transition operation breaks timeline derivation for all operations in the graph.
3. **Observations 3 & 4** show that operations like `TrimClipOp` and `SlipClipOp` lack basic domain validation (e.g. `in_point_sec <= out_point_sec` and `in_point_sec >= 0`), allowing state corruption (negative clip durations and negative asset offsets) to pollute the derived `Timeline`.
4. **Observation 5** shows that track creation on `MoveClipOp` relies on `clip.track_kind`, causing track type mismatches when moving clips between audio and video tracks.
5. Therefore, while the existing unit test suite passes 100%, empirical stress testing and boundary analysis reveal critical flaws in operation replay and derived state logic. The verdict is **REJECTED**.

---

## 3. Caveats

- **Existing Unit Tests**: The standard unit test suite (`PYTHONPATH=open_edit python3 -m unittest discover -s open_edit/tests`) passes cleanly (123/123 tests pass). The failure modes identified require stress testing with cyclic graph structures, invalid transition parameters during replay, and boundary inputs.
- **Scope**: Code changes were not made to `apply.py`, strictly adhering to the review-only role constraint.

---

## 4. Conclusion

- **Verdict**: **REJECTED**
- **Actionable Remediation Required**:
  1. Add cycle detection (e.g., `visited = set()`) in `derive_timeline` (`open_edit/ir/apply.py:601`) to break loop and skip/flag ops with parent cycles.
  2. Handle `ValueError` inside `derive_timeline` (or catch invalid transitions in `apply_operation` and mark op as un-appliable / return timeline unchanged) so replay does not crash the process.
  3. Validate clip bounds in `TrimClipOp` (`new_in_point_sec <= new_out_point_sec`) and `SlipClipOp` (`in_point_sec >= 0.0`).
  4. Fix track creation logic in `MoveClipOp` to respect destination track kind.

---

## 5. Verification Method

To independently verify these empirical findings:

1. **Run Standard Unit Test Suite**:
   ```bash
   PYTHONPATH=open_edit python3 -m unittest discover -s open_edit/tests
   ```
   *Expected*: Passes 100% cleanly (123 tests).

2. **Run Empirical Stress Test Suite**:
   ```bash
   python3 /home/ah64/apps/mlt-pipeline/.agents/challenger_m3_1/stress_test.py
   ```
   *Expected*: Reports `FAIL` for Parent Cycle Vulnerability and Fuzzing Random Operations (`ValueError` on invalid transition replay).

3. **Run Boundary Edge Case Test Suite**:
   ```bash
   python3 /home/ah64/apps/mlt-pipeline/.agents/challenger_m3_1/test_edge_cases.py
   ```
   *Expected*: Shows inverted trim producing negative duration (-10.0s), slip into negative asset time (-9.0s), and track kind pollution.
