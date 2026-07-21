# EditGraphStore Integration & Operation Lifecycle Analysis

## Executive Summary

This report provides a comprehensive analysis of the `EditGraphStore` class (`open_edit/storage/edit_graph.py`), its SQLite storage mechanism, operation payload serialization/deserialization flows, project ID handling, status update flows, and history query usages across the `open_edit` codebase (`ir/api.py`, `ir/apply.py`, `cli.py`, `serve/`, `agent/`, `storage/`, and `render/`).

---

## 1. EditGraphStore Architecture & Schema Overview

### 1.1 Database Configuration (`open_edit/storage/edit_graph.py`)
- **Storage Location**: One `.db` file per project (typically `.open_edit/edit_graph.db`).
- **Concurrency & Integrity**: 
  - `PRAGMA journal_mode=WAL` (Write-Ahead Logging for non-blocking concurrent reads during writes).
  - `PRAGMA foreign_keys=ON` (Enforces referential integrity on `parent_id` foreign keys).
- **Connection Management**: Managed via `_conn()` context manager which opens connection, sets pragmas, auto-commits on success, auto-rollbacks on exception, and closes connection in `finally`.

### 1.2 Database Schema (`open_edit/storage/schema.sql`)
1. `project_meta`: Key-value table (`key TEXT PRIMARY KEY`, `value TEXT NOT NULL`) storing metadata such as `project_id`, `folder`, `ingested_count`.
2. `edits`: Append-only log of operations:
   - `edit_id TEXT PRIMARY KEY`
   - `parent_id TEXT` (Foreign key referencing `edits(edit_id)`)
   - `kind TEXT NOT NULL`
   - `author TEXT NOT NULL`
   - `timestamp TEXT NOT NULL`
   - `status TEXT NOT NULL CHECK (status IN ('applied', 'reverted', 'superseded'))`
   - `sequence_num INTEGER NOT NULL`
   - `payload TEXT NOT NULL` (JSON representation of operation object)
   - Indexes: `idx_edits_sequence`, `idx_edits_parent`, `idx_edits_status`.
3. `jobs`: Execution lock state (`job_id TEXT PRIMARY KEY`, `kind TEXT`, `status TEXT CHECK (status IN ('running', 'completed', 'failed'))`, `started_at TEXT`, `finished_at TEXT`, `error TEXT`). Managed via `JobLock` (`open_edit/storage/job_lock.py`).

---

## 2. Operation Payload Serialization & Deserialization Flow

### 2.1 Serialization (`model_dump_json()`)
- Concrete Pydantic operation models (`AddClipOp`, `TrimClipOp`, `MoveClipOp`, `AddTransitionOp`, `AddEffectOp`, etc.) inherit from `Operation` in `open_edit/ir/types.py`.
- When appending an operation to SQLite in `EditGraphStore.append(op, sequence_num=None)` (`open_edit/storage/edit_graph.py:86`):
  ```python
  conn.execute(
      "INSERT INTO edits "
      "(edit_id, parent_id, kind, author, timestamp, status, sequence_num, payload) "
      "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
      (
          op.edit_id, op.parent_id, op.kind, op.author, op.timestamp,
          op.status, sequence_num, op.model_dump_json(),
      ),
  )
  ```
- `op.model_dump_json()` serializes the full Pydantic model state into a JSON string stored in the `payload` TEXT column.

### 2.2 Deserialization (`TypeAdapter(OperationUnion)`)
- `OperationUnion` in `open_edit/ir/types.py:263-276` is defined as a discriminated union:
  ```python
  OperationUnion = Annotated[
      Union[AddClipOp, RemoveClipOp, MoveClipOp, TrimClipOp, ...],
      Field(discriminator="kind"),
  ]
  ```
- **Pydantic Compatibility Challenge**: As documented in `open_edit/pydantic_compat.py`, `OperationUnion` is a type annotation (discriminated union) rather than a subclass of `BaseModel`. Therefore, `.model_validate()` / `.model_validate_json()` cannot be called directly on `OperationUnion`.
- **Deserialization Pattern**: In `EditGraphStore.load_all()` (`open_edit/storage/edit_graph.py:99`):
  ```python
  for row in cur.fetchall():
      op = TypeAdapter(OperationUnion).validate_json(row[0])
      op.status = row[1]
      ops.append(op)
  ```
- `TypeAdapter(OperationUnion).validate_json(row[0])` parses the `payload` JSON string, inspects the `kind` field discriminator, and instantiates the matching concrete Pydantic subclass.
- **DB Column Precedence**: After validating JSON, `op.status = row[1]` overrides the status field on the instantiated operation with the SQLite `status` column value. This ensures that DB-level status changes (such as undoing/reverting or superseding an edit) take precedence over whatever status was initially serialized in the `payload` JSON.

---

## 3. Project ID Handling

### 3.1 DB-Level Persistence (`EditGraphStore.project_id`)
- Defined in `open_edit/storage/edit_graph.py:49-67`:
  ```python
  @property
  def project_id(self) -> str:
      with self._conn() as conn:
          cur = conn.execute(
              "SELECT value FROM project_meta WHERE key = 'project_id'"
          )
          row = cur.fetchone()
          if row is not None:
              return row[0]
          from open_edit.ir.types import new_id
          pid = new_id()
          conn.execute(
              "INSERT INTO project_meta (key, value) VALUES ('project_id', ?)",
              (pid,),
          )
          return pid
  ```
- On first access of a new `edit_graph.db` file, `project_id` queries `project_meta`. If absent, it generates a fresh UUID4 via `new_id()`, inserts it into `project_meta`, and returns it.
- Subsequent calls retrieve the persisted string, guaranteeing that every database file maintains a stable, unique `project_id` across reopens.

### 3.2 System-Wide Project ID Propagation
1. **Agent Tools & Sandbox Bridge**:
   - `open_edit/agent/tools/_helpers.py`: `make_ir()` retrieves `store.project_id` and constructs `IR(buffer, project_id=project_id, parent_op_id=parent_op_id)`.
   - `load_project()` constructs a `Project` model stamped with `store.project_id`.
   - `open_edit/agent/sandbox_bridge.py`: passes `store.project_id` to free-form Python execution sandboxes.
2. **Server & REST API (`open_edit/serve/`)**:
   - `open_edit/serve/projects.py`: `get_project_state(project_id)` uses `store.project_id` to query notes and verify project identity.
   - `open_edit/serve/pi_bridge.py`: injects `project_id` from `EditGraphStore(db_path).project_id` into tool invocation arguments.

---

## 4. Status Update Flows

### 4.1 Schema Constraint & Status States
- Column constraint: `status TEXT NOT NULL CHECK (status IN ('applied', 'reverted', 'superseded'))`.
- **States**:
  - `'applied'`: Default status upon creation/append. Operation is active and included during timeline derivation.
  - `'reverted'`: Operation has been undone or reverted. Retained in the database log for auditability but skipped during timeline derivation.
  - `'superseded'`: Operation has been replaced by a newer operation in an edit chain.

### 4.2 Status Update Method (`EditGraphStore.update_status`)
- Defined in `open_edit/storage/edit_graph.py:104-110`:
  ```python
  def update_status(self, edit_id: str, new_status: str) -> None:
      with self._conn() as conn:
          conn.execute(
              "UPDATE edits SET status = ? WHERE edit_id = ?",
              (new_status, edit_id),
          )
  ```

### 4.3 Integration in Operations Replay (`open_edit/ir/apply.py`)
- In `apply_operation(timeline: Timeline, op: OperationUnion) -> Timeline` (`open_edit/ir/apply.py:72-73`):
  ```python
  if op.status != "applied":
      return timeline
  ```
- Non-applied operations (`reverted` or `superseded`) act as no-ops during timeline derivation, ensuring pure state projection from active log entries.

### 4.4 Status Change Workflows
- **CLI Undo (`open_edit/cli.py:146-160`)**:
  ```python
  ops = store.load_all()
  for op in reversed(ops):
      if op.status == "applied":
          store.update_status(op.edit_id, "reverted")
          return 0
  ```
- **CLI List (`open_edit/cli.py:107-120`)**: Summarizes operations by status (`applied` count vs `reverted` count).

---

## 5. History Query & Integration Usages Across Subsystems

### 5.1 History Queries (`load_all()` and `reorder()`)
- **`load_all()`**: Queries `SELECT payload, status FROM edits ORDER BY sequence_num`. Retains strict append-sequence ordering.
- **`reorder(edit_id_a, edit_id_b)`**: Swaps sequence numbers of adjacent operations (`abs(seq1 - seq2) == 1`).

### 5.2 Usage Across `open_edit` Subsystems

| Subsystem | File Path | Usage Description |
|---|---|---|
| **IR API** | `open_edit/ir/api.py` | Defines `IR` builder; delegates operation emission to `SupportsAppend` buffer (adapted via `_StoreBuffer` in `_helpers.py` to `store.append(op)`). |
| **IR Replay** | `open_edit/ir/apply.py` | Replays loaded operations sequentially (`derive_timeline(project)` iterates `project.edit_graph` populated from `store.load_all()`). |
| **CLI** | `open_edit/cli.py` | `cmd_init` (creates DB schema & project_meta), `cmd_list` (queries graph history), `cmd_summary` (derives state from history), `cmd_undo` (updates status to reverted), `cmd_free_form` (appends child ops). |
| **Server Backend** | `open_edit/serve/projects.py` | `get_project_state` loads `store.load_all()` & `store.project_id` for UI state snapshot; `_scan_project` reads op counts. |
| **Bridge & Tools** | `open_edit/serve/pi_bridge.py` | Reads `store.project_id` to bind tool execution parameters. |
| **Agent Helpers** | `open_edit/agent/tools/_helpers.py` | `_StoreBuffer` wraps `store.append`; `load_project` loads history via `store.load_all()`; `make_ir` binds `store.project_id` & buffer. |
| **Sandbox Bridge** | `open_edit/agent/sandbox_bridge.py` | Reads edit graph and passes `store.project_id` into sandbox container. |
| **Job Locking** | `open_edit/storage/job_lock.py` | Utilizes `EditGraphStore._conn()` to manage the single-slot job lock table `jobs`. |
| **Rendering** | `open_edit/render/orchestrator.py` | Loads `store.load_all()`, filters `applied` operations, calculates `canonical_json_hash`, and builds timeline for render execution. |

---

## 6. Findings & Key Insights

1. **Clean Separation of Concerns**: `EditGraphStore` isolates SQLite persistence, sequence assignment, and transaction logic. It exposes a minimal, clean API (`append`, `load_all`, `update_status`, `reorder`, `project_id`).
2. **Type-Safe Serialization**: Using `model_dump_json()` for storage and `TypeAdapter(OperationUnion).validate_json()` for deserialization guarantees strict Pydantic validation on read/write without needing custom table columns per operation field.
3. **Database Precedence for Dynamic Attributes**: Deserialized operations get their `status` field explicitly updated from SQLite (`op.status = row[1]`), avoiding stale status values in the JSON payload blob.
4. **Stable Project Identity**: The `project_meta` key-value table guarantees `project_id` stability across server restarts, CLI runs, and multi-tool agent sessions.
