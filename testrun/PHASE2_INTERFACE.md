# PHASE 2 INTERFACE CONTRACT (coordinator-defined; read before editing)

Repo: /home/amr/apps/mlt-pipeline (venv: source .venv/bin/activate; python 3.14).
Suite: `python -m pytest tests/ -q --timeout=120 -p no:cacheprovider` (note: pytest 9 -q suppresses the summary line; count dots, expect ~1474; FAILED lines matter).

## File ownership (NO CROSS-EDITING; if you must touch another agent's file, write a NOTE in testrun/PHASE2_INTERFACE.md instead)
- A (proxy generation): open_edit/render/source_proxy.py, open_edit/kernel/asset_proxy_jobs.py, open_edit/storage/assets.py, open_edit/serve/routers/assets.py, open_edit/serve/__init__.py or app.py (only to add a background runner), open_edit/cli.py (only to add an asset-proxy CLI command).
- B (proxy consumption): open_edit/render/timeline_plan.py, open_edit/render/orchestrator.py, tests/test_render/* (policy tests).
- C (chunk size): open_edit/render/preview_chunks.py (ONLY the _chunk_size function), open_edit/render/preview_invalidation.py (ONLY make_chunk_windows + its docstring/tests).
- D (parallel bake): open_edit/render/preview_chunks.py (ONLY the serial bake loop inside render_preview_chunks + _bake_chunk signature), open_edit/kernel/tool_executor.py (ONLY if a concurrency env read belongs there).

## Key facts (verified by coordinator)
- _EMISSION_POLICY in timeline_plan.py: {"final": "original", "review-artifact": "original", "proxy-edit": "proxy", "preview-chunk": "proxy"}.
- _resolve_asset_paths_with_diagnostics (timeline_plan.py) already: uses proxy when policy=proxy AND proxy_status==ready AND proxy bytes exist; otherwise falls back to original and queues proxy generation (_enqueue_missing_source_proxy -> asset_proxy_jobs).
- generate_asset_proxy (source_proxy.py) is complete: 360p libx264 veryfast crf28, CAS + meta.json proxy_hash/proxy_status/proxy_profile. Default profile DEFAULT_SOURCE_PROXY_PROFILE.
- make_chunk_windows (preview_invalidation.py): default chunk = 1s (chunk_frames = fps). preview_chunks._chunk_size(fps_num, fps_den, params) is the real decision point.
- render_preview_chunks (preview_chunks.py): serial `for index in selected: _check_graph(...); _bake_chunk(...)` loop. _bake_chunk mutates failed_chunks (list), metrics (dict-like _PreviewDiagnostics), writes per-chunk artifacts under cache.
- Existing tests: tests/test_render/test_preview_chunks.py, test_preview_invalidation.py, test_source_proxy*, test_timeline_plan*.

## Safety rules (user: "if it will corrupt the files don't")
- NEVER modify /home/amr/Videos/video project files. Scratch projects live in /home/amr/apps/mlt-pipeline/testrun/phase2_scratch*.
- Originals in CAS are immutable; proxies are NEW CAS objects (additive).
- Each agent: run the targeted tests for your area before and after; never leave the suite red for files you own.
