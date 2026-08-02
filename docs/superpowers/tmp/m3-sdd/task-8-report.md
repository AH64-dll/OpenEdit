# M3 Task 8 Report

Implemented durable `preview-chunks` scheduling and the internal worker CLI.

- Extended the SQLite render-job mode constraint and legacy migration to retain
  existing job data, including `params_json`.
- Added exact-parameter coalescing for preview jobs, preview progress/result
  persistence, QC bypass, and the existing process-group subprocess path.
- Added `open_edit preview-chunks --job-id ... --json`; it loads the durable
  row and calls the lazy `render_preview_chunks` worker seam.
- Kept whole-file render history separate from preview manifests and rejected
  manifest paths as MP4 render files.

Verification:

- `.venv/bin/python -m pytest tests/test_render_jobs.py tests/test_serve_render_jobs.py tests/test_preview_chunks.py -q`
- `.venv/bin/python -m pytest tests/test_render/test_orchestrator.py -q`
- `.venv/bin/python -m compileall -q` on all changed Task 8/9 modules.

The repository-wide suite has two unrelated failures in
`tests/test_focus_popup_layout.py` because the external
`/home/ah64/OpenEditProjects/timeline-test` Remotion files are absent.
