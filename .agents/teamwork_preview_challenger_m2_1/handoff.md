# Handoff Report: Milestone 2 SQLite Edit Graph Store Stress Testing

## Verdict: CONFIRMED

The empirical stress testing of `EditGraphStore` (`open_edit/open_edit/storage/edit_graph.py`) has been completed. The stress tests **CONFIRMED** critical vulnerabilities and design gaps, specifically:
1. **Concurrency Race Condition**: Concurrent appends produce duplicate `sequence_num` values in the database.
2. **Missing Status Filtering**: `load_all()` lacks status filtering capabilities.
3. **Silent Update Failure**: `update_status()` on non-existent `edit_id` fails silently without error.

---

## 1. Observation

### 1.1 Bulk Insertion & Sequence Numbering (`stress_bulk_insertion.py`)
- **Command executed**: `python3 .agents/teamwork_preview_challenger_m2_1/stress_bulk_insertion.py`
- **Result**: Bulk insertion of 1,000 operations completed in `0.2706s` (`3,695.61 ops/sec`).
- **Sequence Numbering**: Monotonic single-threaded appends produced sequence numbers `0..999` without gaps.
- **Explicit Sequence Numbers**: `append(op, sequence_num=100)` succeeded, and subsequent default `append()` derived `MAX(sequence_num) + 1 = 101`.
- **Duplicate Sequence Numbering**: Inserting two operations with `sequence_num=10` succeeded without raising an error because `schema.sql` (line 18) defines `sequence_num INTEGER NOT NULL` without a `UNIQUE` constraint.

### 1.2 Status Updates & Filtering (`stress_status_transitions.py`)
- **Command executed**: `python3 .agents/teamwork_preview_challenger_m2_1/stress_status_transitions.py`
- **Transitions**: Transitioning `status` ("applied" -> "reverted" -> "superseded" -> "applied") via `update_status()` succeeded and persisted.
- **CHECK Constraint**: Attempting `update_status(op.edit_id, "invalid_status")` failed with verbatim exception:
  `sqlite3.IntegrityError: CHECK constraint failed: status IN ('applied', 'reverted', 'superseded')` (defined in `schema.sql`:17).
- **Silent Update on Non-Existent ID**: Executing `update_status("non-existent-id", "reverted")` returned cleanly without raising `ValueError` or `KeyError`. `update_status` (`edit_graph.py`:107-110) executes `UPDATE edits SET status = ? WHERE edit_id = ?` without inspecting `cur.rowcount`.
- **Status Filtering in `load_all()`**: Attempting `load_all(status="applied")` raised `TypeError: EditGraphStore.load_all() got an unexpected keyword argument 'status'`. `load_all()` (`edit_graph.py`:91-102) has signature `def load_all(self) -> list[OperationUnion]:` and executes `SELECT payload, status FROM edits ORDER BY sequence_num`, loading all status types without DB-level filtering.

### 1.3 Concurrent Access (`stress_concurrency.py`)
- **Command executed**: `python3 .agents/teamwork_preview_challenger_m2_1/stress_concurrency.py`
- **Multi-Threaded Appends**: 10 concurrent threads inserting 20 operations each (200 total ops) produced **47 duplicate sequence numbers** (e.g. sequence number `0` assigned to 3 operations, sequence number `1` assigned to 7 operations).
- **Multi-Process Appends**: 5 concurrent processes inserting 20 operations each (100 total ops) produced **13 duplicate sequence numbers** across processes (e.g. sequence number `18` assigned to 2 operations).
- **WAL Mode Read/Write**: Concurrent readers calling `load_all()` while a writer appended 100 operations executed 116 read queries with 0 errors, reading incremental state sizes from 50 to 150 operations without blocking.

### 1.4 Reorder Edge Cases (`stress_reorder_edge_cases.py`)
- **Command executed**: `python3 .agents/teamwork_preview_challenger_m2_1/stress_reorder_edge_cases.py`
- **Valid Swap**: Swapping adjacent ops with sequence numbers `0` and `1` succeeded and was reflected in `load_all()`.
- **Invalid Edit IDs**: Calling `reorder("valid_id", "invalid_id")` or `reorder("invalid1", "invalid2")` raised `ValueError("Both edits must exist; got N rows")`.
- **Same Edit ID**: Calling `reorder(id_a, id_a)` returned 1 row from `SELECT ... WHERE edit_id IN (?, ?)`, raising `ValueError("Both edits must exist; got 1 rows")`.
- **Non-Adjacent Sequence Numbers**: `reorder(id_a, id_b)` with sequence gap = 2 raised `ValueError: Edits must be adjacent to reorder; got sequence_num gap 2`.
- **Gapped Sequence Numbers**: Swapping two ops with sequence numbers `0` and `2` (where sequence number `1` is missing) raised `ValueError` because `edit_graph.py`:128 checks `abs(seq1 - seq2) != 1`.
- **Duplicate Sequence Numbers**: Swapping two ops with identical sequence numbers (e.g., `5` and `5`) raised `ValueError` because `abs(5 - 5) == 0 != 1`.

---

## 2. Logic Chain

1. **Observation 1.3** shows that concurrent `append()` calls across threads or processes produce duplicate `sequence_num` entries in the `edits` table.
2. In `edit_graph.py`:75-78, `append()` calculates sequence number via `SELECT COALESCE(MAX(sequence_num), -1) + 1 FROM edits`. In standard `sqlite3` connection transactions, this `SELECT` query runs under a deferred read transaction. When multiple threads/processes execute this simultaneously, they read identical `MAX(sequence_num)` values and insert rows with identical sequence numbers.
3. In `schema.sql`:18, `sequence_num INTEGER NOT NULL` has no `UNIQUE` constraint or autoincrement counter, permitting duplicate sequence numbers to persist.
4. When `load_all()` executes `SELECT payload, status FROM edits ORDER BY sequence_num`, duplicate sequence numbers result in non-deterministic ordering of operations.
5. **Observation 1.2** shows `update_status()` executes `UPDATE edits SET status = ? WHERE edit_id = ?` without validating if any row was affected (`cur.rowcount == 0`), causing non-existent IDs to fail silently.
6. **Observation 1.2** also shows `load_all()` has no filter parameters. Consumers (e.g., `open_edit/render/orchestrator.py`:77) must perform manual Python filtering (`[op for op in ops if op.status == 'applied']`).
7. **Observation 1.4** demonstrates that `reorder()` strictly relies on `abs(seq1 - seq2) == 1`. If sequence numbers are non-contiguous due to deletions or custom sequence assignment, `reorder()` fails even if the operations are logically adjacent in insertion order.

---

## 3. Caveats

- **SQLite WAL Concurrency**: SQLite WAL mode prevents read-lock blocking during writes, but SQLite write transactions remain single-writer. High process contention may hit default connection timeouts if writes are not batched or protected by `BEGIN IMMEDIATE`.
- **In-Memory SQLite**: Stress testing was performed on real temp files (`Path(tmpdir) / "*.db"`). File system sync behavior may vary slightly on network-attached storage or NFS.
- **No Modifications to Core Code**: Pursuant to challenger identity guidelines, no changes were made to `open_edit/open_edit/storage/edit_graph.py` or `schema.sql`.

---

## 4. Conclusion

**Verdict: CONFIRMED**

The stress testing empirically confirms that `EditGraphStore` exhibits critical concurrency failure modes and API deficiencies:
- **Critical Failure Mode**: Race condition in `append()` produces duplicate sequence numbers during concurrent writes due to non-atomic MAX query and missing `UNIQUE` constraint in `schema.sql`.
- **Design Deficiency**: `update_status()` does not raise an exception when updating non-existent edit IDs.
- **Design Deficiency**: `load_all()` lacks status filtering support at the database layer.
- **Edge Case Rigidity**: `reorder()` fails on logically adjacent operations if sequence numbers contain numeric gaps.

### Recommended Mitigations for Implementation Team:
1. **Fix Concurrency**: Execute `append()` within `BEGIN IMMEDIATE` transaction blocks or use SQLite autoincrement / database-level sequence lock to guarantee atomic sequence number assignment.
2. **Schema Constraint**: Add `UNIQUE(sequence_num)` or composite constraint in `schema.sql` if strict uniqueness is required.
3. **Fix Silent Update**: Check `cur.rowcount` in `update_status()` and raise `ValueError(f"Edit ID {edit_id} not found")` if 0 rows were updated.
4. **Enhance `load_all()`**: Add optional `status: str | None = None` parameter to `load_all(status="applied")` to filter directly in SQL (`WHERE status = ?`).

---

## 5. Verification Method

To independently execute and verify all stress test findings:

```bash
# Navigate to project root
cd /home/ah64/apps/mlt-pipeline

# Run complete stress test suite runner
python3 .agents/teamwork_preview_challenger_m2_1/run_all_stress_tests.py

# Run individual stress test modules
python3 .agents/teamwork_preview_challenger_m2_1/stress_bulk_insertion.py
python3 .agents/teamwork_preview_challenger_m2_1/stress_status_transitions.py
python3 .agents/teamwork_preview_challenger_m2_1/stress_concurrency.py
python3 .agents/teamwork_preview_challenger_m2_1/stress_reorder_edge_cases.py
```

**Files to Inspect**:
- Stress test runner and modules: `.agents/teamwork_preview_challenger_m2_1/`
- Target under test: `open_edit/open_edit/storage/edit_graph.py`
- DB Schema: `open_edit/open_edit/storage/schema.sql`

**Invalidation Conditions**:
The findings would be invalidated if `append()` is made atomic and `stress_concurrency.py` yields 0 duplicate sequence numbers across process and thread runs.
