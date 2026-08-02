# M3 Task 9 Report

Exposed `preview-chunks` through the existing MCP and REST render contracts.

- Added schema-advertised ranges, media, and priority fields to
  `trigger_render`.
- Normalized and validated preview ranges, bounded request count, preserved
  quality/codec validation, and added the explicit
  `OPEN_EDIT_PREVIEW_CHUNKS=1` rollout gate.
- Forwarded preview parameters through the durable job service; `wait=true`
  returns the manifest-oriented worker result.
- Extended REST enqueue/poll models with preview fields and persisted result
  metadata while preserving HTTP 400 validation and 409 stale revisions.

Verification:

- `.venv/bin/python -m pytest tests/test_tool_registry.py tests/test_tool_executor.py tests/test_serve_render_jobs.py -q`
- `.venv/bin/python -m pytest tests/test_mcp_server.py tests/test_schema_validator.py tests/test_kernel_facade.py -q`

Both focused suites pass. The full repository run is otherwise green except
for the two unrelated missing external Remotion fixture failures recorded in
`task-8-report.md`.
