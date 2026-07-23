# Empirical Verification Report — Challenger 2 (M2)

**Target Repository**: `/home/ah64/apps/mlt-pipeline/open_edit`  
**Execution Date**: 2026-07-22  
**Conclusion**: **CONFIRMED** (100% Pass Rate across non-skipped pytest suite; all target features empirically verified)

---

## Executive Summary

Challenger 2 conducted adversarial empirical verification of four target requirements in `open_edit`:
1. **Total pytest test suite execution & pass rate**: Executed `.venv/bin/pytest tests/`. Verified 754 total passed tests out of 754 non-skipped tests (**100.0% pass rate**; 5 skipped due to optional bwrap container environment requirements).
2. **Dev server health route (`GET /api/health`)**: Verified returns `HTTP 200 OK` with response JSON `{"status": "ok"}`.
3. **LLM config save error recovery (`PUT /api/projects/{id}/llm-config`)**: Verified catches `OSError` / file permission errors when persisting config and returns structured HTTP 500 JSON response `{"error": "failed to save LLM config: ..."}` without leaking unhandled exceptions or internal stack traces.
4. **Transient network dropout retry handling (`open_edit/serve/llm.py`)**: Verified `stream_chat` implements exponential backoff retry loop (`max_retries = 2`, attempts up to 3 times) for transient network dropouts (`ConnectionError`, `TimeoutError`, `OSError`, or API connection exceptions) when `events_yielded == 0`.

---

## Detailed Empirical Findings

### 1. Pytest Test Suite Execution
- **Command**: `.venv/bin/pytest tests/`
- **Output summary**:
  ```text
  754 passed, 5 skipped, 1 warning in 37.12s
  ```
- **Analysis**:
  - Total tests executed: 759
  - Passed: 754
  - Skipped: 5 (`tests/test_free_form_e2e.py` skipped because bubblewrap `bwrap` is not present in the execution sandbox)
  - Failed: 0
  - Pass rate of non-skipped tests: 100.0%

### 2. Dev Server Health Route (`GET /api/health`)
- **Location**: `open_edit/serve/app.py` (lines 368–371)
- **Code Inspection**:
  ```python
  @app.get("/api/health")
  async def get_health() -> dict[str, str]:
      """Health check endpoint returning {"status": "ok"}."""
      return {"status": "ok"}
  ```
- **Empirical Execution Result**: Tested via `fastapi.testclient.TestClient(app).get("/api/health")`.
  - HTTP Status: `200`
  - Response JSON: `{"status": "ok"}`

### 3. LLM Config Save Error Recovery (`PUT /api/projects/{id}/llm-config`)
- **Location**: `open_edit/serve/app.py` (lines 408–443) and exception handler (lines 200–207)
- **Code Inspection**:
  ```python
  @app.put("/api/projects/{project_id}/llm-config")
  async def put_llm_config(project_id: str, req: LLMConfigRequest) -> LLMConfigResponse:
      ...
      try:
          llm_config_mod.save_llm_config(project_path, cfg)
      except (llm_config_mod.LLMConfigError, OSError, Exception) as exc:
          raise HTTPException(status_code=500, detail=f"failed to save LLM config: {exc}") from exc
  ```
  ```python
  @app.exception_handler(HTTPException)
  async def _http_exception_handler(_request, exc: HTTPException) -> JSONResponse:
      msg = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
      return JSONResponse(
          status_code=exc.status_code,
          content={"error": msg},
      )
  ```
- **Empirical Execution Result**: Injected an `OSError("[Errno 13] Permission denied")` during `save_llm_config`.
  - HTTP Status: `500`
  - Response JSON: `{"error": "failed to save LLM config: [Errno 13] Permission denied: '/dummy/config.toml'"}`
  - Confirmed no raw tracebacks or 500 server crashes are leaked to the client.

### 4. Transient Network Dropout Retry Handling (`open_edit/serve/llm.py`)
- **Location**: `open_edit/serve/llm.py` (lines 188–242)
- **Code Inspection**:
  ```python
  max_retries = 2
  for attempt in range(max_retries + 1):
      events_yielded = 0
      try:
          ...
          break
      except (ConnectionError, TimeoutError, OSError) as exc:
          if attempt < max_retries and events_yielded == 0:
              await asyncio.sleep(0.2 * (2 ** attempt))
              continue
          yield {"type": "error", "message": f"{spec.name} network error: {exc}"}
          return
      except Exception as exc:
          exc_str = str(exc).lower()
          is_transient = (
              "connection" in exc_str or "timeout" in exc_str or "network" in exc_str or
              exc.__class__.__name__ in ("APIConnectionError", "NetworkError", "TimeoutException", "ConnectTimeout", "ReadTimeout")
          )
          if is_transient and attempt < max_retries and events_yielded == 0:
              await asyncio.sleep(0.2 * (2 ** attempt))
              continue
          ...
          yield {"type": "error", "message": f"{spec.name} provider error: {exc}"}
          return
  ```
- **Empirical Execution Result**:
  - Test 1 (Recovery): Simulated transient `ConnectionError` on attempt 1 and `TimeoutError` on attempt 2. `stream_chat` retried with exponential backoff (0.2s, 0.4s) and yielded the successful delta on attempt 3. `call_count == 3`.
  - Test 2 (Exhaustion): Simulated persistent `ConnectionError`. `stream_chat` attempted 3 times (initial + 2 retries) before yielding `{"type": "error", "message": "mock_transient_exhaust network error: Persistent network outage"}`.
  - Test 3 (Mid-stream fail): Simulated error after 1 event was yielded (`events_yielded == 1`). `stream_chat` did NOT retry (`call_count == 1`) and immediately yielded the error event to prevent duplication.

---

## Test Artifacts Created
- `/home/ah64/apps/mlt-pipeline/open_edit/tests/test_challenger_empirical.py` — Dedicated empirical test suite verifying health, LLM config OSError recovery, and LLM transient retry behavior.
