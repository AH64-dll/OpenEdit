# Task 2 Report — Stage timing and artifact names

## Status

Implemented the Wave A Task 2 render diagnostics and naming changes.

## Implementation

- Instrumented `render_project()` around timeline derivation, profile/content
  fingerprint plus cache lookup, Remotion materialization, render-plan
  construction, MLT emission, pipe execution, and source repair.
- Mapped `PipeResult.audio_elapsed_sec`, `melt_elapsed_sec`, and
  `ffmpeg_elapsed_sec` to canonical `melt_audio`, `melt_video`, and
  `ffmpeg_encode` entries while preserving `melt`, `audio`, and `ffmpeg`
  aliases.
- Ensured every canonical stage is present; stages not reached are explicit
  `skipped` entries with reasons. Product metadata remains stable on success
  and failure paths.
- Added QC stage timing to the durable job service and human-readable CLI
  path. The JSON CLI path leaves QC for the job service, avoiding duplicate
  work.
- Reconciled Review Studio and MCP documentation copy with the 640×360
  full-timeline review artifact, source media fallback, and future timeline
  preview chunks vocabulary.
- `melt_runner.py` already exposed the required `PipeResult` timing fields;
  no behavior change was needed there.

## TDD and verification

- RED: the new canonical-stage, QC-stage, and copy tests failed for the
  expected missing-stage/stale-label reasons.
- GREEN: `.venv/bin/python -m pytest -q tests/test_render/test_orchestrator.py tests/test_render_jobs.py tests/test_review_ui.py`
  — 18 passed.
- Render regression: `.venv/bin/python -m pytest -q tests/test_render` —
  86 passed.
- Stale-copy search for `Proxy 720p`, `Render Proxy Video (540p)`, and
  `Render proxy (720p)` returned no matches.
- Python compilation, diff whitespace checks, and IDE lint diagnostics passed.

## Concerns

The broader CLI subprocess tests remain blocked by the pre-existing
environment issue where `/home/ah64/.local/bin/open_edit` cannot import this
checkout (`ModuleNotFoundError: open_edit`); this is the same issue documented
in Task 1’s report. Unrelated working-tree changes and asset/docs files were
not staged.
