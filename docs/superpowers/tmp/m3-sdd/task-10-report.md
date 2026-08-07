# M3 Task 10 Report

Implemented project-scoped preview-chunk HTTP routes:

- Added manifest, indexed artifact-file, and preview-only wipe endpoints.
- Added artifact URL projection, active preview-job lookup, and safe proxy fallback.
- Enforced cache-root/path safety and `Accept-Ranges: bytes` file responses.
- Added `OPEN_EDIT_AUTO_PREVIEW` and `OPEN_EDIT_PREVIEW_CHUNKS` rollout helpers.
- Exposed `auto_preview` and `preview_chunks` through `/api/ui-config`.

Verification:

- `.venv/bin/python -m pytest tests/test_serve_preview_chunks.py tests/test_serve_env.py tests/test_review_ui.py tests/test_preview_cache.py tests/test_preview_manifest.py tests/test_preview_invalidation.py tests/test_preview_pipe.py -q` — passed.
- `ruff check` and targeted `compileall` — passed.
- The full render-job focus still requires M3 Tasks 8–9 (`preview-chunks` mode/schema and REST enqueue) and was not changed per ownership.
