# Project: Open Edit Connection Handling & Interrupt Button

## Architecture
- Target Codebase: `/home/ah64/apps/mlt-pipeline/open_edit`
- Backend: Python FastAPI / WebSocket application managing LLM provider API clients, configuration persistence, agent turn execution loops, tool cancellation, and WebSocket client communication (`open_edit/serve/`).
- Frontend: Web UI components (topbar control bar, prompt input row, toast notification system, WebSocket client runtime) (`open_edit/serve/static/`).

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Architecture & Problem Exploration | Backend WS handlers, LLM config, Agent turn loop, Frontend UI | none | DONE |
| 2 | Backend Connection Handling & Interrupt Logic | Provider fallback, WS cancel frame, tool/stream halt, config error handling | M1 | DONE |
| 3 | Frontend Stop Button & Connection Toasts | Topbar & input-row Stop ⏹ button, UI state reset, connection drop toasts | M1, M2 | DONE |
| 4 | Test Suite Verification & Audit | `pytest tests/` 100% pass rate, WS cancel pytest, Forensic Audit | M1, M2, M3 | IN_PROGRESS |

## Interface Contracts
- WebSocket turn control: Client sends interrupt frame `{"type": "cancel"}` or `{"type": "stop"}`; Server cancels task execution cleanly and sends `{"type": "cancelled"}` or closes cleanly.
- LLM Provider error handling: Catch file write / API / network errors on config save and generation turns, return clear detail, and support fallback / connectivity checks (`GET /api/health`).
- Frontend state machine: Input row & topbar switch between 'idle' (Send) and 'executing' (Stop ⏹) state. Clicking Stop instantly resets UI to ready state and toasts user.

## Code Layout
- Package: `/home/ah64/apps/mlt-pipeline/open_edit`
- Backend: `open_edit/serve/app.py`, `open_edit/serve/agent.py`, `open_edit/serve/tool_executor.py`, `open_edit/serve/cli_adapter.py`, `open_edit/serve/llm.py`
- Frontend: `open_edit/serve/static/index.html`, `open_edit/serve/static/app.js`, `open_edit/serve/static/js/ws.js`, `open_edit/serve/static/js/chat.js`
- Tests: `open_edit/tests/`
