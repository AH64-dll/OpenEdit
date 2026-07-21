# Summary of Changes

## Modified / Created Files

1. `open_edit/tests/test_storage/__init__.py` (CREATED)
   - Added package initializer to enable test discovery for `python3 -m unittest discover -s tests`.

2. `open_edit/tests/test_storage/test_edit_graph.py` (REFACTORED & EXPANDED)
   - Converted test functions into `TestEditGraphStore(unittest.TestCase)` subclass.
   - Implemented `setUp()` and `tearDown()` using `tempfile.TemporaryDirectory()` for DB file creation and cleanup.
   - Implemented test assertions covering:
     - SQLite table & PRAGMA initialization (`edits`, `jobs`, `project_meta`, WAL mode, foreign keys).
     - `project_id` generation on initial access and persistent retrieval across re-reads and store reopens.
     - Direct SQLite row assertions and `load_all()` payload deserialization for ALL 10 operation schemas (`AddClipOp`, `RemoveClipOp`, `MoveClipOp`, `TrimClipOp`, `AddTransitionOp`, `AddEffectOp`, `SetKeyframeOp`, `GroupEditsOp`, `RawMltXmlOp`, `FreeFormCodeOp`).
     - Status updates (`applied`, `reverted`, `superseded`) via `update_status()`.
     - History queries via `load_all()` preserving sequence ordering.
     - Sequence reordering via `reorder()` and error handling for non-adjacent / missing operations.

3. `open_edit/tests/test_storage/test_assets.py` (REFACTORED)
   - Refactored into `TestAssetStore(unittest.TestCase)` using `tempfile.TemporaryDirectory`.
   - Used `@unittest.skipUnless(_ffprobe_available(), ...)` for conditional test execution.

4. `open_edit/tests/test_storage/test_assets_alignment.py` (REFACTORED)
   - Refactored into `TestAssetsAlignment(unittest.TestCase)` using `tempfile.TemporaryDirectory` and `unittest.mock.patch`.

5. `open_edit/tests/test_storage/test_job_lock.py` (REFACTORED)
   - Refactored into `TestJobLock(unittest.TestCase)` using `tempfile.TemporaryDirectory`.

6. `open_edit/tests/test_storage/test_notes.py` (REFACTORED)
   - Refactored into `TestNotesStore(unittest.TestCase)` using `tempfile.TemporaryDirectory`.

7. `open_edit/tests/test_storage/test_render_snapshots.py` (REFACTORED)
   - Refactored into `TestRenderSnapshotStore(unittest.TestCase)` using `tempfile.TemporaryDirectory`.

8. `open_edit/tests/test_storage/test_transcription.py` (REFACTORED)
   - Refactored into `TestTranscription(unittest.TestCase)` using `tempfile.TemporaryDirectory` and `unittest.mock.patch`.

## Verification
- Executed `python3 -m unittest discover -s tests` from `open_edit`: 87 tests discovered and passed with 0 failures.
- Executed `pytest tests/test_storage/` from `open_edit`: 61 tests passed with 0 failures.
- Executed `pytest tests/` from `open_edit`: 287 tests passed with 0 failures.
