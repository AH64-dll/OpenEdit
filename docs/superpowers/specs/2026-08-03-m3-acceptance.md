# M3 Chunked Timeline Preview Acceptance

Date: 2026-08-03
Scope: MCP/REST host-worker preview chunks and rollout verification
Status: automated acceptance passed; manual MCP smoke is pending a media-backed
project. Review Studio UI Tasks 11–13 are intentionally excluded.

## Product boundaries

- `mode=proxy` remains the complete whole-file review artifact.
- `mode=preview-chunks` is a separately gated background range cache.
- `final` remains the delivery render.
- Free-form IR stays sandboxed and never renders preview media.
- No live MLT SDL/OpenGL consumer is introduced.

The preview-chunk API remains behind `OPEN_EDIT_PREVIEW_CHUNKS=1`. When the
gate is disabled, the route returns a clear feature-disabled response while
proxy and final rendering remain available. Jobs return a durable job ID and
the worker publishes a schema-versioned manifest atomically.

## Acceptance criteria

### Job and manifest contract

- A preview-chunk request is non-blocking by default and can be polled by its
  durable job ID.
- The manifest exposes red, yellow, and green chunk state, frame-aligned
  ranges, independently addressable video/audio/playback artifacts, and
  `graph_changed`/`partial` state.
- A one-second chunk is a valid selection unit; unchanged green chunks remain
  seekable while dirty ranges are baked.
- Exact-range prior artifacts and the whole-file proxy remain valid fallbacks
  while a new chunk is unavailable.

### Invalidation and cache safety

- A Remotion edit invalidates only its overlapping video zone and preserves
  unaffected green chunks.
- Audio gain/silence/normalization changes do not change unchanged video
  artifact keys; audio and playback artifacts may change.
- Cache writes use temporary files and atomic publication. Cap, eviction,
  expiry, path-safety, recovery, and wipe behavior remain covered.
- Clearing preview cache files does not alter the edit graph or proxy artifact.

### Diagnostics

Every worker result contains bounded, browser-safe diagnostics with:

- per-job total, selected, processed, skipped-green, and failed counts;
- selected start/end ranges;
- video, audio, and mux elapsed seconds;
- video, audio, and mux bytes written;
- aggregate and per-plane cache hits/misses;
- eviction counts and removed bytes;
- `graph_changed` and `partial` flags.

Worker logs carry the same summary fields. The frontend exposes only formatted
counts, ranges, timings, byte totals, cache totals, evictions, and state
labels; arbitrary nested values and absolute source paths are not browser
visible.

## Verification evidence

Passed focused commands:

```text
PYTHONPATH=/home/ah64/apps/mlt-pipeline .venv/bin/pytest -q \
  tests/test_preview_chunks.py tests/test_serve_preview_chunks.py \
  tests/test_e2e_render.py
PYTHONPATH=/home/ah64/apps/mlt-pipeline .venv/bin/pytest -q \
  tests/test_preview_chunks.py tests/test_preview_frontend.py \
  tests/test_render_jobs.py tests/test_serve_render_jobs.py
PYTHONPATH=/home/ah64/apps/mlt-pipeline .venv/bin/pytest -q \
  tests/test_preview_frame_engine_contract.py tests/test_remotion_frame_engine.py \
  tests/test_render/test_remotion_dirty.py tests/test_render/test_cache.py \
  tests/test_render/test_source_proxy.py tests/test_preview_pipe.py \
  tests/test_sandbox_bridge.py
python -m compileall -q open_edit tests
```

The short real-host fixture ran because `melt`, `ffmpeg`, and `ffprobe` are
installed. The full suite reached 100%; two unrelated focus-popup tests fail
only because the external `/home/ah64/OpenEditProjects/timeline-test`
fixture is absent, and five existing environment/observation tests skip.
The configured Ruff command reports 21 pre-existing findings outside the
changed worker/tests; targeted Ruff and IDE diagnostics for changed files are
clean. `mypy` is unavailable in the environment.

## Manual smoke and rollback

The pinned MCP project was checked with `query_project(list_assets)` and has
no assets, so the Review Studio render/edit/restart/cache-wipe smoke path was
not run against that empty project. It must be completed with a short
media-backed project before enabling the feature by default:

1. Start Review Studio review-only and load the project.
2. Render proxy, then a 4–8 second chunk window.
3. Observe red → yellow → green transitions and sequential playback.
4. Seek into a red chunk and confirm whole-file proxy fallback labeling.
5. Apply one Remotion edit and one audio-gain edit; verify plane-specific
   invalidation.
6. Restart the server and verify manifest/job recovery.
7. Clear chunk cache and verify the edit graph and proxy remain.

Rollback is `OPEN_EDIT_PREVIEW_CHUNKS=0` (or unset), followed by the preview
cache wipe route if needed. This leaves proxy/final artifacts and the edit
graph untouched.
