# M2 Source Proxies & QC Acceptance — 2026-08-03

Branch: `feat/render-m0-m1-remotion-engine`

M2 Tasks 1–7 landed; Task 8 verification performed by orchestrator after the
dedicated Task 8 subagent stalled.

## Result

Focused + broader render/storage/QC/serve matrix: **310 passed**  
(`tests/test_render/`, `tests/test_storage/`, `tests/test_qc/`, serve render/
project/asset-stream/asset-proxy jobs, layering, render_jobs).

`python -m compileall -q open_edit`: **ok**

CLI note: put `.venv/bin` first on `PATH` so tests do not hit the stale
`~/.local/bin/open_edit` import environment.

## Contracts verified

| Contract | Evidence |
|---|---|
| `final` / `review-artifact` → original source media | `source_media_policy_for(...) == "original"` |
| `proxy-edit` / `preview-chunk` → proxy when ready | `source_media_policy_for(...) == "proxy"` |
| Final guard rejects non-original policy | orchestrator/timeline_plan raise on final+proxy |
| Proxy QC skip on deliverable cache hit | `qc_policy("proxy", cache_hit=True) == "skip"` |
| Final QC still runs on cache hit | `qc_policy("final", cache_hit=True) == "run"` |
| Duration-budgeted / incomplete QC reports | Task 4 tests in `tests/test_qc/` |
| Cache policy never deletes source CAS/sidecars | `tests/test_storage/test_cache_policy.py` |
| Durable `generate-asset-proxy` jobs | `tests/test_asset_proxy_jobs.py`, serve tests |
| `f=rawvideo` pipe preserved | pipe_builder regressions green |
| MCP docs distinguish three products | `docs/MCP.md` (Task 7 `7cb0086`) |

## Commits (M2)

- `0b5fccd` source-proxy CAS generation
- `5b84e7d` durable generate-asset-proxy jobs
- `ac34cf8` emission profiles + final originals guard
- `6cd2983` unified cache eviction policy
- `570574f` duration-budgeted QC policy
- `afdbbb1` source-repair polish
- `7cb0086` MCP/docs for emission + QC budgets

## M3 handoff

Stable contracts for chunked preview:

1. Emission profile `preview-chunk` may resolve ready `proxy_hash` CAS.
2. Missing proxies enqueue via `AssetProxyJobService` without blocking plan build
   (explicit fallback reason).
3. `enforce_project_cache()` / `CacheSettings` own derived-byte caps.
4. QC policy API remains the single decision point for skip/light/full.

## Out of scope / known gaps

- Full Phase 1 A/B/C rebench with source-proxy diagnostics not re-run in this
  gate (M1 benches remain authoritative for Remotion wall clocks).
- Ruff binary may be absent from `.venv`; compileall used instead.
- Unrelated asset-indexer / graphify / `assets/` tree left unstaged.
