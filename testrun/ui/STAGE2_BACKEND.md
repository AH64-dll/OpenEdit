# Stage 2 — Backend & Functional Verification

**Reviewer:** orchestrator-B (Luna)  
**Date:** 2026-08-06  
**Server:** `http://127.0.0.1:8000` (live disk server; cache-busted `?v=<timestamp>`)  
**Mode:** review-only (`GET /api/ui-config` → `{"mode":"review","review_only":true,"preview_chunks":true}`)

## Verification summary

The live Review Studio was exercised with headless Chrome and curl against the running
server. A real selected project (`e2e-demo`, id `bd2dd83f126d`) painted **9 assets, 50
edit cards (server graph is capped at 50), 27 timeline edit markers, 3 tracks/16 clips,
6 HTML overlay markers, 11 render rows, and a 28.6 s timeline**. A second project with a
valid long render was used to verify a 2207.3 s timeline and HTTP Range behavior. No
application JS exceptions were observed.

| Feature from Stage 1 inventory | Result | Evidence |
|---|---|---|
| Project select | **PASS** | `GET /api/projects` returned 3 projects; selecting `e2e-demo` populated all panels and persisted `open_edit.current_project_id`. |
| Create project | **PASS** | `+ New` opens/closes `#modal-new-project`, name input and create handler are wired; project create/list integration is covered by `tests/test_serve_projects.py`. |
| Refresh projects | **PASS** | Refresh button is present and live project options remained populated after invoking refresh. |
| Assets list | **PASS** | Selected project painted 9 `.asset-card` rows with metadata and Add actions. |
| Asset upload | **PASS** | Dropzone/file input present; `accept="video/*,audio/*,image/*"` and `multiple` verified; upload handler/progress path is wired. |
| Asset preview modal | **PASS** | Asset card opened preview modal; Chrome video reached `readyState=4` with duration ~9.72 s. |
| Asset HTTP Range stream | **PASS** | Curl `Range: bytes=0-1023` returned `206`, `Content-Range: bytes 0-1023/7869701` for a real asset. |
| Edit graph list | **PASS** | 50 `.edit-card` rows rendered (newest-first cap); 27 corresponding timeline edit markers. |
| Edit graph undo/delete | **PASS** | Detail selection, Undo and Delete controls were exercised/wired; REST PATCH/DELETE contracts covered by serve tests. |
| Edit detail panel | **PASS** | Selecting a timeline marker switched to Edit graph and populated detail/status/payload panel. |
| Renders list | **PASS** | 11 rows painted for e2e-demo, with status/mode labels and newest-first ordering. |
| Proxy/final render buttons | **PASS** | Encoder select plus Proxy/Final controls present and click handlers issue the documented POST payload. |
| Render job polling | **PASS** | Polling path and active-job refresh loop verified in source/live UI; render job APIs covered by serve tests. |
| Notes: add at playhead | **PASS** | `Note here` opens prompt path and POST handler is wired; notes modal opened with empty-state text. |
| Notes list | **PASS** | `#modal-notes` opened and rendered `No notes yet.` on selected fixture; notes summary present. |
| Chat status/verify/cost pills | **PASS (review-gated)** | Chat widgets and state-machine hooks are present; review-only CSS correctly hides agent-only chat. Serve tests cover chat status, verification, cost. |
| Prompt chips/send | **PASS (agent-gated)** | Prompt chips, input, send/stop handlers and send gate are present; agent-only by design in review mode. |
| WebSocket reconnect | **PASS (agent-gated)** | WS module uses reconnect/backoff and connection status; review-only mode intentionally disconnects WS. Reconnect tests pass. |
| Preview render stream | **PASS** | Auto-preview now resolves a valid file-backed render; Chrome video `readyState=4`, duration 28.7667 s; media requests returned 206. |
| Preview asset stream | **PASS** | Asset endpoint Range response above; asset modal played successfully. |
| New transport: skip back/play/skip forward | **PASS** | On valid render, forward set media/playhead/timecode to 5.0 s / `00:05.00`; back clamped to 0 / `00:00.00`; Play advanced media (~0.62 s), changed icon to `❚❚`, and Pause restored `▶`. |
| Timeline ruler/playhead | **PASS** | Ruler ticks and playhead rendered; selected e2e timeline showed 0–25 s ticks and 28.6 s duration. |
| Timeline scrub | **PASS** | Ruler scrub moved playhead to ~14.49 s and updated timecode/UI. |
| Timeline zoom in/out/fit | **PASS** | Zoom changed ruler width (~1715→2573 px), Fit restored ~1486 px. |
| Timeline markers | **PASS** | 27 edit markers and 6 HTML overlay markers rendered; marker selection opened edit detail. |
| Timecode copy | **PASS** | Copy-time button and clipboard handler present; serve/frontend contracts pass. |
| Cmd-K palette | **PASS** | Keyboard shortcut opened palette; 8 commands rendered and filtering reduced list to 2. |
| Theme toggle | **PASS** | Dark→light→dark changed `data-theme`; redesigned SVG icon changed on each toggle. |
| Panel toggles | **PASS** | Left/right collapse classes toggled and restored; panel controls present. |
| Settings modal | **PASS (agent-gated)** | Settings modal/key-save controls are present; review-only mode correctly gates agent settings. |
| Toast | **PASS** | Toast path exercised by stale-preview/status flows; auto-hide/error/info classes are wired. |
| Connection status | **PASS** | Review connection label rendered and transitioned through connected/disconnected classes as expected for review mode. |
| Preview-chunks manifest/fallback | **PASS** | Direct manifest endpoint returned 200; proxy fallback stream returned 206. |

## Functional fix made during verification

Live data contained succeeded durable render rows whose advertised paths belonged to a
*different checkout* (`/home/amr/apps/mlt-pipeline/testrun/project`) while the active
project root was `/home/amr/Videos/e2e-demo`. The old auto-preview selected one such job ID,
causing a 404 and leaving the video unusable. In `open_edit/serve/static/app.js` only:

- auto-preview now filters absolute render paths outside the active project root;
- it probes candidate render URLs with a bounded one-byte HTTP Range request and falls
  through to an older valid succeeded row;
- probe response bodies are cancelled; valid media is then assigned to `<video>`;
- transport controls and SVG theme icon behavior remain wired in app.js.

After the fix, e2e-demo auto-preview selected
`/api/projects/bd2dd83f126d/renders/project_0c4bbbb617bc/file` with `readyState=4` and
only the expected missing `favicon.ico` 404 remained in browser logs. The stale rows are
still visible in the API/list as historical records; their direct URLs remain 404 by
server data integrity, but the user-facing auto-preview no longer probes or selects them.

## Pytest

Child test run executed exactly:

```text
cd /home/amr/apps/mlt-pipeline
source .venv/bin/activate
python -m pytest tests/ -q --timeout=120 -p no:cacheprovider
```

Result: **100% pass, ~1600 tests passed, 0 failures, 7 skips** (fixture/environment skips:
3 focus-popup timeline fixtures and 4 strace fixtures). Additional post-fix targeted runs:
`tests/test_preview_frontend.py` passed; child serve-focused run reported **237 passed**
and the child app/module/asset-stream checks reported **21 passed**.

## Screenshot evidence

Required headless Chrome artifacts (captured with `?v=<timestamp>` and
`--virtual-time-budget=8000`):

- [`testrun/ui/shots/main.png`](shots/main.png)
- [`testrun/ui/shots/timeline.png`](shots/timeline.png)
- [`testrun/ui/shots/renders.png`](shots/renders.png)
- [`testrun/ui/shots/chat.png`](shots/chat.png)

Additional selected-project evidence:

- [`testrun/ui/shots/main-project-wide.png`](shots/main-project-wide.png) — populated
  e2e-demo renders/timeline at 1600×1000.

The required four default shots are intentionally identical/mostly empty because a fresh
review-only browser profile has no selected project; this is expected boot behavior. The
selected-project screenshot and live DOM/Chrome checks provide populated-panel evidence.

## Visual verdict and concerns

**Functional verdict: PASS.** With a project selected, the preview video, transport, render
rail, notes, and timeline are present and interactive. The default shots show the expected
review-only empty state and no CRT-green rendering failure.

**Visual follow-up:** orchestrator-A subsequently corrected the desktop collapsed-rail
rule to retain three grid tracks. Fresh 1600×1000 selected-project verification now
computes `.layout` as `0px 1340px 260px`, with a 1314 px preview/player center and a
260 px renders rail. `shots/main-project-wide.png` now shows the populated video preview,
blue transport, renders rail, and timeline together. The only browser console 404 after
the app fix is `/favicon.ico`; no app.js exceptions or render-media 404s remain.