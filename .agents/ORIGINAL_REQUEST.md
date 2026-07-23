# Original User Request

## Initial Request — 2026-07-21T07:50:48Z

Implement Phase 1 of the Open Edit platform: the core Intermediate Representation (IR) runtime, operation schemas, and the SQLite edit log database.

Working directory: /home/ah64/apps/mlt-pipeline/open-edit
Integrity mode: demo

## Requirements

### R1. Operations Data Models (Pydantic)
Implement concrete Pydantic schemas in `open_edit/ir/types.py` for both basic clip edits (`AddClipOp`, `RemoveClipOp`, `MoveClipOp`, `TrimClipOp`) and advanced edits (`AddTransitionOp`, `AddEffectOp`, `SetKeyframeOp`, `GroupEditsOp`, `RawMltXmlOp`, `FreeFormCodeOp`) inheriting from a base `Operation` class.

### R2. SQLite Edit Graph Store
Implement a database storage layer in `open_edit/storage/edit_graph.py` that persists the append-only log of operations for a project. It must handle inserting operations, querying history, and updating status columns.

### R3. Operation Replay & Derived State
Implement pure functions in `open_edit/ir/apply.py` (specifically `apply_operation` and `derive_timeline`) to sequentially apply the database operations to an empty project and project the current derived `Timeline` state.

## Acceptance Criteria

### Unit Tests
- [ ] Must write unit tests under `tests/` verifying all operation schemas and Pydantic validators.
- [ ] Must write unit tests under `tests/` asserting correct SQLite insertions, status updates, and history queries.
- [ ] Must write unit tests under `tests/` asserting that `derive_timeline` returns the correct, expected state after replaying sequence of operations (including revert/undo operations).
- [ ] All unit tests must pass cleanly using the Python `unittest` framework.
- [ ] The command `python3 -m unittest discover -s tests` must execute successfully with zero failures.

## Follow-up — 2026-07-22T10:16:51Z

Implement robust connection error handling, automatic dev server connectivity checks, provider failure fallback, and a topbar/input-row Request Interrupt (Stop ⏹) button for Open Edit.

Working directory: /home/ah64/apps/mlt-pipeline/open_edit

## Requirements

### R1. Provider Connection Debugging & Auto-Recovery
- Fix LLM config save network errors and provider connection dropouts.
- Implement clear UI toasts for connection drops and auto-reconnect fallback.

### R2. Request Interrupt (Stop ⏹) Button
- Add an interactive Stop button during agent turns that halts WebSocket streaming and tool execution cleanly.
- Re-enable input and return the UI to ready state instantly upon interruption.

## Acceptance Criteria

### Automated & E2E Verification
- [ ] Unit tests pass in pytest tests/ (100% pass rate).
- [ ] WebSocket cancel / disconnect handling verified via pytest.
- [ ] Manual test: Changing provider or sending a turn handles network errors cleanly and allows clicking "Stop" to interrupt execution.
