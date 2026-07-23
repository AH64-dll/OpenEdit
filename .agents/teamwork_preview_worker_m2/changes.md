# Changes Report — Milestone 2 & Milestone 3 Implementation

## Summary of Changes

Milestone 2 & Milestone 3 for Open Edit have been fully implemented, covering Backend Connection Handling & Interrupt Logic, Frontend UI Request Interrupt (Stop ⏹) & Connection Toasts, and full test suite verification.

---

## Files Modified & Summary of Changes

### 1. `open_edit/open_edit/serve/app.py`
- **`ws_chat` Refactoring**: Refactored the WebSocket chat endpoint so `run_agent_turn` executes as a background `asyncio.Task` (`current_turn_task`). A concurrent loop listens on `websocket.receive_text()`.
- **Cancel / Stop Handling**: When a `{"type": "cancel"}` or `{"type": "stop"}` JSON message is received, `_cancel_turn()` cancels the turn task cleanly (`task.cancel()`), awaits its cancellation, and emits `{"type": "cancelled"}` over WebSocket.
- **Client Disconnect Cleanup**: When a WebSocket client disconnects (`WebSocketDisconnect` or socket teardown), `_cancel_turn()` cancels the active background task cleanly in exception handlers and `finally:` block.
- **`GET /api/health` Endpoint**: Added health check endpoint returning `{"status": "ok"}`.
- **`put_llm_config` Exception Handling**: Expanded exception handling during config persistence to catch `(llm_config_mod.LLMConfigError, OSError, Exception)` and return clean HTTP 500 error responses with detail.
- **Async Event-Loop Safety**: Wrapped synchronous `available_models()` calls in `asyncio.to_thread` across `get_llm_config`, `put_llm_config`, and `get_provider_models`.

### 2. `open_edit/open_edit/serve/agent.py`
- **Cancellation Awareness**: Added `_is_cancelled()` helper checking `should_cancel` callback and `asyncio.current_task().cancelling() > 0`.
- **Turn Loop Interruption**: Checked `_is_cancelled()` at turn loop starts, during LLM streaming, and before tool executions.
- **`CancelledError` Propagation**: Ensured `asyncio.CancelledError` is re-raised immediately instead of caught as a generic exception.
- **Async Tool Execution**: Updated `_execute_tool` to handle coroutines/awaitables when invoking `_execute_trigger_render`.

### 3. `open_edit/open_edit/serve/tool_executor.py`
- **Async `execute_trigger_render`**: Refactored `execute_trigger_render` from synchronous `subprocess.run` to `asyncio.create_subprocess_exec`.
- **Process Cancellation**: Wrapped process execution in `try...except asyncio.CancelledError:`. Upon cancellation or timeout, terminates running render processes via `proc.kill()` and `await proc.wait()`.
- **Non-blocking Probe**: Wrapped `_probe_duration` in `asyncio.to_thread`.

### 4. `open_edit/open_edit/serve/cli_adapter.py`
- **Non-blocking Model Discovery**: Introduced `_run_subprocess_safe` helper that offloads synchronous `subprocess.run` calls in `_opencode_models_via_cli` and `_jcode_models_via_cli` to a thread pool executor when an event loop is running.

### 5. `open_edit/open_edit/serve/llm.py`
- **Transient Network Dropout Handling**: Added retry loop (up to 2 retries with exponential backoff) in `stream_chat` for `(ConnectionError, TimeoutError, OSError)` and transient API network dropouts.
- **Contract Coercion**: Restored `StreamEvent` TypedDict variants and `_coerce_event` contract helper.

### 6. `open_edit/open_edit/serve/static/index.html`
- **Topbar Stop Button**: Added `<button id="btn-topbar-stop" class="btn btn-secondary hidden" title="Interrupt request">Stop ⏹</button>` to `.topbar-right`.

### 7. `open_edit/open_edit/serve/static/app.js`
- **Send & Chat Enable Control**: Updated `handleSend()` to invoke `setChatEnabled(false)` when sending a message.
- **Dual Stop Button Toggle**: Updated `setChatEnabled(enabled)` to toggle visibility of both `#btn-stop` and `#btn-topbar-stop`.
- **Turn Interruption Logic**: Updated `cancelTurn()` to send `{"type": "cancel"}` over WebSocket, reset chat status, re-enable `#chat-input`, restore ready UI state, and display toast `"Turn interrupted by user"`.
- **Event Binding**: Wired `#btn-topbar-stop` to `cancelTurn()`.

### 8. `open_edit/open_edit/serve/static/js/ws.js`
- **Connection Drop Toast**: Added toast `"WebSocket connection dropped"` on `ws.onclose`.
- **Auto-reconnect Toast**: Added toast `"WebSocket reconnected"` on `ws.onopen` when reconnecting.

### 9. Test Updates & New Test Cases
- `open_edit/tests/test_serve_agent.py`: Updated `test_execute_trigger_render_*` to be async and mock `asyncio.create_subprocess_exec`.
- `open_edit/tests/test_tool_executor.py`: Updated `test_execute_trigger_render_missing_args` for async `execute_trigger_render`.
- `open_edit/tests/test_serve_ws.py`: Added `test_ws_chat_cancellation_message` and `test_ws_chat_stop_message`.
- `open_edit/tests/test_serve_llm_config_api.py`: Added `test_get_health_endpoint` and `test_put_llm_config_catches_oserror_and_returns_500`.

---

## Test Verification

Command:
```bash
python3 -m pytest open_edit/tests
```

Result:
```text
747 passed, 5 skipped, 1 warning in 35.65s (100% pass rate)
```
