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
make test
# or:
python3 -m unittest discover -s phase4_chat_ui -p "test_*.py"
```
