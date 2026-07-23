# Open Edit Backend Architecture Exploration Report

## Executive Summary

This report presents an in-depth code investigation of the **Open Edit** backend codebase located at `/home/ah64/apps/mlt-pipeline/open_edit`. The investigation focuses on the WebSocket communication lifecycle, agent turn execution loop, task control and cancellation mechanics, and test suite layout.

---

## 1. WebSocket Communication Endpoints and Message Handling Loops

### 1.1 Route & Connection Lifecycle
- **Endpoint Route**: `WS /api/chat/{project_id}` defined in `open_edit/serve/app.py:636`.
- **Pre-Connection Validation**:
  - Before accepting the WebSocket, `ws_chat` invokes `_require_project(project_id)` (`app.py:658`).
  - If the project does not exist (`HTTPException(404)`), the server accepts the socket, sends a JSON error frame (`{"type": "error", "message": "project not found: ..."}`), and closes the socket with close code `4404` (`app.py:665-669`).
- **Connection Handshake**:
  - Upon successful project validation, the server accepts the connection (`websocket.accept()`) and immediately sends a `ready` event frame (`app.py:673`):
    ```json
    {"type": "ready", "project_id": "<project_id>"}
    ```

### 1.2 Inbound Protocol & Frame Processing
- **Inbound Message Format**:
  - The client sends JSON strings:
    ```json
    {
      "message": "User prompt string...",
      "conv_id": "optional-conversation-id-uuid"
    }
    ```
- **Parsing & Validation**:
  - `raw = await websocket.receive_text()` (`app.py:681`).
  - If JSON decoding fails: returns `{"type": "error", "message": "invalid JSON..."}` and keeps loop open.
  - If `message` is missing or empty: returns `{"type": "error", "message": "missing 'message' field"}`.
- **Conversation State Resolution**:
  - If `conv_id` is omitted, `agent_mod.new_conversation_id()` (`agent.py:133`) generates a new UUID hex string.
  - Per-connection in-memory history cache (`conversations: dict[str, list[dict]]`) stores active message threads (`app.py:677`).
  - Disk persistence is loaded lazily from `.open_edit/conversations/<conv_id>.jsonl` via `load_conversation(project_id, conv_id)` (`agent.py:102`).

### 1.3 Outbound Event Streaming Protocol
The server streams events yielded by `agent_mod.run_agent_turn(...)` directly to the WebSocket via `websocket.send_text(json.dumps(event, default=str))` (`app.py:715`).

**Event Types & Wire Shapes**:
1. `ready`: `{"type": "ready", "project_id": "..."}`
2. `text`: `{"type": "text", "text": "assistant text delta..."}`
3. `tool_start`: `{"type": "tool_start", "name": "...", "input": {...}}`
4. `tool_result`: `{"type": "tool_result", "name": "...", "result": {...}}`
5. `render`: `{"type": "render", "path": "...", "mode": "proxy"|"final"}`
6. `verification_started`: `{"type": "verification_started", "render_id": "...", "stage": "sampling"|"encoding"|"ready"}`
7. `verification_result`: `{"type": "verification_result", "outcome": "pass"|"iterate"|"failed"|"skipped"|"capped", "verdict_source": "..."}`
8. `error`: `{"type": "error", "message": "..."}`
9. `done`: `{"type": "done", "stop_reason": "end_turn"|"error"|"max_iterations"}`
10. `cost_update`: `{"type": "cost_update", "turn_tokens": int, "turn_cost_usd": float, "session_cost_usd": float, "source": "pi"|"computed"|"unavailable"}`

### 1.4 Exception & Disconnect Handling in `ws_chat`
- **Turn Exception Handling** (`app.py:716-725`):
  - Any unhandled exception during `run_agent_turn` is caught by `except Exception as exc:`.
  - Sends `{"type": "error", "message": f"agent turn crashed: {exc}"}` followed by `{"type": "done", "stop_reason": "error"}`.
  - The WebSocket message loop (`while True`) remains active.
- **Client Disconnect** (`app.py:726-727`):
  - `WebSocketDisconnect` is caught outside the `while True` loop and returns `None` cleanly.

---

## 2. Current Agent Turn Execution Loop and Task Control Mechanisms

### 2.1 Agent Turn Workflow (`run_agent_turn`)
Located in `open_edit/serve/agent.py:587-975`, `run_agent_turn` is an `AsyncIterator[AgentEvent]`:

1. **System Prompt Assembly** (`agent.py:239-266`):
   - Reads `ProjectState` and constructs a deterministic system prompt containing project state JSON, tool summary, and IR model guides.
2. **Conversation History Update** (`agent.py:627-631`):
   - Appends user message to `conversation_history` list and appends to disk via `append_to_conversation` (`agent.py:122`).
3. **Turn Iteration Loop** (`for _ in range(MAX_AGENT_ITERATIONS)`):
   - `MAX_AGENT_ITERATIONS` defaults to `10` (configurable via `OPEN_EDIT_AGENT_MAX_ITERATIONS` env var, `agent.py:83`).
   - Streams from LLM using `stream_chat(...)` (`open_edit/serve/llm.py:126`).
   - Emits `text_delta` chunks and aggregates `tool_use` blocks.
4. **Completion Check**:
   - If no `tool_use` blocks were emitted, yields `{"type": "done", "stop_reason": stop_reason}` and `cost_update` event, saves session cost via `_save_cost_state_async`, and returns (`agent.py:791-815`).
5. **Tool Execution**:
   - Split into **mutations** (quick edit-graph operations) and **render tools** (`trigger_render`).
   - Mutations executed first via `_execute_tool(tool_name, tool_input, project_path)` (`agent.py:834`).
   - `trigger_render` executed last in batch via `_execute_tool("trigger_render", ...)` which maps to `tool_executor.execute_trigger_render` (`tool_executor.py:55`).
6. **Visual Verification Stage** (`agent.py:877-927`):
   - If visual verification is enabled (`verify_active`), calls `_maybe_verify_render` (`agent.py:340`) to extract JPEG frames via `ffmpeg` / `encode_jpeg` on worker thread.
7. **History Synchronization**:
   - Appends assistant response and `tool_result` messages to history and persists to `.jsonl` disk storage.
   - Loops back to Step 3 for the next iteration.

### 2.2 LLM Streaming Architecture & CLI Adapters
Located in `open_edit/serve/llm.py` and `open_edit/serve/cli_adapter.py`:

- **Providers**:
  - `anthropic`: Direct async Anthropic SDK streaming (`_stream_anthropic`, `llm.py:644`).
  - `openai`: Direct async OpenAI SDK streaming (`_stream_openai`, `llm.py:765`).
  - `pi`, `opencode`, `antigravity`, `jcode`: Subprocess CLI drivers (`_stream_cli`, `llm.py:428`).
- **CLI Subprocess Driver (`_stream_cli`)**:
  - Uses `asyncio.create_subprocess_exec` (`llm.py:494`) to launch binary.
  - Enforces per-adapter timeout (`adapter.default_timeout_s`, e.g. 60s for `pi`, 120s for `opencode`).
  - Streams stdout line-by-line using `asyncio.wait_for(proc.stdout.readline(), timeout=...)`.

### 2.3 Cost Tracking & Persistence
- Session costs are tracked per conversation in `.open_edit/cost.json` (`agent.py:148-215`).
- Read synchronously on turn start (`_load_cost_state`), written asynchronously off-loop via `asyncio.to_thread(_write_cost_json_sync)` after yielding `cost_update`.

---

## 3. Task Cancellation and Interruption Architecture

### 3.1 Existing Limitations in Current Codebase

1. **Synchronous/Blocking In-Turn Event Loop Execution in `ws_chat`**:
   - In `app.py:709`, `ws_chat` runs `async for event in agent_mod.run_agent_turn(...)`.
   - `websocket.receive_text()` is **not** called while `run_agent_turn` is iterating.
   - Any inbound WebSocket frame sent by client during turn execution (e.g. `{"type": "stop"}`) remains unread in Starlette's network buffer until the entire agent turn finishes.
2. **Unused `should_cancel` Hook**:
   - `run_agent_turn` accepts `should_cancel: Callable[[], bool] | None = None` (`agent.py:592`), but `ws_chat` calls it with `should_cancel=None`.
3. **Blocking Subprocess Execution in Tool Executor**:
   - `execute_trigger_render` in `tool_executor.py:78` calls `subprocess.run(["open_edit", "render", ...], timeout=RENDER_TIMEOUT_S)`.
   - `subprocess.run` is synchronous and blocks the Python process/thread for up to 1800s. Python asyncio task cancellation cannot interrupt a synchronous `subprocess.run` call in progress.

### 3.2 Connection Drop & Disconnect Behavior

When a client drops connection mid-turn:
1. `websocket.send_text(...)` in `app.py:715` raises `WebSocketDisconnect` on the next frame yield.
2. The `ws_chat` frame exits, closing the `run_agent_turn` async generator.
3. If an LLM subprocess is running in `_stream_cli` (`llm.py:606`), `asyncio.CancelledError` is caught and invokes `proc.kill()`.
4. However, if `execute_trigger_render` or an `ffmpeg` frame extraction step is running synchronously, the execution continues in background until complete before process resources are freed.

### 3.3 Proposed Architecture for Clean Interruption & Stop/Cancel Frames

To cleanly support client Stop/Cancel signals and connection drops:

```
+-----------------------------------------------------------------------------------+
| WS Endpoint (ws_chat)                                                             |
|                                                                                   |
|  +---------------------------+            +------------------------------------+  |
|  | Message Receiver Loop     |            | Agent Turn Worker Task             |  |
|  | (websocket.receive_text)  |            | (asyncio.create_task)              |  |
|  +-------------+-------------+            +-----------------+------------------+  |
|                |                                            |                     |
|         Receives "stop"                                     | Yields events       |
|                |                                            v                     |
|                v                                   +-------------------+          |
|      Set cancel_event.set()                        | Outbound Queue /  |          |
|      Cancel turn_task.cancel() -------> Cancel --->| WS Send Loop      |          |
|                                                    +-------------------+          |
+-----------------------------------------------------------------------------------+
                                                              |
                                                              v
                                             +----------------------------------+
                                             | Cleanup Hooks:                   |
                                             | - Kill CLI subprocess (proc.kill)|
                                             | - Kill render subprocess         |
                                             | - Remove temporary verify dir    |
                                             | - Save partial cost sidecar      |
                                             | - Yield done (stop_reason=stop)  |
                                             +----------------------------------+
```

#### Step-by-Step Technical Design:

1. **Concurrent Dispatcher in `ws_chat` (`app.py`)**:
   - Refactor `ws_chat` to run a concurrent event loop pattern:
     ```python
     turn_task: asyncio.Task | None = None
     cancellation_event = asyncio.Event()

     async for raw_msg in receive_messages(websocket):
         payload = json.loads(raw_msg)
         msg_type = payload.get("type")
         if msg_type in ("stop", "cancel"):
             if turn_task and not turn_task.done():
                 cancellation_event.set()
                 turn_task.cancel()
                 await websocket.send_text(json.dumps({
                     "type": "done", "stop_reason": "cancelled"
                 }))
         elif payload.get("message"):
             cancellation_event.clear()
             turn_task = asyncio.create_task(
                 run_turn_and_stream(websocket, payload, cancellation_event)
             )
     ```
2. **Async Subprocess Wrapper for Renders (`tool_executor.py`)**:
   - Convert `execute_trigger_render` from `subprocess.run` to `asyncio.create_subprocess_exec`:
     ```python
     proc = await asyncio.create_subprocess_exec(
         "open_edit", "render", "--mode", mode,
         stdout=asyncio.subprocess.PIPE,
         stderr=asyncio.subprocess.PIPE,
         cwd=str(project_path)
     )
     try:
         stdout, stderr = await proc.communicate()
     except asyncio.CancelledError:
         proc.kill()
         await proc.wait()
         raise
     ```
3. **`CancelledError` & Resource Cleanup in `agent.py`**:
   - Ensure `run_agent_turn` wraps loop iterations in `try ... except asyncio.CancelledError:`:
     - Terminate active subprocesses (`proc.kill()`).
     - Remove temporary directories created for visual verification (`oe_verify_*`).
     - Persist current accumulated token usage & cost to `.open_edit/cost.json`.
     - Release any edit graph locks cleanly.

---

## 4. Existing Test Suite Structure and Pytest Configuration

### 4.1 Pytest Configuration (`pyproject.toml`)
Located in `pyproject.toml:45-48`:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-ra -q"
```

### 4.2 Test Suite Taxonomy & Organization

The `tests/` directory contains 91 test files organized as follows:

| Category | Primary Test Files | Purpose / Scope |
| :--- | :--- | :--- |
| **Serve & WebSockets** | `test_serve_app.py`<br>`test_serve_agent.py`<br>`test_serve_cost.py`<br>`test_serve_errors.py`<br>`test_serve_pi_bridge.py`<br>`test_serve_agent_visual_verify.py` | FastAPI routes, WS `ws_chat` flow, Agent turn loop events, cost sidecars, error JSON shapes (`{"error": "..."}`), and visual verification. |
| **LLM & CLI Adapters** | `test_cli_adapter.py`<br>`test_opencode_adapter.py`<br>`test_providers.py`<br>`test_serve_llm_config_api.py`<br>`test_serve_llm_pi.py`<br>`test_serve_llm_usage.py` | CLI adapter discovery (`pi`, `opencode`, `agy`, `jcode`), JSON event parsing, LLM config endpoints, model dropdown listings. |
| **Runtime & Key Store** | `test_runtimes_registry.py`<br>`test_runtimes_keys_store.py` | Environment and `keys.json` API key discovery and masking. |
| **IR & Edit Graph** | `tests/test_ir/test_apply.py`<br>`tests/test_ir/test_catalog.py`<br>`tests/test_ir/test_commutativity.py`<br>`tests/test_ir/test_types.py`<br>`tests/test_ir/test_validate.py`<br>`test_edit_graph_project_id.py` | Intermediate Representation (IR), timeline derivation, operation validation, edit graph persistence in `edit_graph.db`. |
| **Agent Tools & Sandbox** | `test_sandbox_bridge.py`<br>`test_sandbox/test_render_sandbox.py`<br>`test_pyagent_run_python.py`<br>`test_pyagent_import_asset.py`<br>`test_pyagent_search_assets.py` | Sandboxed Python code execution, asset store ingestion, tool security and execution. |
| **QC (Quality Control)** | `tests/test_qc/test_black_frames.py`<br>`tests/test_qc/test_gate.py`<br>`tests/test_qc/test_silence.py`<br>`tests/test_qc/test_thumbnail.py` | Video quality control checks (black frame detection, silence detection, thumbnail generation). |
| **Render Engine** | `tests/test_render/test_cache.py`<br>`tests/test_render/test_orchestrator.py`<br>`tests/test_render/test_validators.py` | Render caching, job queue management, timeouts, MLT rendering. |

### 4.3 Key Test Fixtures (`tests/conftest.py`)
- `tmp_notes_db`: Creates an isolated temporary SQLite `NotesStore`.
- `tmp_project_with_assets`: Creates a mock project pre-populated with a CAS video asset (sidecar JSON + CAS byte placeholder) and pre-seeded `edit_graph.db` with `AddClipOp`, enabling standalone testing of freeform agent tools without running full video renders.

---

## 5. Code Locations Reference Summary Table

| Functional Area | Source File Path | Key Functions / Classes / Lines |
| :--- | :--- | :--- |
| **WebSocket Chat Endpoint** | `open_edit/serve/app.py` | `ws_chat` (lines 636-731), `_require_project` (lines 754-759) |
| **Agent Turn Loop** | `open_edit/serve/agent.py` | `run_agent_turn` (lines 587-975), `_build_system_prompt` (lines 239-266), `_maybe_verify_render` (lines 343-527) |
| **LLM Streaming & CLI Drivers** | `open_edit/serve/llm.py` | `stream_chat` (lines 126-222), `_stream_cli` (lines 428-638), `_stream_pi` (lines 252-300), `_stream_anthropic` (lines 644-759) |
| **CLI Adapter Interface** | `open_edit/serve/cli_adapter.py` | `CLIAdapter` (lines 28-49), `_PiAdapter` (lines 96-157), `_OpenCodeAdapter` (lines 159-208), `_AntigravityAdapter` (lines 210-259) |
| **Tool Execution** | `open_edit/serve/tool_executor.py` | `execute_tool` (lines 39-53), `execute_trigger_render` (lines 55-130) |
| **TS Extension Python Bridge** | `open_edit/serve/pi_bridge.py` | `_run_agent_tool` (lines 68-105), `_run_trigger_render` (lines 293-353) |
| **Cost Tracking Sidecar** | `open_edit/serve/agent.py` | `_load_cost_state` (lines 153-172), `_save_cost_state_async` (lines 204-215) |
| **Pytest Configuration** | `open_edit/pyproject.toml` | `[tool.pytest.ini_options]` (lines 45-48) |
| **Test Fixtures** | `open_edit/tests/conftest.py` | `tmp_notes_db`, `tmp_project_with_assets` |
