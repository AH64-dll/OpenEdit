# Task 6.2 Report: Shared `storage/db.py` connection helper

**Status:** DONE
**Commit:** `e051450` ("refactor(storage): shared sqlite connection helper")

## What was done

1. **Created `open_edit/storage/db.py`** with `open_conn(db_path) -> contextmanager[sqlite3.Connection]`:
   - `sqlite3.Row` row factory
   - `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`
   - commit on normal exit, rollback on exception, close in `finally`
   - Copied the exact PRAGMA/commit/rollback semantics of the real `EditGraphStore._conn()` (which does **not** set `row_factory` itself; `row_factory=sqlite3.Row` was added per the brief's interface spec — verified no consumer compares fetched rows against tuples; all use integer indexing/unpacking, `sqlite3.Row` is safe on Python 3.14.5).

2. **Migrated the stores** (all `sqlite3.connect` now lives only in `db.py`):
   - `edit_graph.py`: `_conn` kept as a thin wrapper (`with open_conn(self.db_path) as conn: yield conn`) — **required** because `serve/projects.py`, `cli.py`, and `tests/` call `store._conn()`; internal call sites unchanged.
   - `commands.py`, `timeline_cache.py` (the 5.6 sub-stores): deleted private `_conn`, call sites now `open_conn(self.db_path)`.
   - `notes.py`, `render_snapshots.py`: all `sqlite3.connect(...) as con` → `open_conn`; removed now-redundant manual `con.row_factory = sqlite3.Row` lines.
   - `job_lock.py`: `JobLock.__init__(edit_graph)` signature unchanged (tests + `sandbox_bridge.py` pass a store); stores `self.db_path = edit_graph.db_path`; `_ensure_schema`/`_release_stale_locks` take `db_path` and use `open_conn`. No `edit_graph._conn()` reach-in remains. `EditGraphStore` import demoted to `TYPE_CHECKING`.
   - `ordering.py` (extra, in my ownership): `store._conn()` → `open_conn(store.db_path)` at 4 sites so no `_conn()` use remains outside edit_graph.py.

## Verification

- `pytest tests/test_storage/ tests/test_job_lock.py tests/test_migrations.py tests/test_keys_store.py tests/test_history_compaction.py tests/test_tool_executor.py` → **99 passed**
- `pytest tests/test_layering.py` → **4 passed** (4/4)
- Extra safety runs: `test_serve_edit_graph_api.py test_edit_graph_project_id.py test_serve_command_idempotency.py test_phase567_edit_render.py` → 19 passed; `test_sandbox_bridge.py test_cli_notes.py test_style/test_notes_archive.py` → 46 passed
- Grep `_conn()` in `open_edit/`: remaining uses are `edit_graph.py` internal only, plus `store._conn()` on the store's own instance in `serve/projects.py:659` and `cli.py:67` (thin wrapper → `open_conn`; `serve/` and `cli.py` are outside this wave's file list — left untouched).
- Grep `edit_graph._conn` across `open_edit/` + `tests/`: **no matches** (exit 1).

## Concerns

- `serve/projects.py:659` and `cli.py:67` still call `store._conn()` (the wrapper). Semantically identical, but if the brief wants *zero* `_conn()` references outside edit_graph.py, those two call sites are the remaining candidates for a future wave (cli.py is safe to migrate to `open_conn(store.db_path)`; serve/ belongs to the parallel track).
- `row_factory=sqlite3.Row` is a small behavior addition beyond the original `_conn()`; verified harmless for all current consumers (no tuple-equality or `isinstance(tuple)` checks on fetched rows in open_edit/ or tests/).
