# M3 Task 16 Report

Completed rollout verification for the MCP/host-worker path. Review Studio UI
Tasks 11–13 remain out of scope.

Verification:

- M3 preview, render-job, serve-route, cache, manifest, invalidation, pipe,
  frontend, and sandbox focus suites passed.
- M1/M2 gates passed: preview frame-engine contract, Remotion frame-engine
  reuse/dirty coverage, render-cache eviction, source-proxy coverage, and
  sandbox bridge coverage.
- `python -m compileall -q open_edit tests`, changed-file IDE lints, targeted
  Ruff, and `git diff --check` passed.
- The full suite reached 100%; two unrelated `test_focus_popup_layout.py`
  tests fail because `/home/ah64/OpenEditProjects/timeline-test` is absent.
  Five existing environment/fixture tests remain skipped.
- The configured Ruff command still reports 21 pre-existing findings in
  `render_jobs.py`, `tool_executor.py`, `tool_registry.py`,
  `preview_cache.py`, and `preview_invalidation.py`; the changed preview
  worker and acceptance tests are clean. `mypy` is not installed.

Manual/MCP note:

- The pinned MCP project was queried with `list_assets` and returned no
  assets, so the destructive manual edit/restart/cache-wipe smoke path was
  not run against that empty project. The installed `melt`/`ffmpeg`/`ffprobe`
  short real-host fixture passed instead.
- `mode=proxy` remains a whole-file artifact; preview chunks stay feature
  gated, use atomic cache publication, preserve rawvideo pipe behavior, and
  do not add a live MLT SDL/OpenGL consumer. Free-form sandbox coverage
  remains unchanged.
