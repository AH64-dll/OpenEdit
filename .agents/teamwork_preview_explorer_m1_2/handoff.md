# Handoff Report: LLM Provider Config & Network Layer Analysis

## 1. Observation

Direct observations made during inspection of `/home/ah64/apps/mlt-pipeline/open_edit`:

1. **Config Save Endpoint (`open_edit/serve/app.py`:402-435)**:
   - `PUT /api/projects/{project_id}/llm-config` validates provider against `cli_adapter_mod.list_adapters()` and model against non-empty string `not req.model or not req.model.strip()`.
   - `llm_config_mod.save_llm_config(project_path, cfg)` writes to `<project>/.open_edit/config.toml` using atomic temp file replacement.
   - `llm_config_mod.LLMConfigError` is caught, but raw `OSError` / `PermissionError` during file write is uncaught and bubbles to global exception handler (`app.py`:209-227), returning generic `500 {"error": "internal server error"}`.

2. **Synchronous Subprocess Event-Loop Blocking (`open_edit/serve/cli_adapter.py`:57-91 & 351-380)**:
   - `_opencode_models_via_cli()` runs `subprocess.run([bin_path, "models"], capture_output=True, text=True, timeout=10, check=False)`.
   - Called directly inside synchronous adapter methods `available_models()` invoked by `async def get_llm_config` and `async def put_llm_config` (`app.py`:393, 434) on the main asyncio thread.

3. **Validation Limitations**:
   - `list_adapters()` (`cli_adapter.py`:438-445) only returns adapters where `is_available()` returns `True`. Saving a provider that is uninstalled or missing binary/SDK returns `400 Bad Request` (`unknown provider`).
   - No dry-run API key check or model verification against remote endpoints is executed during `PUT /api/projects/{project_id}/llm-config` or `PUT /api/settings/keys`.

4. **Network Error Handling & Streaming (`open_edit/serve/llm.py`:193-222, `open_edit/serve/agent.py`:728-751)**:
   - `stream_chat` catches `Exception` during streaming and yields `{"type": "error", "message": f"{spec.name} provider error: {exc}"}`.
   - `run_agent_turn` in `agent.py` catches `Exception` and yields `{"type": "error", "message": f"LLM stream error: {exc}"}`.
   - CLI adapters enforce process timeouts via `_read_with_timeout()` (`llm.py`:502-513), killing subprocess on timeout.

5. **Dev Server Connectivity & Reconnect (`open_edit/serve/static/js/ws.js`:40-98, `app.js`:867-878)**:
   - WS client implements exponential backoff reconnection (`Math.min(1000 * 1.5^(attempts-1), 10000)`).
   - Reconnects on `online` and `focus` events and failed message sends.
   - No backend health check route (`/api/health`) exists to probe REST availability independently of WebSocket state.

---

## 2. Logic Chain

1. **From Observation 1**: Because `put_llm_config` in `app.py` catches only `LLMConfigError`, file system write errors (`PermissionError`, disk full `OSError`) escape the local try/except block. In FastAPI, uncaught exceptions hit `_unhandled_exception_handler`, which logs to stderr and returns `500 {"error": "internal server error"}`. **Logic**: The client receives a generic error rather than actionable notification that project configuration persistence failed due to file permissions.

2. **From Observation 2**: In Python `asyncio`, running blocking synchronous calls like `subprocess.run()` inside an `async def` route without `asyncio.to_thread` blocks the main thread event loop. **Logic**: Calling `GET` or `PUT /api/projects/{id}/llm-config` when `opencode` or `jcode` CLI binary delays causes the entire server (all HTTP routes and WebSocket message processing) to freeze for up to 10-15 seconds.

3. **From Observation 3**: Provider validation relies strictly on `is_available()`, while model validation only checks string non-emptiness. **Logic**: Users cannot pre-configure a provider before installing its CLI, while invalid model names (e.g. typos) are saved to `config.toml` without early error feedback.

4. **From Observation 4 & 5**: The current agent runtime does not feature provider failover or auto-reconnect fallback chains during streaming dropouts. **Logic**: Any transient network dropout or rate limit (429/503) immediately terminates the user's turn with an error, requiring manual user intervention to switch providers or resubmit.

---

## 3. Caveats

- Investigation was performed strictly via static code analysis (read-only mode).
- Real network failure scenarios (e.g. actual HTTP 503 from Anthropic/OpenAI or CLI process hangs) were analyzed based on control flow and exception handling paths in source code rather than live network fault injection.

---

## 4. Conclusion

The Open Edit LLM provider configuration and network layer is functional for baseline operations but lacks resilience against transient network failures and contains specific unhandled exception & blocking flaws:
1. File write permissions errors during config/key saves are not caught locally, leaking generic 500 errors.
2. Synchronous `subprocess.run` calls during model discovery block the asyncio event loop.
3. Model validation and API key dry-run verification are missing prior to config persistence.
4. Auto-reconnect exists only at the WebSocket frontend client; backend runtime lacks provider failover chains for transient outages.

---

## 5. Verification Method

To independently verify these findings:

1. **Verify Test Suite**:
   Run pytest on the LLM config and provider test suites:
   ```bash
   pytest tests/test_llm_config.py tests/test_serve_llm_config_api.py tests/test_serve_errors.py tests/test_providers.py
   ```

2. **Inspect Code Files**:
   - `open_edit/serve/app.py` lines 402–435 (`put_llm_config` exception handling)
   - `open_edit/serve/cli_adapter.py` lines 57–91 (`_opencode_models_via_cli` blocking subprocess)
   - `open_edit/serve/llm.py` lines 183–223 (`stream_chat` error catching and fallback logic)
   - `open_edit/serve/agent.py` lines 728–751 (`run_agent_turn` exception handling)

3. **Invalidation Conditions**:
   - The findings regarding event-loop blocking are invalidated if `available_models()` is refactored to execute via `asyncio.to_thread` or `asyncio.create_subprocess_exec`.
   - The findings regarding unhandled write errors are invalidated if `put_llm_config` is updated to catch `(LLMConfigError, OSError)`.
