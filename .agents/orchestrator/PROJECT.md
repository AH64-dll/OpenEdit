# Project: Open Edit Phase 1

## Architecture
- `open_edit/ir/types.py`: Pydantic data models for operations (`AddClipOp`, `RemoveClipOp`, `MoveClipOp`, `TrimClipOp`, `AddTransitionOp`, `AddEffectOp`, `SetKeyframeOp`, `GroupEditsOp`, `RawMltXmlOp`, `FreeFormCodeOp` inheriting from `Operation`).
- `open_edit/storage/edit_graph.py`: SQLite edit graph storage layer supporting append-only log, inserting operations, history queries, and status updates.
- `open_edit/ir/apply.py`: Replay & derived state logic (`apply_operation`, `derive_timeline`).
- `open_edit/tests/`: Unit tests validating all operation schemas, SQLite operations, and timeline state derivation / undo / revert functionality.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Operations Data Models | `open_edit/ir/types.py` & schemas/validators unit tests | none | DONE |
| 2 | SQLite Edit Graph Store | `open_edit/storage/edit_graph.py` & storage unit tests | M1 | DONE |
| 3 | Operation Replay & Derived State | `open_edit/ir/apply.py` & replay unit tests | M1, M2 | IN_PROGRESS |
| 4 | Suite Verification | Run `python3 -m unittest discover -s tests` & final verification | M1, M2, M3 | PLANNED |

## Interface Contracts
- Operation schemas inherit from base `Operation`.
- `EditGraphStore` interface for SQLite log persistence.
- `apply_operation(timeline, op)` and `derive_timeline(ops)` for replay state.

## Code Layout
- Package: `open_edit` under `/home/ah64/apps/mlt-pipeline/open_edit`
- Modules: `open_edit/ir/types.py`, `open_edit/storage/edit_graph.py`, `open_edit/ir/apply.py`
- Tests: `open_edit/tests/`
