# M3 Task 6 Report

Implemented bounded atomic preview-chunk storage in
`open_edit/render/preview_cache.py`.

- Added `manifest.json`, plane directories, temporary storage, and a durable
  artifact-ID index.
- Added content-hashed artifact commits and manifest replacement with
  validate-then-`os.replace()` publication.
- Added traversal-safe resolution, zero-byte/cap/free-space rejection, LRU
  and age pruning, atomic fallback clearing, and preview-only wipe.
- Added focused coverage for atomic publication, integrity/path safety,
  restartable index resolution, cap/expiry eviction, free-space rejection,
  and wipe isolation.

## Verification

- `.venv/bin/python -m pytest tests/test_preview_cache.py -q`
- `.venv/bin/python -m pytest tests/test_preview_cache.py tests/test_preview_manifest.py tests/test_render/test_cache.py tests/test_storage/test_cache_policy.py -q`
- `.venv/bin/python -m pytest tests/test_render -q`
- `.venv/bin/python -m compileall -q open_edit/render/preview_cache.py tests/test_preview_cache.py`
- IDE diagnostics: no linter errors for owned files
