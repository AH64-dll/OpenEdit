# Stage 3 Code Review — OpenEdit Review Studio (Redesign)
Reviewer: review-code (DeepSeek V4 Flash) · Date: 2026-08-06
Scope: B (DOM half) · C (wiring) · E (contract) · git-diff sanity
Sources: open_edit/serve/static/{index.html,style.css,app.js}, js/{dom,ws,api,assets,chat,state}.js, testrun/ui/CONTRACT.md, git diff (HEAD ce93e42 → working tree)

---
## Summary
| Item | Verdict | Confidence |
|---|---|---|
| B — logo DOM (no inner O, sizes) | PASS | 98% |
| C — wiring exists for each feature | PASS | 95% |
| E — contract (68 IDs, classes, 3 vars, __testHooks, pinned strings) | PASS | 97% |
| Git-diff sanity (dead CRT blocks, regressions) | PASS (2 dead-code notes) | 92% |

## E — Contract gates

### E1. All IDs from CONTRACT.md present
Extracted the full enumerated ID list from CONTRACT.md (81 tokens incl. inner/on-demand items; contract's own "68" excludes `#renders-degraded-warn` (on-demand) and modal-name refs).
- **80/81 found in index.html** (`id="..."`); 0 true duplicate IDs (88 unique `id` attrs; 118 raw including `data-od-id`).
- The 1 not-in-HTML ID, `renders-degraded-warn`, is contractually "created on demand" — app.js creates it verbatim: `el('div', { id: 'renders-degraded-warn', class: 'empty-state' }, [])` (catch path in refreshRenders). ✓
- Reverse check: 72 unique IDs referenced by JS (`$('#..')` etc. across all 7 JS files) — **all present in index.html** except `renders-degraded-warn` (on-demand, above). No renamed IDs.
- `data-od-id`: exactly **30** in index.html, set matches CONTRACT list 1:1 (topbar, logo, btn-new-project, btn-refresh-project, btn-cmd-k, btn-toggle-theme, btn-toggle-left/right-panel, btn-settings, btn-topbar-stop, btn-left/right-panel, conn-status, layout, panel-left/center/right, btn-send, btn-refresh-renders, btn-render-proxy/final, btn-show-notes, timeline-panel, btn-copy-timecode, btn-add-note-playhead, btn-timeline-zoom-in/out/fit, btn-create-project, btn-save-settings-keys). ✓
- Modals wired per contract: `showModal/hideModal/hideAllModals` in dom.js use `$('#'+id)`; modal ids `modal-cmd-k`, `modal-new-project`, `modal-asset-preview`, `modal-notes`, `modal-settings` all exist in HTML and are referenced by name in JS. ✓

### E2. 3 inline var names defined in style.css
- `--green`, `--text-dim`, `--border` — all defined (3/3/3 declarations incl. legacy blocks). Winning declarations (final `:root`, lines 2203–2255): `--green: #16a34a; --text-dim: #85858b; --border: rgba(255,255,255,.14)`. ✓
- Note: `--green` resolves to #16a34a (modern green-600, used for status/conn dot), NOT the legacy CRT #33ff66/#0a4d1a (those appear only in the dead light-theme block, see Git-diff notes). Design gate A may still want to eyeball the 27 `var(--green)` uses — code-wise the contract requires only that the var is defined.

### E3. JS-emitted classes unchanged
All CONTRACT classes verified present in JS **and** CSS (or static HTML where the contract says so):
- `.modal`(16 rules) `.modal-backdrop`(3) `.modal-card(-wide)`(9/3) `.hidden` `[data-modal-close]` (5 buttons in HTML, queried in app.js:1143)
- `.panel-tabs .tab` + `.tab-content[data-tab="assets"/"edits"]` (both in HTML ×2; `.panel-tabs .tab` CSS at 2557+)
- `.empty-state`, `.msg/.msg-user/.msg-bot/.msg-error`, `.tool-card .gear .tool-body .tool-name .tool-input .tool-result` + modifier `.failed`, `.spinner`, `.search-results(-placeholder)`, `.result-card .result-thumb .result-body .result-title .result-meta .license-badge` + modifiers `.attr-required`/`.permissive`, `.result-attribution`, `.result-import-btn`, `.render-card`, `.prompt-chip` + `data-prompt` (4 in HTML)
- `.timeline-*`: track-row/clip(+video/audio)/overlay-marker/remotion-marker(+pending)/edit-marker(+reverted)/note-marker/ruler-tick(-line/-label)/track-label-row/track-kind-badge(+video/audio)/empty-state — all in CSS+JS; `#timeline-ruler-col` gets `data-scrub-bound` via `dataset.scrubBound='1'` in bindTimelineScrubbing (app.js:1763). ✓
- Body classes: `review-only-mode` (add), `panel-left-collapsed`/`panel-right-collapsed` (toggle) in app.js; `has-timeline` static in HTML; `agent-only`/`review-only`/`mobile-only` in HTML. ✓
- `.chat-status[data-state]` (css=18), `.cost-badge[data-source]` (css=3), `.verify-chip[data-state]` — JS state machines set attributes (tests intercept setAttribute). ✓

### E4. window.OpenEdit.__testHooks intact
`window.OpenEdit = { state, api, formatPreviewDiagnostics, connectWS, refreshProjects, loadProjectState, selectProject, __testHooks: { normalizeAssets, normalizeEdits, normalizeTimeline, normalizeRenders, normalizeNotes, summarizeOpPayload, openAssetPreview, createChatStatus, createCostBadge, appendSearchResults, sendChatMessage, handleSend } }` — **12 hooks, all present** (app.js ~1439–1469). ✓

### E5. Test-pinned strings intact
- `"Review artifact · 640×360"` in app.js ✓ (test_review_ui.py pins it)
- `"Proxy 720p"` absent ✓, `"540p"` absent ✓ (tests assert absence)
- `"Source media"` in app.js ✓
- `id="cost-badge"` in index.html:173 ✓ (test_serve_cost_badge.py:57 pins it)
- Node-harness frontend suites **all green**: test_serve_chat_status (5), test_serve_search_assets + cost_badge + send_reconnect + loading_state + module_structure (20), test_serve_asset_stream + test_review_ui (19) — total 44 passed, 0 failed.
- `node --check` passes on all 7 JS files (app.js + js/{api,assets,chat,dom,state,ws}.js). ✓

## B — Logo, DOM half
- Markup: `<a class="logo" data-od-id="logo" id="logo" href="/" aria-label="Open Edit"><span class="logo-mark" aria-hidden="true"></span><span class="logo-text">pen&nbsp;Edit</span></a>`.
- **`.logo-mark` is an empty span — no text node, no "O"** (only a comment in the markup; `content: ""` in `.logo-mark::after`; no `content:"O"` anywhere in CSS — the only 'OV' content string is the timeline overlay marker label, line 2834). ✓
- Mark sits **in the O position** (before "pen Edit") → reads "Open Edit". ✓
- `.crt-tv-screen`/`.crt-tv-knobs`: **absent from HTML entirely** (0 occurrences); additionally killed in CSS: `.crt-tv-screen { opacity:0 !important; font-size:0 !important; color:transparent !important; }` (line 2378), `.crt-tv-knobs { display:none !important; }` (line 2379) with comment "hide the old glyph/knobs so the monitor itself reads as the O". Double-safe. ✓
- Sizes: `.logo-mark` **22×22px** (style.css:2357–2358; 20px under ≤560px media query), wordmark `.logo` font-size **16px** (2345). Wordmark/mark ratio = 16/22 = **0.727 ∈ [0.72, 0.75]** ✓. Glass opening (::after inset 5px → 12px) ≈ cap-height of the 16px "O" (~11.5px, 0.72×16). ✓ Monitor = rounded-rect screen + bezel + blue gradient + glow (2352–2374) — squircle-with-screen, as required.

## C — Wiring exists for each feature (partial, wiring-level)
- **Transport (NEW)**: `#btn-skip-back/#btn-play/#btn-skip-fwd/#tc-current/.transport-total` all in index.html (preview-panel) + handlers in app.js: `seekPreviewBy(±5)` (clamps 0..duration), `togglePreviewPlayback` (play() promise caught), `updatePreviewTransport` (play/pause icon swap ❚❚/▶, aria-label, timecode), bound in bindEvents + play/pause/ended listeners on `#preview-player`. ✓
- **Theme toggle**: `applyTheme` sets `documentElement.dataset.theme` (flips data-theme) **and swaps the button SVG** (moon path for dark / sun for light) via innerHTML — SVG icon swap present (app.js ~630–646; diff replaced the old 🌙/☀️ emoji). ✓
- **Range-probe fix**: `_renderEndpointIsReachable` (app.js:1533+) — `fetch(renderFileUrl, { headers: { Range: 'bytes=0-0' }, cache: 'no-store' })`, cancels body, returns `response.ok`; guard skips stale durable rows outside the project root; `maybeAutoLoadPreview` now tries preferred→fallback candidates, skipping 404s instead of stranding the preview. ✓ (git diff confirms this is a new addition, not a revert.)
- **WS transport** (ws.js, unchanged by this diff): connect/reconnect with exponential backoff capped 10s, max 8 attempts, stale-socket guard, intentional-close guard, 4404 project-not-found stop, review-only mode sets `conn-status connected` "Review mode (no chat WebSocket)". `scheduleReconnect` exported & used. ✓
- All feature IDs bound in bindEvents: project select/create/refresh, assets, edits, renders, notes, chat, cmd-K palette (`openCmdPalette`), panel toggles, settings modal, toast (`showToast`), timeline scrub (`bindTimelineScrubbing`). ✓

## Git-diff sanity
Diff: index.html +232/−102, style.css +1825/−424, app.js +115/−6 (ws.js/dom.js/etc. untouched). Redesign confined to the 3 static files.

- **CRT colors**: `#33ff66` and `#ffb000` — **0 occurrences** in html/css/js. Legacy `#0a4d1a/#1bba43/#b37a00/#05290e/#128c30` exist ONLY inside the dead `[data-theme="light"]` block (lines 85–118; see note). ✓
- **scanline/grain**: no scanline rules at all; `body::before, body::after { content:none !important; display:none !important; background:none !important; opacity:0 !important; animation:none !important; }` at lines 2944–2952 (comment: "CRT texture shutdown: the studio shell is clean graphite, not scanlined") **kills both the old texture pseudo-elements and the new film-grain rule (lines 122–133, opacity .035)** — later source order + !important. Grain/scanlines DISABLED. ✓
- **vignette**: 0 occurrences. ✓
- **flicker**: `@keyframes crt-flicker` defined twice (1734, 1956) but referenced only by `.crt-tv-screen`, which is (a) absent from the DOM, (b) `opacity:0 !important` (2378), (c) `animation:none !important` (2953). DISABLED. ✓
- **Duplicate :root blocks** — 5 theme blocks: line 9 (`:root`: light base + studio tokens + legacy aliases), 85 (`[data-theme="light"]`: STALE CRT green/amber), 2171 (`:root`: `--studio-*` tokens: graphite #1a1a1c…, accent #0071e3, radii 8/12/18/980), 2203 (`:root`: legacy alias names **remapped to graphite/blue** — `--accent:#0071e3`, `--text:#f5f5f7`, `--text-dim:#85858b`, `--border:rgba(255,255,255,.14)`, `--green:#16a34a`), 2259 (`:root`: `--oe-*` compat aliases). The new blocks come **after** the legacy/light blocks with equal specificity → **new values win**. ✓

### Non-blocking findings (dead code, zero rendering impact)
1. **Duplicate dead "Logo CRT Style" blocks** — the entire legacy `.crt-tv-icon/.crt-tv-screen/.crt-tv-knobs/.crt-tv-knob` + `[data-theme="light"]` variants exist **twice** (lines ~1747–1797 and ~1969–2014), plus duplicate `@keyframes crt-flicker`. No HTML element carries these classes, and the kill rules (2378–2379, 2953) neutralize them regardless. They are dead/duplicate CSS, not styling anything — cleanup, not a regression.
2. **`[data-theme="light"]` block (85–118) never got its values remapped** — comment promises "Linear light neutrals" but values are the old CRT green/amber. Every color var it sets is overridden by the later `:root` (2203) so it has **no rendering effect**; only `--shadow-card/--shadow-modal` survive from it in light theme. Note for reviewer A: light theme currently resolves to the dark studio palette (later `:root` wins), so "Toggle Light/Dark Mode" may not visibly lighten — design-level concern, not a contract break.
3. Cosmetic: `.conn-label` span in the conn-status markup has no CSS rule and is hidden by the 9px/overflow:hidden/color:transparent dot style (2415–2430); ws.js overwrites className with `conn-status <state>` (drops unused `conn` class). Harmless.

## Verdict
- **B: PASS** — DOM has no inner O; legacy CRT logo elements hidden/absent; sizes within spec (22px mark / 16px wordmark → ratio 0.727).
- **C: PASS (wiring)** — transport, theme SVG swap, Range probe, WS reconnect, and all feature bindings present with matching IDs.
- **E: PASS** — all contract IDs (80/81 static + 1 on-demand with exact id), classes, 3 vars, `__testHooks` (12 hooks), and pinned strings intact; all 7 JS files pass `node --check`; 44 frontend pytest cases green; no duplicate HTML ids.
- **Git-diff sanity: PASS** with 2 dead-code cleanup notes (duplicate legacy CRT CSS blocks; stale `[data-theme="light"]` values) — neither styles anything in any mode.
- Overall confidence: **93/100** (runtime pixel-level rendering, console exceptions in a real browser, and light-theme visual behavior are outside this code review and belong to reviewers A/D/F).
