# M3 Task 4 Report

Implemented plane-aware preview chunk invalidation in
`open_edit/render/preview_invalidation.py`.

- Added canonical SHA-256 video/audio keys containing frame geometry, profile
  and content fingerprints, plane-filtered timeline slices, and localized
  operation semantics.
- Added operation-plane classification, conservative unknown/raw/free-form and
  missing-snapshot fallbacks, composition UID collection, and audio-only
  effect exclusion from video keys.
- Added requested-range dirty-window selection with interactive prioritization,
  neighboring dirty context, background coverage, and green-window skipping.
- Extended `tests/test_preview_invalidation.py` with audio-only, Remotion,
  unknown, snapshot, classification, key-filtering, and selection coverage.

Verification:

- `./.venv/bin/python -m pytest tests/test_preview_invalidation.py -q`
- `./.venv/bin/python -m pytest tests/test_preview_invalidation.py tests/test_preview_manifest.py tests/test_render -q`
- `./.venv/bin/python -m compileall -q open_edit/render/preview_invalidation.py tests/test_preview_invalidation.py`
- IDE diagnostics: no linter errors.
- Ruff was unavailable in the project virtual environment.

The full `./.venv/bin/python -m pytest -q` run reached 100% but had nine
pre-existing environment failures: seven CLI tests use the stale
`/home/ah64/.local/bin/open_edit` without the repository on `sys.path`, and two
focus-popup tests require missing `/home/ah64/OpenEditProjects/timeline-test`
fixtures. None touch the Task 4 files.
