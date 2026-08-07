# M2 Task 5-CORE Report

Status: complete within the delegated CORE scope.

Implemented:

- Added `CacheSettings.from_env()` with documented byte/age/free-space defaults
  and safe fallback for malformed or non-positive environment values.
- Added `CacheEvictionReport` and `enforce_project_cache()`.
- Added reference-aware source-proxy scanning that protects canonical CAS bytes
  and sidecars, clears `proxy_hash` metadata before deleting a derived proxy,
  and never classifies a CAS file as disposable by filename alone.
- Added stale/LRU eviction for render and Remotion derivatives, newest
  mode-aware deliverable protection, active-path protection, orphan temporary
  cleanup, and best-effort disk-pressure cleanup with warnings.
- Extended `RenderCache.put()` with optional `cache_class`/`mode` metadata and
  hardened `remove()` sidecar cleanup.

Verification:

- `tests/test_storage/test_cache_policy.py tests/test_render/test_cache.py tests/test_remotion_ir_materialize.py tests/test_render/test_orchestrator.py`: 50 passed.
- `tests/test_storage/ tests/test_render/ tests/test_remotion_ir_materialize.py`: 213 passed.
- `compileall` and IDE lint diagnostics passed.
- Ruff was unavailable at `.venv/bin/ruff`.

Scope note: orchestrator, materialize, timeline-plan, source-proxy,
asset-proxy-job, QC, and `.env.example` wiring remain intentionally deferred
to the owning integration lanes.
