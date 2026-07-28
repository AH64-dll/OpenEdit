# Delivery Loop — Grok Orchestrator

You are the **orchestrator** (Grok). Workers are **Composer** sub-agents.
The loop does **not** stop until you certify the product **100% delivery-ready**.

## Scope (do NOT change UI style)

- Fix bugs only: timeline, render, review UI, MCP, kernel paths.
- No visual redesign; keep existing CSS/theme.
- Remove dead code and confusing error toasts where safe.

## Delivery checklist (all must pass)

1. **Review UI** (`open_edit serve --review-only`)
   - No WebSocket / LLM error toasts in review mode
   - Assets panel collapsible; preview unobstructed
   - Timeline seek + scrub on long edits; auto-fit works
   - Render proxy/final: enqueue, poll, list status, stream preview MP4

2. **Render pipeline**
   - Proxy/final produce full-duration MP4 (not 0.04s stubs)
   - Empty `video_graphics` track must not break melt composite
   - Job status transitions: queued → running → succeeded/failed

3. **MCP + project**
   - `edit_project`, `query_project`, `trigger_render` work on pinned project
   - `ingest_local` with allowlist

4. **Tests**
   - `pytest open_edit/tests/test_review_ui.py open_edit/tests/test_render_service.py open_edit/tests/test_remotion_proxy_golden.py` green

## Worker protocol

1. Grok assigns **one** focused task per worker (file/area + acceptance criteria).
2. Worker implements + runs targeted tests; returns evidence (command output, log lines).
3. Grok reviews; if not 100%, assigns next task. Repeat.
4. Grok writes `PROGRESS.md` with pass/fail per checklist item.

## Current known issues (seed list)

- [fixed?] Review mode WS reconnect spam → "Connection lost — giving up"
- [fixed?] `selectProject` called `connectWS` + `loadLLMConfig` in review mode
- [fixed?] Render list hid queued/running jobs → looked like button did nothing
- [ ] 32 min proxy render: confirm UI shows progress until complete
- [ ] Audit remaining agent-only UI leaks in review mode
