# M3 Task 3 Report

Implemented frame-aligned preview geometry and local timeline slicing.

- Added `ChunkWindow` and one-project-second default windows using integer
  project-frame arithmetic, including short final chunks and crop metadata.
- Added plane-aware `slice_timeline()` with half-open overlap handling,
  rebased clip/source coordinates, preserved effects, and cropped/rebased
  HTML and Remotion overlays.
- Documented that render planning and MLT emission consume pre-sliced local
  timelines without restoring project offsets.

Verification:

- `.venv/bin/python -m pytest tests/test_preview_invalidation.py tests/test_render_emitter.py tests/test_render/test_emitter.py -q`
- `.venv/bin/python -m pytest tests/test_render -q`
- `.venv/bin/python -m compileall -q open_edit/render/preview_invalidation.py open_edit/render/timeline_plan.py open_edit/render/emitter.py`

Both pytest commands and compilation passed. Ruff was not installed in the
project virtual environment; IDE diagnostics reported no linter errors.
