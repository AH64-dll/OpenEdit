# Handoff Report — Explorer 3 (Milestone 2: EditGraphStore Integration)

## 1. Observation

### Codebase Locations & Code Verbatim Quotes
- `open_edit/storage/edit_graph.py`:
  - `EditGraphStore` initialises schema from `open_edit/storage/schema.sql` (line 46: `conn.executescript(SCHEMA_PATH.read_text())`).
  - Table `edits` columns: `edit_id, parent_id, kind, author, timestamp, status, sequence_num, payload` (`schema.sql:11-21`).
  - WAL journal mode & foreign keys enabled (lines 34-35: `conn.execute("PRAGMA journal_mode=WAL")`, `conn.execute("PRAGMA foreign_keys=ON")`).
  - `append(op, sequence_num=None)` auto-increments sequence number (`SELECT COALESCE(MAX(sequence_num), -1) + 1 FROM edits`) and serializes `op.model_dump_json()` into `payload` TEXT (lines 75-87).
  - `load_all()` deserializes via `TypeAdapter(OperationUnion).validate_json(row[0])` and sets `op.status = row[1]` (lines 94-101).
  - `update_status(edit_id, new_status)` updates column `status` where `edit_id` matches (lines 104-110).
  - `project_id` property queries or inserts `project_id` in `project_meta` table (lines 49-67).
- `open_edit/ir/api.py`:
  - `IR` constructor accepts `ops_buffer: SupportsAppend` protocol (`append(__x: Any)`).
  - Each IR operation builder method (`add_clip`, `trim_clip`, `move_clip`, etc.) instantiates concrete Pydantic operation and calls `self._ops.append(op)`.
- `open_edit/ir/apply.py`:
  - `apply_operation(timeline, op)` checks `if op.status != "applied": return timeline` (lines 72-73).
  - `derive_timeline(project)` iterates over `project.edit_graph` and calls `apply_operation` for each.
- `open_edit/cli.py`:
  - `cmd_init` creates `EditGraphStore(db_path)` and inserts metadata.
  - `cmd_list` calls `store.load_all()`.
  - `cmd_summary` passes `store.load_all()` to `derive_timeline`.
  - `cmd_undo` finds last applied op and calls `store.update_status(op.edit_id, "reverted")`.
- `open_edit/serve/projects.py` & `open_edit/serve/pi_bridge.py`:
  - `get_project_state` and `_scan_project` load `EditGraphStore(db_path)` and call `store.load_all()` / `store.project_id`.
  - `pi_bridge.py` resolves project identity via `EditGraphStore(db_path).project_id`.
- `open_edit/agent/tools/_helpers.py`:
  - `_StoreBuffer` wraps `EditGraphStore.append`.
  - `load_project()` constructs `Project` with `edit_graph=store.load_all()` and `project_id=store.project_id`.
  - `make_ir()` returns `IR` backed by `_StoreBuffer(store)`.

---

## 2. Logic Chain

1. **Observation**: `OperationUnion` in `open_edit/ir/types.py` is defined as `Annotated[Union[...], Field(discriminator="kind")]`.
2. **Logic Step 1**: In Pydantic 2, type unions annotated with field discriminators cannot use `BaseModel.model_validate()` directly because `Union` is not a `BaseModel` class.
3. **Logic Step 2**: Therefore, `TypeAdapter(OperationUnion)` (from `pydantic` / `open_edit/pydantic_compat.py`) is required to validate JSON strings and construct the appropriate concrete operation model subclass based on `kind`.
4. **Observation**: `EditGraphStore.append()` uses `op.model_dump_json()` to store the payload string, while `EditGraphStore.load_all()` uses `TypeAdapter(OperationUnion).validate_json(row[0])` and assigns `op.status = row[1]`.
5. **Logic Step 3**: Updating `op.status` from SQLite column `row[1]` ensures database-level status modifications (`store.update_status(edit_id, "reverted")`) immediately reflect in memory upon `load_all()`, overriding any static status string originally present in `payload`.
6. **Observation**: `apply_operation` in `open_edit/ir/apply.py` ignores any operation where `op.status != "applied"`.
7. **Logic Step 4**: Replaying `load_all()` ops via `derive_timeline` thus correctly excludes reverted or superseded operations without modifying the append-only SQLite edit log.

---

## 3. Caveats

- **No Schema Migrations**: SQLite schema in `schema.sql` is designed to be additive-only for local project snapshot DBs (`edit_graph.db`).
- **In-Memory Operations Mutability**: When `load_all()` returns operation instances, mutating an in-memory `op.status` does NOT persist to SQLite unless `store.update_status()` is called.
- **Concurrent Writes**: `journal_mode=WAL` allows concurrent readers during a write, but SQLite still serializes write transactions across processes.

---

## 4. Conclusion

`EditGraphStore` provides a solid, type-safe, append-only SQLite storage backend for `open_edit`:
- Operation payload serialization (`model_dump_json()`) and deserialization (`TypeAdapter(OperationUnion).validate_json()`) are cleanly separated and robust.
- Database status column (`status`) takes precedence over JSON payload status and drives state filtering during timeline replay (`derive_timeline`).
- `project_id` generation via `project_meta` ensures stable, persistent project identity across server API requests, CLI commands, and agent tool execution contexts.

---

## 5. Verification Method

To independently verify the `EditGraphStore` integration and status update / history query functionality:

1. **Run SQLite Storage Unit Tests**:
   ```bash
   python3 -m unittest open_edit/tests/test_storage/test_edit_graph.py
   ```
2. **Run Project ID Persistence Unit Test**:
   ```bash
   python3 -m unittest open_edit/tests/test_edit_graph_project_id.py
   ```
3. **Run Full Test Suite**:
   ```bash
   python3 -m unittest discover -s open_edit/tests
   ```
