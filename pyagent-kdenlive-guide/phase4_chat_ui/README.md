# PyAgent — Phase 4 Chat UI

A local FastAPI web app that wraps the Phase 3 `pi` extension runtime as a chat
interface, so you can edit a `.kdenlive` project by talking to `pi` in a browser
tab positioned next to Kdenlive.

## What it does

- **Chat transcript** — multi-turn conversation with `pi` (which has the
  `pyagent_*` Kdenlive-editing tools from Phase 3 loaded).
- **Live project-state panel** — shows `get_project_info()` (resolution, fps,
  track count, duration) and refreshes after every applied edit and on any
  external file change (Phase 5 handoff hook).
- **Quick-action buttons** — one-click common requests (add crossfade, list
  effects, etc.).
- **Plan card** — pending-edit summary is rendered as a distinct, approvable
  card. Phase 3 auto-approves via `PYAGENT_AUTO_APPROVE`; this card is the UI
  affordance and is wired to the approve/reject REST endpoint.

## Architecture

```
browser (vanilla JS)  --WebSocket /ws-->  FastAPI (app.py)
                                            |-- PiClient  -> spawns `pi --mode json`
                                            |-- state.py  -> run_op(...)  [Phase 3]
                                            |-- watcher.py -> watchfiles on the .kdenlive
```

- No JS build step. `static/index.html`, `app.js`, `style.css` served as files.
- Binds to `127.0.0.1` only. No auth, no CORS — single-user local dev tool.
- `PiClient` runs `pi --mode json --print --session-id <id>` per prompt; the
  session id preserves multi-turn context across spawns. The JSON event stream
  is parsed into normalized `PiEvent`s (messages, tool calls, errors).

## File map (post-2026-07-19 cleanup)

| File | Purpose | Lines |
|---|---|---|
| `app.py` | FastAPI routes only (slimmed from 722 → 135 LOC in cleanup) | 135 |
| `pi_client.py` | Spawns `pi --mode json`, parses events | 240 |
| `session.py` | Per-WebSocket session state | 225 |
| `state.py` | Bridges WebSocket events to Phase 3 `run_op(...)` | 42 |
| `watcher.py` | `watchfiles` on the `.kdenlive` (with `.kdenlive.lock` / `~`-suffix filter to fix false positives) | 76 |
| `uploads.py` | Multipart upload handling (extracted from `app.py`) | 76 |
| `types.py` | Shared dataclasses (`Plan`, `PiEvent`, ...) | 56 |
| `adapters/_registry.py` | Adapter registry: provider id → adapter class | 17 |
| `adapters/piagent.py` | Adapter for the `piagent` provider | 87 |
| `adapters/opencode.py` | Adapter for the `opencode` provider | 181 |
| `adapters/__init__.py` | `list_apps()` + `set_app()` re-exports | 86 |
| `ws/manager.py` | WebSocket connection registry | 49 |
| `ws/handler.py` | Single WebSocket message handler | 260 |
| `ws/handlers.py` | Message dispatch table | 225 |
| `ws/__init__.py` | Re-exports | 22 |

Legacy `agent_adapters.py` (358 LOC, hard-coded
`available() -> False`) was removed — split into the per-app files
above. Legacy `ws.py` (358 LOC) was also over-budget and was split
into `ws/{manager,handler,handlers}.py`.

## Setup

```sh
pip install --break-system-packages -e .     # or: make install
```

Requires `pi` on PATH (the `@earendil-works/pi-coding-agent` CLI) and the
Phase 3 extension at `../phase3_pyagent_core/extension.ts`.

## Run

```sh
make run PROJECT=/path/to/your.kdenlive
# or directly:
python3 -m phase4_chat_ui --project /path/to/your.kdenlive --port 8765
```

Then open http://127.0.0.1:8765 in a browser next to Kdenlive.

## Test

```sh
make test                                # 42 passed
```

Per-test-file:

| File | Tests | Purpose |
|---|---|---|
| `test_session.py` | 11 | Per-WebSocket session lifecycle |
| `test_app.py` | 8 | FastAPI route smoke |
| `test_agent_adapters.py` | 5 | Adapter registry + set-app path |
| `test_pi_client.py` | 4 | pi subprocess spawning + event parsing |
| `test_websocket.py` | 4 | WebSocket message dispatch |
| `test_state.py` | 4 | state.py bridges to Phase 3 |
| `test_watcher.py` | 2 | watchfiles filter (false-positive regression) |
| `test_task5_ui.py` | 2 | Phase 5 handoff hook |
| `test_task4_apps.py` | 2 | apps list API contract |
