# Analysis Report: SQLite Edit Graph Store (Milestone 2)

## Executive Summary
This report analyzes the SQLite edit graph storage implementation in `open_edit/storage/edit_graph.py` and its schema definition in `open_edit/storage/schema.sql`. The `EditGraphStore` serves as the durable, append-only persistence layer for the Open Edit platform's Intermediate Representation (IR). It maintains an immutable log of operation history, manages stable project metadata, tracks background jobs, and supports operation status modifications (e.g. undo/revert, supersede) and sequence reordering.

---

## 1. Architecture & Connection Management

### File Locations
- Database Schema: `open_edit/open_edit/storage/schema.sql`
- Store Implementation: `open_edit/open_edit/storage/edit_graph.py`
- Test Suites: `open_edit/tests/test_storage/test_edit_graph.py` and `open_edit/tests/test_edit_graph_project_id.py`

### File Layout & Database Pathing
Each project uses a single SQLite file (`edit_graph.db`) stored at `~/.open-edit/projects/<id>/edit_graph.db`. 
When instantiating `EditGraphStore(db_path)`, parent directories are automatically created:
```python
self.db_path = Path(db_path)
self.db_path.parent.mkdir(parents=True, exist_ok=True)
self._init_schema()
```

### Connection Lifecycle (`_conn`)
Connection management is handled via Python's `@contextmanager` decorator in `_conn()` (`edit_graph.py:30-42`):
```python
@contextmanager
def _conn(self) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(self.db_path))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```
Key properties:
- **WAL Mode (`PRAGMA journal_mode=WAL`)**: Enables Write-Ahead Logging to allow concurrent read operations while writes occur.
- **Foreign Key Enforcement (`PRAGMA foreign_keys=ON`)**: SQLite defaults to ignoring FK constraints; explicit enablement enforces `parent_id` foreign keys.
- **Transaction Safety**: Automatically commits on successful context exit, rolls back on exceptions, and ensures connection closure in the `finally` block.

---

## 2. Database Schema Breakdown (`schema.sql`)

The schema (`open_edit/open_edit/storage/schema.sql`) consists of three tables and four secondary indexes. The schema design is additive-only without complex migration scripts as files represent snapshot storage.

### Schema Structure Table
| Table Name | Column Name | Type | Constraints | Description |
|------------|-------------|------|-------------|-------------|
| `project_meta` | `key` | `TEXT` | `PRIMARY KEY` | Metadata key (e.g., `'project_id'`) |
| `project_meta` | `value` | `TEXT` | `NOT NULL` | Associated metadata value |
| `edits` | `edit_id` | `TEXT` | `PRIMARY KEY` | Unique ID of the edit operation |
| `edits` | `parent_id` | `TEXT` | `FOREIGN KEY REFERENCES edits(edit_id)` | Parent operation ID for graph linkage |
| `edits` | `kind` | `TEXT` | `NOT NULL` | Discriminator kind string (e.g. `'add_clip'`) |
| `edits` | `author` | `TEXT` | `NOT NULL` | Author identifier (user or agent name) |
| `edits` | `timestamp` | `TEXT` | `NOT NULL` | ISO 8601 timestamp string |
| `edits` | `status` | `TEXT` | `NOT NULL CHECK (status IN ('applied', 'reverted', 'superseded'))` | Operational state |
| `edits` | `sequence_num` | `INTEGER` | `NOT NULL` | Zero-indexed ordering sequence number |
| `edits` | `payload` | `TEXT` | `NOT NULL` | JSON serialized operation model |
| `jobs` | `job_id` | `TEXT` | `PRIMARY KEY` | Unique background job identifier |
| `jobs` | `kind` | `TEXT` | `NOT NULL` | Job type discriminator |
| `jobs` | `status` | `TEXT` | `NOT NULL CHECK (status IN ('running', 'completed', 'failed'))` | Job lifecycle state |
| `jobs` | `started_at` | `TEXT` | `NOT NULL` | Job start timestamp |
| `jobs` | `finished_at` | `TEXT` | | Job finish timestamp (nullable) |
| `jobs` | `error` | `TEXT` | | Job error message string (nullable) |

### Indexes
1. `CREATE INDEX IF NOT EXISTS idx_edits_sequence ON edits(sequence_num);` — Optimizes `ORDER BY sequence_num` queries in `load_all()`.
2. `CREATE INDEX IF NOT EXISTS idx_edits_parent ON edits(parent_id);` — Speeds up parent-child relation lookups.
3. `CREATE INDEX IF NOT EXISTS idx_edits_status ON edits(status);` — Accelerates status filter queries.
4. `CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);` — Optimizes lookup of active/failed background jobs.

---

## 3. Persistent Project ID Management

The `project_id` property (`edit_graph.py:48-67`) guarantees a stable project identifier across database reopens:
- On query, checks `project_meta` for `key = 'project_id'`.
- If present, returns the stored string `value`.
- If absent (first open), generates a new UUID via `open_edit.ir.types.new_id()`, inserts `('project_id', pid)` into `project_meta`, and returns `pid`.

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

---

## 4. Operation Append & Insertion Mechanism

Operation insertion is performed by `append(op, sequence_num=None)` (`edit_graph.py:69-89`):

```python
def append(self, op: OperationUnion, sequence_num: int | None = None) -> int:
    with self._conn() as conn:
        if sequence_num is None:
            cur = conn.execute(
                "SELECT COALESCE(MAX(sequence_num), -1) + 1 FROM edits"
            )
            sequence_num = cur.fetchone()[0]
        conn.execute(
            "INSERT INTO edits "
            "(edit_id, parent_id, kind, author, timestamp, status, "
            " sequence_num, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                op.edit_id, op.parent_id, op.kind, op.author, op.timestamp,
                op.status, sequence_num, op.model_dump_json(),
            ),
        )
    return sequence_num
```

### Mechanisms & Evidence:
1. **Sequence Auto-Assignment**: Uses `COALESCE(MAX(sequence_num), -1) + 1` to assign sequential 0-based integers.
2. **Payload Serialization**: Converts Pydantic operation models to JSON via `op.model_dump_json()`.
3. **Structured Column Storage**: Stores core fields (`edit_id`, `parent_id`, `kind`, `author`, `timestamp`, `status`, `sequence_num`) both in top-level indexed columns and within the JSON payload.

---

## 5. History Querying & Deserialization

Operations history loading is performed by `load_all()` (`edit_graph.py:91-102`):

```python
def load_all(self) -> list[OperationUnion]:
    with self._conn() as conn:
        cur = conn.execute(
            "SELECT payload, status FROM edits ORDER BY sequence_num"
        )
        ops: list[OperationUnion] = []
        for row in cur.fetchall():
            op = TypeAdapter(OperationUnion).validate_json(row[0])
            op.status = row[1]
            ops.append(op)
        return ops
```

### Mechanisms & Evidence:
1. **Sequence Order Guarantee**: Executes `SELECT payload, status FROM edits ORDER BY sequence_num`.
2. **Polymorphic Deserialization**: Uses Pydantic's `TypeAdapter(OperationUnion).validate_json(...)` to reconstruct specific concrete Operation types (`AddClipOp`, `RemoveClipOp`, etc.) based on the `kind` discriminator.
3. **Status Column Synchronization**: Overrides `op.status = row[1]` to ensure the in-memory operation object reflects any subsequent database status updates (e.g. `'reverted'` or `'superseded'`).

---

## 6. Status Modification & Operation Reordering

### Status Updates (`update_status`)
Changes an edit's status in the database (`edit_graph.py:104-110`):
```python
def update_status(self, edit_id: str, new_status: str) -> None:
    with self._conn() as conn:
        conn.execute(
            "UPDATE edits SET status = ? WHERE edit_id = ?",
            (new_status, edit_id),
        )
```
- Schema CHECK constraint limits `new_status` to `'applied'`, `'reverted'`, or `'superseded'`.
- Database error is raised if invalid status string is provided.

### Operation Reordering (`reorder`)
Swaps the sequence position of two adjacent operations (`edit_graph.py:112-141`):
```python
def reorder(self, edit_id_a: str, edit_id_b: str) -> None:
    with self._conn() as conn:
        cur = conn.execute(
            "SELECT edit_id, sequence_num FROM edits "
            "WHERE edit_id IN (?, ?) ORDER BY sequence_num",
            (edit_id_a, edit_id_b),
        )
        rows = cur.fetchall()
        if len(rows) != 2:
            raise ValueError(f"Both edits must exist; got {len(rows)} rows")
        (id1, seq1), (id2, seq2) = rows
        if abs(seq1 - seq2) != 1:
            raise ValueError(
                f"Edits must be adjacent to reorder; "
                f"got sequence_num gap {abs(seq1 - seq2)}"
            )
        conn.execute(
            "UPDATE edits SET sequence_num = ? WHERE edit_id = ?",
            (seq2, id1),
        )
        conn.execute(
            "UPDATE edits SET sequence_num = ? WHERE edit_id = ?",
            (seq1, id2),
        )
```
- Validation 1: Both edit IDs must exist in the database (len(rows) == 2).
- Validation 2: The edits must be strictly adjacent in sequence (`abs(seq1 - seq2) == 1`).
- Atomic Swap: Both UPDATE statements execute within a single connection transaction context.

---

## 7. Summary & Recommendations
The current SQLite storage implementation for Milestone 2 is complete, lightweight, robustly tested, and fully meets all Phase 1 IR requirements. No code modifications are required for Milestone 2.
