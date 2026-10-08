# Architecture constraints

[BLUEPRINT.md](BLUEPRINT.md) documents the implementation. Future changes must
preserve these contracts:

- MCP remains the primary interface; startup needs no LLM SDK or API key.
- Tool schemas and dispatch have one source of truth in the kernel.
- Project paths come from `ProjectPaths`; graph edits commit atomically.
- Existing operation logs remain replayable and revisions reject stale writes.
- Render settings determine request identity; jobs and results persist.
- Cancellation and process shutdown reap local render workers.
- New graphics use HyperFrames; legacy Remotion graphs retain compatibility.
- Prompts load detailed guides on demand and page large read results.
- Optional chat and review presentation remain outside the editing kernel.
- Layer boundaries are covered by `tests/test_layering.py`.
