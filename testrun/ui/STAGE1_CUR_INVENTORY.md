# STAGE 1 (cur-1) — Current Review Studio Frontend: Inventory & Features

**Author:** Study agent (cur-1) · **Date:** 2026-08 (session) · **Sources read directly:**
`open_edit/serve/static/index.html`, `open_edit/serve/static/app.js`,
`open_edit/serve/static/style.css`, `open_edit/serve/static/js/{state,dom,api,assets,chat,ws}.js`,
`open_edit/serve/app.py`, `open_edit/serve/routers/{projects,renders,assets,config,ops,preview_chunks}.py`,
`open_edit/serve/projects.py`, `tests/_node_harness.py`, frontend-pinning tests.
Live server verified: `curl /` → 200; `/api/ui-config` → `{"mode":"review","review_only":true,...}`
(server runs as `.venv/bin/python -m open_edit.cli serve --review-only --port 8000`, PID 8262).

---

## 0. Executive summary

The current Review Studio is a **fully functional CRUD + streaming app with a two-mode UI**
(full agent mode vs review-only mode, switched server-side by `OPEN_EDIT_REVIEW_ONLY`). The
frontend is **vanilla ES modules, no framework, no bundler**:

- `index.html` — static shell, three-column grid + bottom timeline panel + modals + toast.
- `app.js` (69 KB) — ES-module entry point; imports 6 sibling modules from `static/js/` and
  contains the timeline renderer, preview player logic, renders/notes/settings, theme, cmd-K.
- `static/js/{state,dom,api,assets,chat,ws}.js` — state/normalizers, DOM helpers, REST client,
  assets panel, chat log/status widgets, WebSocket client.
- `style.css` (54 KB) — base design system + appended **CRT phosphor restyle** (green-on-black,
  amber accent, scanlines, vignette, film grain, flicker animation). Design language is
  "retro CRT terminal", **not** the Linear-style header comment (the header is stale; the
  variables were re-themed to CRT green).
- Logo today: `.crt-tv-icon` — a 24×20 px CRT-TV glyph **containing a literal letter "O"**
  (`.crt-tv-screen` text "O") — exactly what the mission says must be redesigned (monitor
  shape IS the O, no inner O).

No PNG timeline export, no "QC badges", no preview-chunks usage exist in the current
frontend (see §2 notes). Timeline = pure DOM (`<div>` boxes), preview = `<video>` + HTTP Range.

---

## 1. File map & load chain

```
index.html
  ├─ <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap">   (Google Fonts CDN)
  ├─ <link rel="stylesheet" href="/style.css?v=20260728-crt-restyle">
  └─ <script type="module" src="/app.js?v=20260729-preview-rev">
        └─ imports ./js/state.js, ./js/dom.js, ./js/api.js, ./js/assets.js, ./js/chat.js, ./js/ws.js
```

- Served by FastAPI `app.mount("/", StaticFiles(html=True))` mounted **last** (never shadows `/api`).
- No CSP headers anywhere (grep of `serve/` found none). No external JS libs; only Google
  Fonts (Inter + JetBrains Mono). Inline SVG icons inline in HTML/JS.
- **Backups exist:** `static.bak.20260806_154241/`, `static.bak.crt.20260806_173328/` — safe
  rollback points if redesign goes wrong.
- Body starts with `class="has-timeline"` (column layout incl. timeline). `data-theme="dark"` on `<html>`.

---

## 2. Feature inventory (every user-facing feature → DOM → JS powering it)

### 2.1 Project select & creation
- DOM: `#project-select`, `#btn-new-project`, `#btn-refresh-project`, `#new-project-name`, `#btn-create-project`, modal `#modal-new-project`.
- JS: `refreshProjects()` → `api.listProjects()` → `renderProjectSelect()`; `selectProject(id)` resets conversation/panels/timeline/status widgets and calls `loadProjectState()` + `connectWS()`; create → `api.createProject(name)`.
- Persistence: `localStorage['open_edit.current_project_id']`.

### 2.2 Left panel — Assets tab
- DOM: `#assets-list`, `#dropzone`, `#file-input` (hidden, `accept="video/*,audio/*,image/*"`, multiple), `#upload-progress`.
- JS: `renderAssets()` (assets.js) builds `.asset-card` (emoji icon by extension, duration/res/fps/codec/audio sub-line, "Add" button, click→`openAssetPreview()` modal). Upload via XHR `api.ingestFiles()` with progress bar; drag&drop + click handlers in `bindEvents()`. Loading state `.loading-state` + spinner during `getProjectState` (pinned by `tests/test_serve_loading_state.py`).
- Asset preview modal: `#modal-asset-preview`, `#asset-preview-video` — `<video src=asset.url>` streaming from `/api/projects/{id}/assets/{hash}/file` (Range-supported; validated 64-hex hash).
- "Add" button → `addAssetToTimeline()` → POST `/api/projects/{id}/ops` `{command:'add_clip', params:{asset_hash, track_id:'V1', position_sec, in_point_sec:0, out_point_sec}, expected_revision, author:'user'}`.

### 2.3 Left panel — Edit graph tab
- DOM: tab buttons `.panel-tabs .tab[data-tab="assets"|"edits"]`; `#edit-graph-list`, detail `#edit-detail-panel` (+`#edit-detail-kind/status/author/id/payload`), `#btn-edit-undo`, `#btn-edit-delete`.
- JS: `renderEditGraph()` (newest first, cap 50), `selectEdit()`, `showEditDetail()`; Undo → `PATCH /api/projects/{id}/ops/{edit_id}/status` `{status:'applied'|'reverted', expected_revision}`; Delete → `DELETE /api/projects/{id}/ops/{edit_id}?expected_revision=…` (confirm dialog; op is marked reverted, not hard-deleted).
- Auto-refresh loop: `startEditGraphRefresh()` — `setInterval` 5 s `api.getProjectState`, skips repaint when `graph_revision` unchanged; on change → toast + optional auto-proxy (15 s debounce).

### 2.4 Center — Preview player (review mode)
- DOM: `#preview-panel`, `#preview-player` (`<video controls playsinline>`), `#preview-empty`, `#preview-mode-badge`.
- Mode gating: `body:not(.review-only-mode) .preview-panel { display:none }`; review mode makes center a column (preview + chat input row still shown in review mode! chat-log/status are `agent-only` and hidden).
- JS: `loadRenderInPreview(renderId, mode)` — sets `player.src = /api/projects/{id}/renders/{renderId}/file` (FastAPI `FileResponse`, `Accept-Ranges: bytes` → browser `<video>` Range requests; `.melt` intermediates refused server+client-side). `maybeAutoLoadPreview()` — in review mode auto-selects newest playable proxy/final by `graph_revision`/`edit_graph_hash`/timestamp; stale preview → warn toast. `maybeLoadSourcePreview()` — plays first source asset when **no** succeeded proxy/final exists; badge "Source media"; error toast "…install Shotcut/melt".
- Time sync: `timeupdate` → `state.playheadSec` → `updatePlayheadUi()`.

### 2.5 Center — Chat (agent mode; `agent-only`)
- DOM: `#chat-log`, `.prompt-chip` ×4 (Cut silences / Add lower-third / Normalize audio / Render final), `#chat-status` (status pill), `#verify-chip` (verification pill), `#cost-badge` (cost pill), `.chat-input-row` with `#chat-input` textarea + `#btn-send` + `#btn-stop`; topbar also has `#btn-topbar-stop`.
- JS: `sendChatMessage()` → WS `{type:'user_message', message, conversation_id, conv_id}` (both contract shapes); `handleWsEvent()` dispatches `text`→`appendTextDelta` (streaming into `.msg-bot`), `tool_start`/`tool_result`→`.tool-card` (spinner → result; `search_assets` gets `appendSearchResults` grid with license badges + "+ Add to project" → `open-edit:quick-send` custom event → `sendText`), `error`, `render`→`.render-card`, `done`→`markTurnDone()`+`loadProjectState()+refreshRendersList()`, `cancelled`, `cost_update`→cost badge, `verification_started`/`verification_result`→verify chip.
- State machines: `createChatStatus` (idle/thinking/tool_running), `createVerifyChip` (idle/checking/verified/failed/skipped/capped), `createCostBadge` (pi/computed/unavailable labels) — all exposed on `window.OpenEdit.__testHooks` (pinned by tests).
- Send gate: `refreshSendGate()` — input/button disabled until project+provider+model selected; `setChatEnabled()` toggles stop buttons.

### 2.6 Right panel — Renders
- DOM: `#renders-list`, `#btn-refresh-renders`, `#render-encoder-select` (GPU/CPU), `#btn-render-proxy`, `#btn-render-final`; degraded-warning element `#renders-degraded-warn` (created on demand).
- JS: `renderRendersList()` — `.render-item` with status emoji, mode label ("Review artifact · 640×360" / "Final export · 1080p"), status label, size, time; click → `loadRenderInPreview()` (succeeded) or toast (running/queued/failed). `triggerRender(mode)` → POST `/api/projects/{id}/render` `{mode, encoder, expected_revision}` → `pollRenderJob()` (2 s interval, max 120 polls) + `refreshRendersList()`; `isProxyStale()` confirm-guard for final renders. Render polling: `state.renderPollTimer` — `setInterval(refreshRendersList, 5000)` only while any job queued/running.

### 2.7 Right panel — Notes
- DOM: `#notes-summary` (pending count), `#btn-show-notes` → modal `#modal-notes` + `#notes-list`.
- JS: `renderNotesSummary()`; `openNotesModal()` renders `.note-item` (time, source, status, text). Add at playhead: `#btn-add-note-playhead` → `prompt()` → `api.createNote()` POST `/api/projects/{id}/notes` `{text, t_start, t_end}`.

### 2.8 Right panel — Style section
- DOM only (`.panel-section` "Style"); static hint text per mode. No JS wiring. **Free space for redesign** (reference has an aspect/quality rail here).

### 2.9 Timeline panel (bottom)
- DOM scaffold: `#timeline-panel` > header (`#timeline-timecode-label`, `#timeline-duration-label`, `#btn-copy-timecode`, `#btn-add-note-playhead`, `#btn-timeline-zoom-in/out`, `#btn-timeline-fit`) > `.timeline-body` > `.timeline-responsive-inner` > `#timeline-track-labels` + `#timeline-ruler-col` (`#timeline-playhead`, `#timeline-ruler`, `#timeline-tracks-area` with `#timeline-empty-msg`).
- **Rendering: pure DOM** (no canvas, no PNG). `renderTimeline(timelineData, {edits, notes})` (exported) draws: ruler ticks (`.timeline-ruler-tick`, step adapts to zoom), track label rows with kind badge, `.timeline-track-row` (34 px, zebra), `.timeline-clip` (video/audio, left+width via `secToPx = sec*60*tlZoom`), `.timeline-overlay-marker` (yellow "HTML"), `.timeline-remotion-marker` ("REM"/"REM?" pending), `.timeline-edit-marker` (click → select edit + switch to Edit graph tab + seek), `.timeline-note-marker` (click → seek + notes modal), playhead line positioned `left: secToPx(playheadSec)`.
- Interactions: click/drag scrub on `#timeline-ruler-col` (`mousedown/mousemove/mouseup`, ignores markers), zoom in/out (1.5×, clamp 0.001–8), Fit (`fitTimelineToWindow` — zoom = availW/(dur*60), no 0.05 floor), `tlAutoFitPending` auto-fit once for >120 s timelines, timecode copy → clipboard `[MM:SS.FF]`, note-at-playhead.
- Data: `state.currentProjectState.timeline_full` (tracks/clips/overlays/remotion_compositions/duration_sec) from `GET /api/projects/{id}`; normalized by `normalizeTimeline`.

### 2.10 Topbar (global)
- Logo block (`#logo` with `.crt-tv-icon` — see §4.4), project select, LLM provider/model selects (`#llm-provider-select`, `#llm-model-select`, `#llm-tools-warn`), `#btn-cmd-k` (⌘K palette), `#btn-toggle-theme` (🌙/☀️), panel collapse `#btn-toggle-left-panel/right-panel` (review mode), `#btn-settings` (agent), `#btn-topbar-stop` (agent), mobile toggles `#btn-left-panel/right-panel`, `#conn-status` dot (red/yellow/green WS state).
- Command palette: `#modal-cmd-k`, `#cmd-input`, `#cmd-list`; 8 commands (new project, refresh, proxy render, final render, settings, theme, upload, clear chat); keyboard nav ↑↓↵, Esc, ⌘K/Ctrl+K global.
- Settings modal (agent): `#modal-settings`, `#settings-runtimes-list` (from `/api/runtimes`), API-key inputs `#key-anthropic|openai|opencode|antigravity` (GET/PUT `/api/settings/keys`), `#btn-save-settings-keys`.
- LLM config: GET/PUT `/api/projects/{id}/llm-config`, GET `/api/llm/providers/{p}/models`; save → reconnect WS.
- Theme: `data-theme` on `<html>`; `localStorage['open-edit-theme']`.

### 2.11 Modals & toast (shared)
- `.modal` + `.modal-backdrop` + `.modal-card(-wide)`; `#toast` (bottom-center, error/success/info/warn classes, auto-hide 3 s); `[data-modal-close]` buttons; Esc closes all; media stopped on modal close (`stopModalMedia`).

### 2.12 WS connection
- URL `ws(s)://{host}/api/chat/{projectId}[?token=…]` (token from `localStorage['openEditWsToken']`, https only); exponential backoff reconnect (max 8, cap 10 s), close code 4404 = project not found (no reconnect), online/focus reconnects.

### 2.13 Feature check vs parent's checklist
- ✅ project select, timeline (DOM), preview player (`<video>` + Range), renders list, notes, chat (agent UI), asset list, playhead/ruler, overlays (HTML overlay + Remotion markers), verify chip (QC-ish).
- ❌ **timeline view PNG** — does NOT exist (no PNG/screenshot export anywhere in frontend or API; closest: project thumbnail `GET /api/projects/{id}/thumbnail` serving `.open_edit/thumbnail.png|jpg`, and `preview-chunks` artifacts which the frontend never consumes).
- ❌ **QC badges** — no QC concept in current UI; nearest is `#verify-chip` (render verification status pill).

---

## 3. app.js structure

### 3.1 Module layout
| Module | Role |
|---|---|
| `app.js` (entry) | boot, bindEvents, project/load/select, panels, renders, notes, settings, theme, cmd palette, chat input, LLM selects, preview player, timeline renderer, `window.OpenEdit` + `__testHooks` |
| `js/state.js` | `state` singleton + normalizers `normalizeAssets/Edits/Timeline/Renders/Notes` + `summarizeOpPayload` (no DOM) |
| `js/dom.js` | `$`, `$$`, `el()`, `showToast`, `showModal/hideModal/hideAllModals/stopModalMedia`, `fmtBytes/fmtDuration/fmtTime`, `truncate` |
| `js/api.js` | `api` REST client (see 3.3) + `_extractError` (parses `{"error"}`/`{"detail"}`) |
| `js/assets.js` | `renderAssets`, `assetIcon`, `openAssetPreview` |
| `js/chat.js` | chat log, tool cards, search results panel, chat-status/verify-chip/cost-badge state machines, `sendChatMessage` |
| `js/ws.js` | `connectWS/disconnectWS/scheduleReconnect`, `setWsState/setReviewConnStatus`, `setOnTurnDone`, `handleWsEvent` |

### 3.2 Key functions & flow
- `boot()` (on DOMContentLoaded): initTheme → `api.getUiConfig()` (sets `state.reviewOnly`/`autoProxy`; adds `review-only-mode panel-left-collapsed` body classes) → `bindEvents()` → create status/verify/cost widgets → `setOnTurnDone(loadProjectState+refreshRendersList)` → `refreshProjects()` → if saved project: `loadProjectState()` + `loadLLMConfig()` + `connectWS()` (or disconnect in review mode) → `startEditGraphRefresh()`.
- `loadProjectState()` → `api.getProjectState(id)` → `paintProjectSnapshot(s)` = renderAssets + renderEditGraph + renderNotesSummary + renders (inline `last_renders` or `refreshRendersList()`) + `renderTimeline(s.timeline_full)` + `maybeLoadSourcePreview` + invalid-timeline toast.
- **Rendering approach:** DOM APIs only (`document.createElement` via `el()` helper, `appendChild`, `innerHTML=''` clears, `textContent`). No innerHTML template strings for dynamic content (except small static clears). Event wiring: `addEventListener` in `bindEvents()` + per-element closures; delegation used for scrubbing (document mousemove/mouseup), modal backdrop clicks, `open-edit:quick-send` custom event.
- **Polling loops:** ① edit-graph refresh 5 s (always); ② renders refresh 5 s while active jobs (renderPollTimer); ③ render job poll 2 s ×120 after triggering; ④ WS auto-reconnect backoff; ⑤ auto-proxy debounce 15 s after graph change.

### 3.3 API surface used by the frontend
| Method/URL | Used by | Payload |
|---|---|---|
| GET `/api/ui-config` | boot | — |
| GET `/api/projects` | refreshProjects | — |
| POST `/api/projects` | create | `{name}` |
| GET `/api/projects/{id}` | loadProjectState, edit-graph poll | — (returns ProjectState incl. `timeline_full`, `ops`, `notes`, `assets[].url`, `graph_revision`, `edit_graph_hash`, `pending_notes_count`) |
| POST `/api/projects/{id}/ingest` | upload (XHR+FormData) | multipart `files` (repeated), progress events |
| POST `/api/projects/{id}/render` | triggerRender | `{mode, encoder, expected_revision}` |
| GET `/api/projects/{id}/renders` | refreshRendersList | — |
| GET `/api/projects/{id}/render_jobs/{job_id}` | pollRenderJob | — |
| GET `/api/projects/{id}/renders/{render_id}/file` | `<video src>` | — (FileResponse, Range) |
| GET `/api/projects/{id}/assets/{hash}/file` | asset preview / source preview | — (FileResponse, Range) |
| GET `/api/projects/{id}/thumbnail?path=` | `api.thumbnailUrl` (defined, **currently unused**) | — |
| POST `/api/projects/{id}/ops` | addAssetToTimeline | `{command, params, author:'user', expected_revision}` |
| PATCH `/api/projects/{id}/ops/{edit_id}/status` | undoEdit | `{status, expected_revision}` |
| DELETE `/api/projects/{id}/ops/{edit_id}?expected_revision=` | deleteEdit | — |
| POST `/api/projects/{id}/notes` | addNoteAtPlayhead | `{text, t_start, t_end}` |
| GET/PUT `/api/projects/{id}/llm-config` | loadLLMConfig/saveLLMConfig | PUT `{provider, model}` |
| GET `/api/llm/providers/{p}/models` | provider dropdown | — |
| GET `/api/runtimes`, GET/PUT `/api/settings/keys` | settings modal | PUT `{provider, key}` |
| WS `/api/chat/{project_id}` | chat | send `{type:'user_message', message, conversation_id, conv_id}` / `{type:'cancel'}` |

### 3.4 State management
Single mutable `state` object (state.js): projects, currentProjectId/State, conversationId, ws/wsState/reconnect*, editGraphRefreshTimer, pendingAssistantMsg, pendingToolCards Map, chatStatus/verifyChip/costBadge widget handles, reviewOnly, autoProxy, playheadSec, lastGraphRevision, proxyRenderInFlight, renderPollTimer, previewRenderId. Module-level vars in app.js: `selectedEditId`, `tlZoom/tlDurationSec/tlCurrentData/tlEditMarkers/tlNoteMarkers/tlScrubbing/tlAutoFitPending`, `chatBaseEnabled`, `providerCapabilities`, `llmProviderSelect/llmModelSelect/llmToolsWarn`, `COMMANDS`/`filteredCommands`/`activeCmdIndex`. Persisted: localStorage keys `open_edit.current_project_id`, `open_edit.conversation_id`, `open-edit-theme`, `openEditWsToken`.

---

## 4. style.css structure & design language

### 4.1 Section map (line numbers in file)
1. Header comment claims **"linear-app"** design system — **stale** (see 4.3).
2. Reset + base (l.18–70) — `:root` CSS variables (CRT palette).
3. `[data-theme="light"]` overrides (l.79–112).
4. Film grain `body::after` (l.116), body base.
5. SVG icon helper `.icon-svg` (l.156).
6. Top bar (l.165) — `.topbar`, `.logo`, `.logo-text`, `.logo-badge`, `.topbar-label`, `.project-select`.
7. Buttons (l.244) — `.btn/-primary/-secondary/-ghost/-outline/-danger/-xs/-sm`, `.kbd-badge`, `.mobile-only`.
8. Connection dot (l.346), Layout grid (l.359) `grid-template-columns: var(--sidebar-w) 1fr var(--sidebar-w)`; panel-center radial lift.
9. Panel tabs (l.393), Assets list (l.434), Dropzone (l.469), Edit graph (l.500), Edit detail (l.541).
10. Center/Chat (l.592) — `.chat-log`, `.empty-state`, `.welcome-*`, `.prompt-chip`, `.msg-*`, tool card (l.700), loading (l.753), render card (l.767), chat status (l.788), cost badge (l.823), verify chip (l.848), chat input (l.878).
11. Right panel (l.912) — `.panel-section`, `.renders-list`, `.render-item`, `.render-buttons`, `.encoder-select`, `.notes-summary`.
12. Modal (l.1001), command palette (l.1104), toast (l.1163).
13. Responsive <1024px (l.1185) — side panels become slide-over drawers; <600px tweaks.
14. Scrollbars (l.1216), Search results (l.1226), Timeline panel (l.1360) — full timeline CSS incl. markers/playhead; `body.has-timeline` column layout (l.1618).
15. LLM bar (l.1626), Review studio (l.1633) — `body.review-only-mode` gating of `.agent-only`/`.review-only`, preview player rules, collapsible panels (l.1677).
16. Reduced motion (l.1686), then **CRT restyle appended**: CRT Effects (scanlines `body::before` + vignette `body::after`, l.1695), Logo CRT style (l.1740), Timeline markers CRT (l.1854), and **duplicated** CRT Effects/Logo/marker blocks again at l.1917/1962/2076 (harmless overrides, but dead weight).

### 4.2 CSS variables (`:root`, dark)
`--bg-deep #080908, --bg #0d0f0e, --bg-elev #131714, --bg-elev-2 #1a201c, --bg-surface #222a24` · `--border rgba(51,255,102,.2)` · `--text #33ff66, --text-primary #5cff85, --text-muted #24b347, --text-dim #1a8033` · `--accent #ffb000, --accent-hover #ffcc4d, --accent-dim/--accent-glow` · `--green #33ff66, --yellow #ffb000, --warn, --red #ff3333` (+dim variants) · bubble vars `--user-bubble/--user-border/--bot-bubble/--bot-border/--tool-bubble/--tool-border` · `--radius 2px / -lg 4px / -xl 6px / -pill 999px` · `--topbar-h 44px, --sidebar-w 260px` · `--transition 150ms / -slow 200ms` · `--font-sans Inter…, --font-mono JetBrains Mono…` · `--shadow-card/--shadow-modal/--focus-ring`. Light theme overrides the same tokens (green→dark green, accent→amber-brown).

### 4.3 Current design language (what it actually looks like)
**CRT phosphor terminal**: near-black green-tinted surfaces, phosphor-green primary text (#33ff66), amber accent (#ffb000) for CTAs/active/playhead, 2–4 px radii (sharp, technical), scanline overlay (`body::before` linear-gradient 4 px rows, z-9998, opacity .5), vignette (`body::after` radial, z-9999), film grain (SVG feTurbulence data-URI, opacity .035, z-9999), monospace used heavily for metadata/timecodes, uppercase letter-spaced labels, glow shadows (`0 0 10px rgba(51,255,102,…)`), `crt-flicker` keyframes on the logo screen. **Note:** the two `body::after` rules (film grain l.117 vs CRT vignette l.~1700) conflict — later one wins (vignette); same for `body::before`. `.btn-secondary` still uses the stale indigo `#7170ff`/`#a5a5e8` palette (leftover from the pre-CRT design — the restyle wasn't thorough). `prefers-reduced-motion` respected (animations/transitions killed).

### 4.4 Current logo markup + CSS
HTML (index.html topbar):
```html
<span class="logo" data-od-id="logo" id="logo">
  <span class="crt-tv-icon">
    <span class="crt-tv-screen">O</span>          <!-- literal letter O — mission says REMOVE -->
    <div class="crt-tv-knobs"><div class="crt-tv-knob"></div><div class="crt-tv-knob"></div></div>
  </span>
  <span class="logo-text">pen&nbsp;Edit</span>
</span>
```
CSS: `.crt-tv-icon` = 24×20 px inline-flex, `--bg-deep` fill, 1 px `--green` border, radius 4 px, inner glow; `.crt-tv-screen` = flex-1 green-dim panel, 11 px mono "O", `crt-flicker` 4 s infinite, green text-shadow; `.crt-tv-knob` = 3×3 px green dots column on the right; light-theme overrides. Wordmark text is "pen Edit" (13.5 px, 600, `--text`). **Redesign target:** monitor shape must itself read as the O (rounded square, no inner letter), sized optically like a capital O in the wordmark, matching the reference's style (gradient, radius, elevation, glass — per mission §Hard requirement).

---

## 5. Dependencies & fragility (what breaks if markup changes)

### 5.1 JS contract — element IDs app.js/chat.js/ws.js/assets.js/dom.js REQUIRE (must keep ids or update JS in lockstep)
`#project-select` `#btn-new-project` `#btn-refresh-project` `#btn-create-project` `#new-project-name`
`#assets-list` `#dropzone` `#file-input` `#upload-progress`
`#edit-graph-list` `#edit-detail-panel` `#edit-detail-kind` `#edit-detail-status` `#edit-detail-author` `#edit-detail-id` `#edit-detail-payload` `#btn-edit-undo` `#btn-edit-delete`
`#preview-player` `#preview-empty` `#preview-mode-badge`
`#chat-log` `#chat-input` `#btn-send` `#btn-stop` `#btn-topbar-stop` `#chat-status` `#verify-chip` `#cost-badge` (+ inner `.chat-status-text` `.verify-chip-text` `.cost-badge-text`)
`#renders-list` `#btn-refresh-renders` `#btn-render-proxy` `#btn-render-final` `#render-encoder-select` `#renders-degraded-warn` (created on demand)
`#notes-summary` `#btn-show-notes` `#notes-list`
`#timeline-panel`(data-od-id) `#timeline-timecode-label` `#timeline-duration-label` `#btn-copy-timecode` `#btn-add-note-playhead` `#btn-timeline-zoom-in` `#btn-timeline-zoom-out` `#btn-timeline-fit` `#timeline-track-labels` `#timeline-ruler-col` `#timeline-playhead` `#timeline-ruler` `#timeline-tracks-area` `#timeline-empty-msg`
`#conn-status` `#btn-cmd-k` `#cmd-input` `#cmd-list` `#modal-cmd-k` `#btn-toggle-theme` `#btn-settings` `#btn-toggle-left-panel` `#btn-toggle-right-panel` `#btn-left-panel` `#btn-right-panel` `#left-panel` `#right-panel`
`#llm-provider-select` `#llm-model-select` `#llm-tools-warn`
`#modal-new-project`(via `$('#new-project-name')` only + showModal id) `#modal-asset-preview` `#asset-preview-title` `#asset-preview-video` `#modal-notes` `#modal-settings` `#settings-runtimes-list` `#key-anthropic` `#key-openai` `#key-opencode` `#key-antigravity` `#btn-save-settings-keys` `#toast`
(showModal/hideModal use `$('#'+id)` — modal ids `modal-cmd-k`, `modal-new-project`, `modal-asset-preview`, `modal-notes`, `modal-settings` are referenced by name in JS.)

### 5.2 Class/attribute contract
- `.modal`, `.modal-backdrop`, `.modal-card(-wide)`, `.hidden` (display:none !important), `[data-modal-close]` (buttons + backdrop).
- `.panel-tabs .tab` + `.tab-content[data-tab="…"]` + `data-tab` values `assets`/`edits`; `.panel-tabs .tab[data-tab="edits"]` clicked by timeline edit markers.
- `.empty-state` (removed by chat.js when first message arrives), `.msg .msg-user .msg-bot .msg-error`, `.tool-card .gear .tool-body .tool-name .tool-input .tool-result(.failed)`, `.spinner`, `.search-results(-placeholder)` grid `.result-card .result-thumb .result-body .result-title .result-meta .license-badge(.attr-required/.permissive) .result-attribution .result-import-btn`, `.render-card`, `.prompt-chip` + `data-prompt` attribute.
- `.timeline-*`: `.timeline-track-row`, `.timeline-clip(.video-clip/.audio-clip)`, `.timeline-overlay-marker`, `.timeline-remotion-marker(.pending)`, `.timeline-edit-marker(.reverted)`, `.timeline-note-marker`, `.timeline-ruler-tick(-line/-label)`, `.timeline-track-label-row`, `.track-kind-badge(.video/.audio)`, `.timeline-empty-state`; `#timeline-ruler-col[data-scrub-bound]` flag.
- Body classes toggled by JS: `review-only-mode`, `panel-left-collapsed`, `panel-right-collapsed`; `has-timeline` (static in HTML); `.open` on `#left-panel`/`#right-panel` (mobile drawers); `agent-only`/`review-only`/`mobile-only` visibility classes driven by CSS + review-mode body class.
- `.chat-status[data-state]`, `.cost-badge[data-source]`, `.verify-chip[data-state]` attributes are set by JS state machines (tests intercept `setAttribute`).
- `data-od-id` attributes (30 in index.html — reference-compatible ids): topbar, logo, btn-new-project, btn-refresh-project, btn-cmd-k, btn-toggle-theme, btn-toggle-left-panel, btn-toggle-right-panel, btn-settings, btn-topbar-stop, btn-left-panel, btn-right-panel, conn-status, layout, panel-left, panel-center, btn-send, panel-right, btn-refresh-renders, btn-render-proxy, btn-render-final, btn-show-notes, timeline-panel, btn-copy-timecode, btn-add-note-playhead, btn-timeline-zoom-in/out/fit, btn-create-project, btn-save-settings-keys. (Used by reference harness/automation — keep them.)

### 5.3 Module import contract
`app.js` must keep the six `./js/*.js` imports and the `window.OpenEdit` + `__testHooks` exports: `state`, `api`, `formatPreviewDiagnostics`, `connectWS`, `refreshProjects`, `loadProjectState`, `selectProject`; hooks `normalizeAssets, normalizeEdits, normalizeTimeline, normalizeRenders, normalizeNotes, summarizeOpPayload, openAssetPreview, createChatStatus, createCostBadge, appendSearchResults, sendChatMessage, handleSend` — pinned by `tests/test_serve_module_structure.py`.

### 5.4 Tests pinning frontend behavior (must stay green)
- `test_serve_module_structure.py` — module loads, hooks/helpers present.
- `test_serve_chat_status.py` — chat-status state machine (setAttribute/data-state, hidden class, label text).
- `test_serve_cost_badge.py` — cost badge labels ("cost n/a (subscription)", "$0.00"/formatting, data-source).
- `test_serve_verify_chip.py` — verify chip states/labels.
- `test_serve_loading_state.py` — assets list loading spinner then data.
- `test_serve_asset_stream.py` — `normalizeAssets` url passthrough, `openAssetPreview` title annotation, asset URL/stream contract.
- `test_serve_search_assets.py` — search results panel renderer.
- `test_serve_send_reconnect.py` — `handleSend` + reconnect on CONNECTING.
- `test_review_ui.py` — reads `app.js`/`index.html` **text**: asserts strings `"Review artifact · 640×360"`, NOT `"Proxy 720p"`/`"540p"`, `"Source media"` present. (Renaming mode labels breaks this test.)
- Plus backend tests: renders/preview-chunks/ws/projects/llm-config/etc. (server-side, unaffected by markup except `/api/ui-config` contract).

### 5.5 Environment/other
- No CSP headers; Google Fonts requires network (fallback stacks provided). WS token via `localStorage.openEditWsToken` (https only). `window.__renderTimeline` global (debug, used by nothing else). `window.OpenEdit` debug namespace. Server static mount serves only the static dir — no hashing/asset pipeline; cache-busting is manual `?v=` query strings.

---

## 6. What MUST be preserved for functionality (the JS contract checklist)

1. **All IDs in §5.1** (or coordinated JS edits — every `$('#…')` call site).
2. **Module structure**: `app.js` + `js/{state,dom,api,assets,chat,ws}.js` as native ES modules; `window.OpenEdit` + `__testHooks` namespace (test contract).
3. **API calls & payload shapes** (§3.3) — any re-styling must not change request/response handling; server error shape `{"error": …}`.
4. **WS event loop** — `handleWsEvent` event types (ready/text/tool_start/tool_result/error/render/done/cancelled/cost_update/verification_started/verification_result); client send payloads `user_message` + `cancel`.
5. **Preview streaming** — `<video>` element with `src` set to Range-capable `/api/projects/{id}/renders/{render_id}/file` and `/api/projects/{id}/assets/{hash}/file`; `.melt` filtering; `#preview-mode-badge` labels (test-pinned text).
6. **Timeline renderer behavior** — `renderTimeline` DOM output classes (§5.2), scrubbing, zoom, fit, playhead `style.left`, markers' click actions (edit-select + tab switch, note modal).
7. **Mode gating** — `.agent-only`/`.review-only`/`body.review-only-mode`/`panel-*-collapsed` classes; review mode must keep preview + renders + timeline + notes + assets working without chat.
8. **localStorage keys** (`open_edit.current_project_id`, `open_edit.conversation_id`, `open-edit-theme`, `openEditWsToken`) and `data-theme` attribute behavior.
9. **Modal semantics** — `.modal` + `.hidden` toggling, `[data-modal-close]`, backdrop click, Esc, media stop on close.
10. **data-od-id attributes** (reference harness compatibility, §5.2).
11. **Test-pinned strings** (`"Review artifact · 640×360"`, `"Source media"`, no `"Proxy 720p"`/`"540p"`).
12. **Server contract** (unchanged by UI work but the redesign must keep using it): `/api/ui-config` flags, review-only mode on port 8000 (currently `--review-only`).

---

## 7. Notes for the merge strategy (cur-2 / coordinator)

- The **logo is the one place the mission's hard requirement is currently violated** (literal "O" inside `.crt-tv-screen`); everything else is a CSS/DOM reskin.
- Current CSS has **stale/contradictory remnants**: "linear-app" header comment, indigo `btn-secondary` colors, duplicated CRT blocks, and two competing `body::before/::after` overlays — a redesign gives a chance to consolidate.
- The reference design and the current app share the same information architecture (topbar, 3-column workspace, bottom timeline, project picker, renders/notes rails, prompt chips, agent/review mode toggles) — mapping is 1:1 per feature; see sibling reports for the reference side.
- Biggest functional constraints on layout freedom: timeline panel is a fixed 180 px bottom bar with its own scroll container; center column is a flex column (preview + chat widgets); review-only mode hides the chat but keeps the input row visible.
