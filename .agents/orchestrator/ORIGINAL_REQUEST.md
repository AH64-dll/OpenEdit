# Original User Request

## 2026-07-21T07:51:11Z

Implement Phase 1 of the Open Edit platform: the core Intermediate Representation (IR) runtime, operation schemas, and the SQLite edit log database according to the requirements and acceptance criteria in ORIGINAL_REQUEST.md.

Requirements summary:
1. Operation Data Models (Pydantic) in open_edit/ir/types.py (AddClipOp, RemoveClipOp, MoveClipOp, TrimClipOp, AddTransitionOp, AddEffectOp, SetKeyframeOp, GroupEditsOp, RawMltXmlOp, FreeFormCodeOp inheriting from base Operation class).
2. SQLite Edit Graph Store in open_edit/storage/edit_graph.py (append-only log of operations, inserting operations, querying history, updating status columns).
3. Operation Replay & Derived State in open_edit/ir/apply.py (pure functions apply_operation and derive_timeline to sequentially apply operations to empty project and project current derived Timeline state, handling revert/undo).
4. All unit tests under tests/ passing cleanly using python3 -m unittest discover -s tests with zero failures.

## 2026-07-22T13:17:10Z

Implement robust connection error handling, automatic dev server connectivity checks, provider failure fallback, and a topbar/input-row Request Interrupt (Stop ⏹) button for Open Edit.
Target project codebase: /home/ah64/apps/mlt-pipeline/open_edit

Requirements:
- R1. Provider Connection Debugging & Auto-Recovery (Fix LLM config save network errors & provider connection dropouts, clear UI toasts, auto-reconnect fallback).
- R2. Request Interrupt (Stop ⏹) Button (Add interactive Stop button during agent turns that halts WebSocket streaming and tool execution cleanly; re-enable input & return UI to ready state instantly).
Acceptance Criteria:
- Unit tests pass in pytest tests/ (100% pass rate).
- WebSocket cancel / disconnect handling verified via pytest.
- Manual test: Changing provider or sending a turn handles network errors cleanly and allows clicking "Stop" to interrupt execution.
