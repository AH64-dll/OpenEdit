# Detailed Exploration Report: LLM Provider Configuration & Network Connection Layer

**Repository Target**: `/home/ah64/apps/mlt-pipeline/open_edit`  
**Agent**: Explorer 2 (`teamwork_preview_explorer_m1_2`)  
**Date**: 2026-07-22  

---

## Executive Summary

Open Edit uses a hybrid LLM provider architecture supporting both Direct SDK streaming (`anthropic`, `openai`) and Subprocess CLI adapters (`pi`, `opencode`, `antigravity`, `jcode`). Configuration is managed per-project via `.open_edit/config.toml` with global environment variable and BYOK key store fallbacks (`~/.open_edit/keys.json`).

Our investigation revealed critical gaps in settings persistence error wrapping, synchronous event-loop blocking during CLI model discovery, lack of pre-save API key / model validation, absence of runtime LLM provider failover, and missing dev server health probe infrastructure.

---

## 1. LLM Provider Configuration Save Endpoints, Persistence, & Validation

### 1.1 Architecture & Endpoints

| Endpoint | Method | Path | Function & Scope |
| :--- | :--- | :--- | :--- |
| **Get Project LLM Config** | `GET` | `/api/projects/{project_id}/llm-config` | Loads per-project `config.toml`, returns active provider, model, `available_providers`, and `available_models`. |
| **Save Project LLM Config** | `PUT` | `/api/projects/{project_id}/llm-config` | Validates provider availability & non-empty model; writes `[llm]` table atomically to `.open_edit/config.toml`. |
| **Get Discovered Runtimes** | `GET` | `/api/runtimes` | Discovers CLI binaries across system `$PATH` and GUI fallback dirs (`~/.local/bin`, `/opt/homebrew/bin`, etc.). |
| **Get API Keys Status** | `GET` | `/api/settings/keys` | Returns masked API key summary (`has_key`, `masked_key`, `source`) across env vars and `~/.open_edit/keys.json`. |
| **Save API Key (BYOK)** | `PUT` | `/api/settings/keys` | Writes user key to `~/.open_edit/keys.json` with `0600` POSIX permissions. |
| **Get Provider Models** | `GET` | `/api/llm/providers/{provider}/models` | Queries CLI or SDK adapter for candidate models. |

### 1.2 Settings Persistence Mechanism

1. **Per-Project Config (`open_edit/serve/llm_config.py`)**:
   - Location: `<project_dir>/.open_edit/config.toml`
   - Schema:
     ```toml
     [llm]
     provider = "opencode"
     model = "opencode-go/minimax-m3"

     [llm.cli]
     # Adapter-specific overrides
     ```
   - Atomic Writes: `_atomic_write_text()` in `llm_config.py` uses `tempfile.mkstemp(prefix=".config.toml.", dir=...)` followed by `os.replace` to prevent corrupted partial reads.
   - Resolution Cascade:
     1. `<project_dir>/.open_edit/config.toml` `[llm]` section (highest priority).
     2. Environment variables: `OPEN_EDIT_LLM_PROVIDER` and `OPEN_EDIT_LLM_MODEL`.
     3. Hardcoded per-provider default models (`_PROVIDER_DEFAULT_MODEL` in `llm_config.py`).

2. **Global BYOK API Key Store (`open_edit/serve/runtimes/keys_store.py`)**:
   - Location: `~/.open_edit/keys.json`
   - File Security: Explicit `os.chmod(KEYS_FILE_PATH, 0o600)` on non-Windows platforms.
   - Key Retrieval Order (`_api_key()` in `llm.py`):
     1. `OPEN_EDIT_LLM_API_KEY`, `OPENCODE_API_KEY`, `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY` env vars.
     2. Provider-specific stored key in `~/.open_edit/keys.json`.
     3. Fallback stored keys across other providers (`anthropic`, `opencode`, `openai`, `antigravity`).

### 1.3 Validation Gaps & Issues

- **Availability Restriction Bottleneck**: `PUT /api/projects/{project_id}/llm-config` checks `req.provider in cli_adapter_mod.list_adapters()`. Because `list_adapters()` filters out adapters where `is_available()` returns `False` (e.g. SDK package missing or binary not detected), a user cannot save configuration for a provider prior to installing its binary, returning a `400 Bad Request` (`unknown provider`).
- **No Active Dry-Run / Validation**: Neither endpoint tests connection or API key validity upon save. Malformed or revoked keys are accepted silently during `PUT` calls and only fail during active chat streaming turns.
- **Unvalidated Model Strings**: Model strings are only checked for `not req.model or not req.model.strip()`. Any arbitrary string (e.g., `"invalid-model-foo"`) is written to disk without verification against `available_models()`.

---

## 2. Network Error Handling Layer

### 2.1 Error Handling Flow by Layer

```
[UI / JS Client] (api.js / ws.js)
       │
       ├─ REST Fetch Error ──► Toast Notification ("Failed to save LLM config: ...")
       └─ WS Connection Drop ──► Exponential Backoff Reconnect (1.5^n, max 10s)
       │
[FastAPI Server] (app.py)
       │
       ├─ HTTPException ──► JSONResponse {"error": "<message>"} (v1.4 contract)
       └─ Uncaught Exception ──► 500 JSONResponse {"error": "internal server error"}
       │
[Agent / LLM Runtime] (agent.py / llm.py)
       │
       ├─ Subprocess CLI Timeout ──► Process kill after timeout; yields error event
       └─ SDK Network Failure ──► Caught by stream_chat; yields {"type": "error", "message": "..."}
```

### 2.2 Detailed Behavior Across Connection Dropouts

1. **Subprocess CLI Adapters (`pi`, `opencode`, `antigravity`, `jcode`)**:
   - Driven by `_stream_cli()` in `open_edit/serve/llm.py`.
   - Timeout Enforcement: `_read_with_timeout()` enforces `adapter.default_timeout_s` (60s for `pi`/`anthropic`/`openai`, 120s for `opencode`/`antigravity`/`jcode`).
   - On Timeout: Process is killed (`proc.kill()`), and `_stream_cli` yields:
     - `{"type": "error", "message": "<adapter> timeout: timed out after Xs"}`
     - `{"type": "done", "stop_reason": "error"}`
2. **Direct SDK Adapters (`anthropic`, `openai`)**:
   - Network dropouts (DNS resolution failure, HTTP 502/503/504, 429 rate limit) during `client.messages.stream()` or chunk iteration raise SDK exceptions (`anthropic.APIConnectionError`, `openai.APIConnectionError`).
   - Caught by outer `try/except Exception as exc:` in `stream_chat()` (`llm.py` line 215), which prints traceback to `sys.stderr` and yields:
     - `{"type": "error", "message": f"{spec.name} provider error: {exc}"}`
3. **Dev Server Connectivity & Frontend State (`ws.js` / `app.js`)**:
   - `ws.js` maintains WS connection state (`disconnected` -> `connecting` -> `connected`).
   - Auto-reconnect uses exponential backoff capped at 10s (`Math.min(1000 * 1.5^(n-1), 10000)`).
   - Reconnection triggers automatically on:
     - `window.addEventListener('online', ...)`
     - `window.addEventListener('focus', ...)`
     - On user message send if socket is in non-connected state (`handleSend` in `app.js`).
   - **Missing Infrastructure**: The dev server lacks a dedicated REST health check / ping route (e.g. `GET /api/health`). The frontend relies solely on WebSocket `onclose` and individual `fetch` failures to infer backend availability.

---

## 3. Auto-Reconnect Fallback & Provider Failover Design

### 3.1 Design Objective

Enable zero-downtime LLM streaming by automatically retrying transient errors and failing over to secondary LLM providers when the primary provider encounters network dropouts, rate limits (429), or service outages (502/503).

### 3.2 System Architecture Diagram

```
                 +-----------------------------------+
                 |        run_agent_turn()           |
                 +-----------------------------------+
                                   │
                                   ▼
                 +-----------------------------------+
                 |    FailoverLLMDispatcher          |
                 +-----------------------------------+
                                   │
                 +-----------------+-----------------+
                 │                                   │
                 ▼                                   ▼
    [Primary: anthropic]               [Fallback 1: opencode]
                 │                                   │
       (Transient Error: 503)             (Success Stream)
                 │                                   │
                 └──────────────► Switch ────────────┘
```

### 3.3 Integration Steps into Backend Runtime

1. **Config Extension (`llm_config.py`)**:
   - Add `fallback_providers: list[ProviderName] = Field(default_factory=list)` to `LLMConfig`.
   - Update `config.toml` schema:
     ```toml
     [llm]
     provider = "anthropic"
     model = "claude-sonnet-4-5"
     fallbacks = ["opencode", "openai"]
     ```

2. **Transient Error Classifier (`llm.py`)**:
   - Implement `is_transient_error(exc: Exception | str) -> bool`:
     - Returns `True` for network timeouts, DNS failures, HTTP 429 (Rate Limit), HTTP 502/503/504 (Server Error), `APIConnectionError`, `subprocess.TimeoutExpired`.
     - Returns `False` for HTTP 401 (Unauthorized), `InvalidModelError`, syntax errors.

3. **Resilient Streaming Generator (`llm.py`)**:
   - Wrap `stream_chat` in a retry-and-failover loop:
     ```python
     async def resilient_stream_chat(
         project_path: Path,
         messages: list[dict],
         tools: list[dict],
         system: str,
         session_id: str | None = None,
     ) -> AsyncIterator[StreamEvent]:
         cfg = load_llm_config(project_path)
         providers_to_try = [cfg.provider] + getattr(cfg, "fallbacks", [])
         
         for idx, provider in enumerate(providers_to_try):
             saw_token = False
             try:
                 async for event in stream_chat_provider(provider, ...):
                     if event["type"] == "text_delta":
                         saw_token = True
                     if event["type"] == "error" and is_transient_error(event["message"]):
                         raise TransientLLMError(event["message"])
                     yield event
                 return
             except TransientLLMError as err:
                 if saw_token:
                     # Mid-stream failure: emit clear notification before switching or ending
                     yield {"type": "error", "message": f"{provider} connection dropped mid-turn: {err}"}
                     return
                 if idx == len(providers_to_try) - 1:
                     yield {"type": "error", "message": f"All providers failed. Last error from {provider}: {err}"}
                     return
                 next_provider = providers_to_try[idx + 1]
                 yield {
                     "type": "text_delta",
                     "text": f"\n\n*[System: {provider} unavailable ({err}). Failing over to {next_provider}...]*\n\n"
                 }
     ```

4. **Dev Server Health Check Endpoint (`app.py`)**:
   - Add `GET /api/health` returning `{"status": "ok", "timestamp": float}`.
   - Frontend polls `/api/health` during WS disconnection to distinguish server process crash vs network interface down.

---

## 4. Code Locations Raising or Leaking Unhandled Errors

### Location 1: Unhandled File Write Exceptions in Config Save Route
- **File**: `open_edit/serve/app.py` (lines 427–429) & `open_edit/serve/llm_config.py` (lines 155–173)
- **Issue**: `put_llm_config()` only catches `llm_config_mod.LLMConfigError`. If `save_llm_config()` raises `PermissionError` or `OSError` (e.g. read-only filesystem or restricted permissions on `.open_edit/config.toml`), the exception is uncaught by the route, causing the global exception handler (`_unhandled_exception_handler`) to return generic 500 `"internal server error"`.
- **Fix**: Catch `(llm_config_mod.LLMConfigError, OSError)` in `put_llm_config()` and raise `HTTPException(status_code=500, detail=f"failed to save LLM config: {exc}")`.

### Location 2: Main Event-Loop Blocking via Synchronous Subprocess Calls
- **File**: `open_edit/serve/cli_adapter.py` (lines 72–77 & 363–368)
- **Issue**: `_opencode_models_via_cli()` and `_jcode_models_via_cli()` invoke `subprocess.run([...], timeout=10/15)` directly inside synchronous functions called by async endpoints (`GET/PUT /api/projects/{id}/llm-config` and `GET /api/llm/providers/{provider}/models`). If the CLI binary hangs or experiences network delay during model listing, it blocks the main FastAPI asyncio event loop for 10–15 seconds, freezing all concurrent API and WebSocket operations for all users.
- **Fix**: Wrap model discovery calls in `asyncio.to_thread(_opencode_models_via_cli)` or perform non-blocking async subprocess execution (`asyncio.create_subprocess_exec`).

### Location 3: Exception Wrapping in Agent Turn Stream Handlers
- **File**: `open_edit/serve/agent.py` (lines 728–751)
- **Issue**: When `stream_chat` encounters an unhandled python exception, `run_agent_turn` catches `Exception as exc` and formats the error message as `f"LLM stream error: {exc}"`. This leaks raw Python exception names (e.g., `httpx.ConnectError: [Errno 111] Connection refused`) directly to the user UI.
- **Fix**: Format network/SDK errors into user-friendly messages (e.g., `"Unable to connect to Anthropic API. Please check your network connection and API key."`) while logging the raw traceback to `sys.stderr`.

### Location 4: Key Store File Write Permission Errors
- **File**: `open_edit/serve/runtimes/keys_store.py` (lines 48–55) & `open_edit/serve/app.py` (lines 458–471)
- **Issue**: `save_stored_key` in `keys_store.py` performs direct `write_text` and `os.chmod` on `~/.open_edit/keys.json` without `try/except`. If `~/.open_edit` is read-only or owned by another user, `PUT /api/settings/keys` raises an uncaught `PermissionError`, returning a generic 500 error without actionable feedback to the UI.
- **Fix**: Wrap `save_stored_key` file operations in `try/except OSError` and raise a custom `KeyStoreError` or handle cleanly in `app.py`.
