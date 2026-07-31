# Task 6.5 Report — Order-sensitive edit-graph hash + snapshot invalidation (H1)

**Status:** DONE
**Commit:** `(see git log — fix(ir): order-sensitive graph hash and snapshot invalidation on reorder)`
**Suite:** 1100 passed / 6 skipped (was 1095/6; +5 new regression tests)

## The bug (before-trace)

`compute_edit_graph_hash` was order-insensitive *in practice*:

1. `EditGraphStore.load_all()` ran `SELECT payload, status, parent_id FROM edits ORDER BY sequence_num` — it never selected `sequence_num`, and the pydantic `Operation` model has no such field.
2. The hash's sort key `_field(op, "sequence_num", 0)` therefore always resolved to `0`; the effective key was `(0, edit_id)` — a stable but *sequence-ignoring* order.
3. `data.pop("sequence_num", None)` additionally stripped the sequence from the digested payload (it was never there to begin with).
4. Consequence: `reorder()` / `reorder_all()` / `move_arbitrary()` changed the DB rows but NOT the digest → `derive_or_load_timeline` looked up a snapshot under the *same, now-stale* key and returned the pre-reorder timeline (H1). Job dedup (`kernel/render_service._graph_fingerprint`) and render-cache keys (`render/cache.py`) were likewise blind to order.

Two existing tests actively pinned the broken behavior:
- `tests/test_ir/test_phase1_hash_snapshot.py::test_order_independent` — asserted `hash([a,b]) == hash([b,a])`.
- `tests/test_render/test_cache.py::test_ir_hash_is_order_stable_and_content_sensitive` — asserted `hash(reversed(ops)) == hash(ops)`.

## The fix (after-trace)

1. **`storage/edit_graph.py::load_all`** now selects `sequence_num` and attaches it via `object.__setattr__(op, "sequence_num", row[3])`. Deliberately NOT a pydantic field: `model_dump()`/`model_dump_json()` (API responses in `serve/routers/ops.py`, stored payloads, golden materialize output) are unchanged — verified by full suite.
2. **`ir/hash.py::compute_edit_graph_hash`** is now order-sensitive:
   - ops without a `sequence_num` fall back to their list position (so `hash([a,b]) != hash([b,a])` even for bare in-memory op lists — the flipped unit tests rely on this);
   - sort key `(sequence_num, edit_id)` tie-break;
   - payload is `f"{seq}:{edit_id}:{op_json}"` (sequence is now part of the digest).
3. **`storage/ordering.py`** (Task 5.6 hook) — verified present and covering all four mutations: `_invalidate_project_snapshots` runs inside the same transaction in `reorder`, `reorder_all`, `move_arbitrary`, `delete_op`; each bumps `graph_revision`. No changes needed there.
4. Downstream consumers needed no changes: `kernel/render_service.py:197`, `serve/projects.py:357`, `render/cache.py` all hash `store.load_all()` output, which now carries real sequences. Dict payloads (e.g. `test_e2e_render.py`'s `canonical_json_hash(payload)`) use the index fallback and produce the same digest as the store path when the list is in sequence order. Previously cached renders will miss once — accepted (correctness > cache warmth).

## Regression tests (`tests/test_graph_hash_order.py`, new)

- `test_hash_changes_when_order_changes` — `reorder_all` flips the hash. **Fails on pre-fix code** (verified via `git stash` of the two source files: 2 failed, 3 passed).
- `test_adjacent_reorder_changes_hash` — `reorder` (adjacent swap) flips the hash. **Fails on pre-fix code.**
- `test_delete_op_changes_hash` — delete flips the hash (passed even pre-fix: op-set change).
- `test_derive_or_load_timeline_reflects_reorder_not_stale_snapshot` — after reorder, no snapshot exists under the new hash and `derive_or_load_timeline` equals a fresh `derive_timeline` (clip order differs from the pre-reorder timeline). Note: this one passed pre-fix too, because 5.6's row-delete hook masks the stale-snapshot symptom for the *reorder* path — the hash key itself remaining constant was the residual bug (e.g. save→reorder→save cycles under one key), which the hash fix removes at the root.
- `test_hash_equal_for_same_graph_loaded_twice` — digest stable across `load_all()` calls.

## Flips of old pins

- `test_ir/test_phase1_hash_snapshot.py::test_order_independent` → `test_order_sensitive` (asserts `!=`).
- `test_render/test_cache.py::test_ir_hash_is_order_stable_and_content_sensitive` → `test_ir_hash_is_order_sensitive_and_content_sensitive` (asserts `!=` on reversal; content sensitivity retained).

## Test runs

- `tests/test_graph_hash_order.py tests/test_ir/ tests/test_render/test_cache.py` → 155 passed
- Step-5 set (`test_storage/ test_ir/ test_history_compaction.py test_render_service.py test_render/ test_remotion_ir_materialize.py test_ir_api.py` + new file) → 279 passed
- `tests/test_layering.py` → 4 passed
- Full suite `tests/ -o addopts=""` → **1100 passed, 6 skipped, 0 failed**

## Concerns

- None blocking. Minor note: `open_edit/open_edit/` (untracked stale duplicate package tree) remains in the worktree and was NOT committed; it is shadowed by the tracked top-level package (`pythonpath=["."]`).
- Committed selectively (5 files), not `git add -A`, to avoid sweeping unrelated untracked files.
