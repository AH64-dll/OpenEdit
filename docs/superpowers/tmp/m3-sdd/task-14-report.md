# M3 Task 14 Report

Documented the finalized MCP/REST `preview-chunks` job surface without
touching Review Studio UI Tasks 11–13.

- Synchronized canonical and packaged MCP playbooks, references, and tool
  surface docs.
- Documented ranges/media/priority, the `OPEN_EDIT_PREVIEW_CHUNKS=1` gate,
  durable polling, manifest statuses, same-range/stale-proxy fallbacks,
  artifact routes, cache controls, and the M3 sequential/MSE/M4 boundaries.
- Clarified the three products: `preview-chunks` background cache, `proxy`
  whole-file review artifact, and `final` delivery; free-form never renders
  preview media.
- Added documentation-contract tests in `test_mcp_server.py` and
  `test_tool_contract.py`.

Verification:

- `.venv/bin/python -m pytest tests/test_mcp_server.py tests/test_tool_contract.py -q` — 24 passed.
- `git diff --check` and IDE lints — clean.
