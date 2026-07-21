# Storage Test Suite & EditGraphStore Coverage Analysis

## 1. Storage Test Suite Structure

The storage test suite for Open Edit is located in `open_edit/tests/test_storage/` with an additional test file `open_edit/tests/test_edit_graph_project_id.py`.

### Detailed Inventory of Storage Test Files

| Test File Path | Purpose / Module Under Test | Test Count | Style / Framework |
|---|---|---|---|
| `open_edit/tests/test_storage/test_edit_graph.py` | Core `EditGraphStore` (schema, WAL mode, append, load_all, update_status, reorder) | 11 | pytest function tests (`tmp_path`) |
| `open_edit/tests/test_edit_graph_project_id.py` | `EditGraphStore.project_id` persistence + `Project.workdir` optionality | 3 | pytest function tests (`tmp_path`) |
| `open_edit/tests/test_storage/test_job_lock.py` | `JobLock` concurrency control wrapping `EditGraphStore` | 6 | pytest function tests (`tmp_path`) |
| `open_edit/tests/test_storage/test_notes.py` | `NotesStore` review notes persistence and status state machine | 15 | pytest function tests (`tmp_path`) |
| `open_edit/tests/test_storage/test_assets.py` | `AssetStore` content-addressed storage (CAS) & metadata probing | 11 | pytest function tests (`tmp_path`) |
| `open_edit/tests/test_storage/test_assets_alignment.py` | `AssetStore` word alignment & transcript sidecars | 6 | pytest function tests (`tmp_path`) |
| `open_edit/tests/test_storage/test_render_snapshots.py` | `RenderSnapshotStore` versioning and eviction | 7 | pytest function tests (`tmp_path`) |
| `open_edit/tests/test_storage/test_transcription.py` | `transcribe()` helper and Whisper fallback | 3 | pytest function tests (`tmp_path`) |

**Total storage tests in suite**: 62 tests across 8 files.

---

## 2. Unittest Compatibility & Test Execution Analysis

### Current Execution Results

1. **Pytest Execution**:
   - Command: `pytest tests/test_storage/ tests/test_edit_graph_project_id.py`
   - Result: **62 passed in 0.70s** (100% pass rate under pytest).

2. **Unittest Discover Execution**:
   - Command: `python3 -m unittest discover -s tests` (run from `/home/ah64/apps/mlt-pipeline/open_edit`)
   - Result: **Ran 26 tests in 0.003s (OK)**.
   - **Key Finding**: None of the 62 storage tests ran! The 26 tests executed by `unittest discover` are strictly from `test_ir/test_types.py`.

3. **Explicit Unittest Execution on Storage Test File**:
   - Command: `python3 -m unittest tests/test_storage/test_edit_graph.py`
   - Result: `Ran 0 tests in 0.000s — NO TESTS RAN` (Exit code 5).

### Root Cause Analysis

- Standard Python `unittest.defaultTestLoader` discovers tests by looking for classes that subclass `unittest.TestCase`.
- Every test in `open_edit/tests/test_storage/` and `test_edit_graph_project_id.py` is written as a top-level pytest function (`def test_...(tmp_path)`).
- These functions rely on pytest-native fixtures (`tmp_path`, `monkeypatch`, `caplog`, `pytest.raises`).
- Because they do not inherit from `unittest.TestCase`, the standard Python `unittest` framework completely ignores them.

### Acceptance Criteria Conflict

- **Acceptance Criteria (from `ORIGINAL_REQUEST.md`)**:
  - *"All unit tests must pass cleanly using the Python unittest framework."*
  - *"The command `python3 -m unittest discover -s tests` must execute successfully with zero failures."*
- **Current State**: While `unittest discover` returns exit code 0, it does so only because it skips 62 storage unit tests. If `unittest` compatibility is required for Milestone 2 acceptance, storage tests must be refactored to inherit from `unittest.TestCase`.

---

## 3. EditGraphStore Test Coverage & Gaps

### Implementation Overview (`open_edit/storage/edit_graph.py`)

`EditGraphStore` manages SQLite persistence for project edit graphs. The DB layout is governed by `open_edit/storage/schema.sql`:
- `project_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)`: Stores metadata like `project_id`.
- `edits`: Append-only log containing `edit_id`, `parent_id`, `kind`, `author`, `timestamp`, `status`, `sequence_num`, `payload`.
- `jobs`: Sandbox and render job locks.

### Coverage Breakdown

| Method / Feature | Existing Test | Status | Gaps Identified |
|---|---|---|---|
| DB File Creation | `test_init_creates_db_file` | Covered | None |
| Table Initialization | `test_init_creates_edits_table`, `test_init_creates_jobs_table` | Covered | `project_meta` table creation not explicitly asserted in `test_edit_graph.py` |
| SQLite PRAGMAs | `test_init_enables_wal_mode`, `test_init_enables_foreign_keys` | Covered | Foreign key enforcement failure on invalid `parent_id` not tested |
| `project_id` Persistence | `test_edit_graph_store_persists_project_id` | Covered | Multi-project DB isolation (ensuring separate DB files generate distinct project IDs) not tested |
| `append()` Auto Sequence | `test_append_assigns_increasing_sequence_num` | Covered | Explicit `sequence_num` parameter (`append(op, sequence_num=X)`) untested |
| `append()` Op Schemas | `test_append_assigns_increasing_sequence_num` (uses `AddClipOp`) | Partial | Only 1 of 10 operation types (`AddClipOp`) tested in `test_edit_graph.py`. Remaining 9 op types (`RemoveClipOp`, `MoveClipOp`, `TrimClipOp`, `AddTransitionOp`, `AddEffectOp`, `SetKeyframeOp`, `GroupEditsOp`, `RawMltXmlOp`, `FreeFormCodeOp`) untested for DB persistence |
| `load_all()` Deserialization | `test_load_all_returns_ops_in_sequence_order` | Covered | Empty database `load_all()` returning `[]` not explicitly tested |
| `update_status()` | `test_update_status_marks_reverted` | Partial | Tested for `"reverted"`. Untested for `"superseded"`. Untested for CHECK constraint violations on invalid status strings (e.g. `"invalid_status"`) |
| Non-existent `edit_id` | N/A | Missing | Updating status on non-existent `edit_id` (noop behaviour) untested |
| `reorder()` Operations | `test_reorder_swaps_adjacent_ops`, `test_reorder_rejects_non_adjacent_ops`, `test_reorder_rejects_missing_ops` | Covered | Edge cases with empty DB or 1-op DB untested |

---

## 4. Recommendations for Refactoring & Expansion

### 1. Refactor Storage Tests to Subclass `unittest.TestCase`

To ensure compatibility with `python3 -m unittest discover -s tests`:
- Convert test functions to methods within `unittest.TestCase` subclasses (e.g. `class TestEditGraphStore(unittest.TestCase)`).
- Replace pytest's `tmp_path` fixture with Python's standard `tempfile.TemporaryDirectory` in `setUp()` / `tearDown()`.
- Replace `pytest.raises` with `self.assertRaises(ValueError)` or `with self.assertRaises(...):`.

### 2. Add Missing Unit Tests for `EditGraphStore`

Add explicit test cases for:
1. **All 10 Operation Schema Round-Trips**: Assert that inserting and loading `RemoveClipOp`, `MoveClipOp`, `TrimClipOp`, `AddTransitionOp`, `AddEffectOp`, `SetKeyframeOp`, `GroupEditsOp`, `RawMltXmlOp`, and `FreeFormCodeOp` preserves all fields correctly.
2. **Explicit Sequence Numbering**: Test calling `append(op, sequence_num=10)` and verify sequence order in `load_all()`.
3. **Foreign Key Constraint Validation**: Assert that inserting an operation with `parent_id` referencing a non-existent `edit_id` raises `sqlite3.IntegrityError` due to `PRAGMA foreign_keys=ON`.
4. **Status Check Constraint Validation**: Assert that `update_status(edit_id, "invalid")` raises `sqlite3.IntegrityError` due to `CHECK (status IN ('applied', 'reverted', 'superseded'))`.
5. **Project Isolation**: Instantiate two `EditGraphStore` instances targeting separate temp DB paths, asserting distinct `project_id` values and independent operation logs.
6. **Empty Store Querying**: Assert `store.load_all()` on a freshly initialized store returns `[]`.
