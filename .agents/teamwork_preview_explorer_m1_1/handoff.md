# Handoff Report: Open Edit Backend Architecture Exploration

## 1. Observation

Direct observations from source inspection of `/home/ah64/apps/mlt-pipeline/open_edit`:

1. **WebSocket Chat Endpoint (`open_edit/serve/app.py:636-731`)**:
   - Route definition: `@app.websocket("/api/chat/{project_id}")`
   - Initial check: Calls `_require_project(project_id)` (`app.py:658`). If 404, accepts connection, sends `{"type": "error", "message": detail}`, and closes socket with code `4404`.
   - On success: accepts WebSocket connection and sends `{"type": "ready", "project_id": project_id}` (`app.py:673`).
   - Inbound message handling loop (`app.py:680-725`):
     ```python
     while True:
         raw = await websocket.receive_text()
         ...
         async for event in agent_mod.run_agent_turn(
             project_id=project_id,
             user_message=message,
             conversation_history=history,
             conv_id=conv_id,
         ):
             await websocket.send_text(json.dumps(event, default=str))
     ```
   - Inbound message parsing expects `{"message": "...", "conv_id": "..."}`.
   - Outbound events emitted: `ready`, `text`, `tool_start`, `tool_result`, `render`, `verification_started`, `verification_result`, `error`, `done`, `cost_update`.

2. **Agent Turn Loop (`open_edit/serve/agent.py:587-975`)**:
   - Signature: `async def run_agent_turn(project_id, user_message, conversation_history, conv_id=None, should_cancel=None) -> AsyncIterator[AgentEvent]`.
   - Iteration cap: `MAX_AGENT_ITERATIONS = int(os.environ.get("OPEN_EDIT_AGENT_MAX_ITERATIONS", "10"))` (`agent.py:83`).
   - LLM Streaming: `stream_chat(...)` in `open_edit/serve/llm.py:126` streams tokens & tool calls from Anthropic, OpenAI, or CLI sub-processes (`pi`, `opencode`, `agy`, `jcode`).
   - Tool Execution: Non-`trigger_render` tools execute first via `_execute_tool(tool_name, tool_input, project_path)` (`agent.py:834`). `trigger_render` executes last via `tool_executor.execute_trigger_render` (`tool_executor.py:55`).
   - Cost tracking: Loaded from `.open_edit/cost.json` on turn start; saved off-loop via `_save_cost_state_async` (`agent.py:204`) after yielding `cost_update`.

3. **Task Cancellation Mechanisms & Gaps**:
   - `ws_chat` in `app.py:709` awaits `run_agent_turn` directly inside `async for`.
   - During `run_agent_turn` execution, `websocket.receive_text()` is **not** polled, preventing any incoming `{"type": "stop"}` or `{"type": "cancel"}` frame from being read while the agent turn is active.
   - `should_cancel` parameter exists in `run_agent_turn` (`agent.py:592`) but is unused by `ws_chat` (called with `should_cancel=None`).
   - `tool_executor.execute_trigger_render` (`tool_executor.py:78`) invokes `subprocess.run(["open_edit", "render", ...], timeout=RENDER_TIMEOUT_S)`, which is a synchronous blocking call that cannot be interrupted mid-flight by Python asyncio task cancellation.
   - Subprocess driver `_stream_cli` in `llm.py:606` properly catches `asyncio.CancelledError` and terminates CLI subprocesses via `proc.kill()`.

4. **Test Suite Structure & Config (`pyproject.toml:45-48` and `tests/`)**:
   - `pytest` configured with `testpaths = ["tests"]`, `pythonpath = ["."]`, `addopts = "-ra -q"`.
   - 91 test files organized into serve/web sockets (`test_serve_app.py`, `test_serve_agent.py`), CLI adapters (`test_cli_adapter.py`, `test_opencode_adapter.py`), IR & edit graph (`test_ir/*`), sandbox & tools (`test_sandbox_bridge.py`, `test_pyagent_*`), and QC (`test_qc/*`).
   - Key fixtures in `tests/conftest.py`: `tmp_notes_db` and `tmp_project_with_assets`.

---

## 2. Logic Chain

1. **Observation 1** shows that `ws_chat` in `app.py` blocks synchronously awaiting `async for event in run_agent_turn(...)`.
2. Because `websocket.receive_text()` is only called before `run_agent_turn` starts and after `run_agent_turn` finishes, any WebSocket message sent by the client (such as `{"type": "stop"}` or `{"type": "cancel"}`) while `run_agent_turn` is running cannot be read by the server until after the turn completes.
3. **Observation 3** shows that while `_stream_cli` handles `asyncio.CancelledError` by calling `proc.kill()`, `execute_trigger_render` in `tool_executor.py` runs a synchronous `subprocess.run(...)` call, preventing task cancellation from aborting rendering operations immediately.
4. Therefore, implementing clean task cancellation requires:
   - Refactoring `ws_chat` to run `run_agent_turn` as a background `asyncio.Task` while concurrently listening on `websocket.receive_text()`.
   - Passing an `asyncio.Event` / `should_cancel` callback into `run_agent_turn`.
   - Refactoring `execute_trigger_render` from synchronous `subprocess.run` to `asyncio.create_subprocess_exec` so `asyncio.CancelledError` can catch and terminate active render processes.
5. **Observation 4** shows that the existing 91 test files in `tests/` already cover `test_serve_app.py`, `test_serve_agent.py`, `test_cli_adapter.py`, `test_serve_errors.py`, and `test_serve_pi_bridge.py`, providing a solid foundation for verifying WebSocket and task cancellation enhancements.

---

## 3. Caveats

- Node.js runtime and external CLI binaries (`pi`, `opencode`, `agy`, `jcode`, `ffprobe`, `ffmpeg`, `hyperframes`) were inspected via python wrapper integration code rather than running full end-to-end renders.
- Terminal execution of `pytest` in this environment returned sandbox restriction code, but static code inspection of all test files in `tests/` and configuration in `pyproject.toml` confirmed the test layout and structure.

---

## 4. Conclusion

The Open Edit backend has a well-structured, modular architecture:
- WebSocket handling in `open_edit/serve/app.py` manages project authorization, message parsing, and event streaming.
- Agent turn execution in `open_edit/serve/agent.py` orchestrates LLM streaming (`llm.py`), tool execution (`tool_executor.py`), cost sidecars (`cost.json`), and visual verification (`visual_verify.py`).
- The primary architectural gap is the **lack of concurrent message polling during agent turn execution in `ws_chat`** and **synchronous subprocess blocking in `execute_trigger_render`**.
- Implementing a task dispatcher pattern in `ws_chat` along with async subprocess creation in `tool_executor.py` will enable clean, instant cancellation for both WebSocket stop frames and abrupt client disconnects without state or lock corruption.

---

## 5. Verification Method

To verify these observations independently:
1. Inspect WebSocket endpoint: `open_edit/serve/app.py` at line 636 (`ws_chat`).
2. Inspect Agent turn loop: `open_edit/serve/agent.py` at line 587 (`run_agent_turn`).
3. Inspect LLM streaming & subprocess management: `open_edit/serve/llm.py` at line 126 (`stream_chat`) and line 428 (`_stream_cli`).
4. Inspect Tool execution: `open_edit/serve/tool_executor.py` at line 39 (`execute_tool`) and line 55 (`execute_trigger_render`).
5. Inspect Test suite setup: `open_edit/pyproject.toml` lines 45-48 and `open_edit/tests/conftest.py`.
