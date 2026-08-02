# M3 Task 7 Report

Implemented the host `render_preview_chunks` worker and focused orchestration
tests.

- Loads the graph/timeline snapshot, computes frame-aligned dirty windows, and
  preserves same-range fallbacks while selected chunks bake.
- Uses the M1 `PreviewVideoRenderer` seam for video, independent preview-pipe
  audio rendering, cheap muxing, atomic cache commits, and manifest progress.
- Stops stale graph publications, cleans job-scoped temporary files, evicts
  after successful publication, and reports partial/graph-changed results.
- Avoids replaying historical operations when a prior timeline snapshot exists.

Verification:

- `.venv/bin/python -m pytest tests/test_preview_chunks.py -q` — passed.
- Preview contracts/cache/invalidation/pipe/frame-engine suite — 42 passed.
- `python -m compileall` for changed modules — passed.
# M3 Task 7 report

- Added the manifest/cache-backed `render_preview_chunks` worker.
- Added frame-aligned snapshot loading, dirty-window selection, plane rendering,
  fallback preservation, atomic publication, graph-stale aborts, cleanup, and
  structured progress results.
- Video work uses the M1 `PreviewVideoRenderer` seam; audio/mux work uses the
  existing preview pipe contract.
- Added fake-renderer/fake-runner coverage for reuse, fallbacks, and graph
  revision changes.
- The default renderer factory remains feature-gated until the host M1
  implementation is registered.
- Verification: `.venv/bin/python -m pytest` preview contract suite — 40 passed.
- Verification: focused render regression suite — 38 passed.
