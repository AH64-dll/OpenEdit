# Stage 3 Code Review R4 — OpenEdit Review Studio (Redesign)
Reviewer: review-code R4 (DeepSeek V4 Flash) · Round 4 · Date: 2026-08-07
Scope: re-review of R3's single residual (rail presentation) — the coordinator's scoped override block appended at the END of style.css (`.renders-list .render-card` + thumb/sub flex + status colors) — plus full syntax gate, full contract sweep, and regression check since R3.
Sources: open_edit/serve/static/{app.js,style.css,index.html}, js/{api,assets,chat,dom,state,ws}.js, testrun/ui/CONTRACT.md, testrun/ui/REVIEW_CODE_R3.md, git state, file mtimes (R3→R4 delta = style.css only, mtime 01:26:04 vs R3's 01:14:30), postcss parse, headless Chromium 133 cascade probe.

---
## Summary
| # | Item | Verdict | Confidence |
|---|---|---|---|
| 1 | Appended override block: syntax, scoping, no chat impact, no NEW dead selectors | **PASS** (3 non-blocking notes, 0 introduced by this change) | 99% |
| 2 | `node --check` 7/7 + contract sweep (IDs, classes, 12 `__testHooks`, pinned strings, 3 inline vars) | **PASS** | 100% |
| 3 | Overall — remaining concerns | **PASS** — 1 pre-existing hygiene nit (line 2015 editor artifact, predates R3, browser-harmless, not introduced here) | 98% |

---

## 1. Appended override block (style.css 2992–3027) — PASS

### 1a. Syntax — PASS
- Block is 8 selectors / 7 rules; braces 7 open / 7 close, balanced; standalone postcss parse of lines 2992–3027: **clean, no errors**.
- Every declaration is valid; all 8 custom properties used (`--oe-ink-2, --oe-surface-2, --oe-line, --oe-radius-md, --oe-ink-muted, --oe-warn, --oe-danger, --oe-success`) are defined in the final winning `:root` (line 2275) with valid values (`#b8b8bd`-chain, `#353539`, `rgba(255,255,255,.14)`, `12px`, `#85858b`, `#eab308`, `#dc2626`, `#16a34a`).
- Full-file postcss parse reports exactly ONE issue, at line 2015:91 — **outside** the block, pre-existing (see §3).

### 1b. Scoping — PASS (verified in a real browser engine)
- Every one of the 8 selectors is rooted at `.renders-list` — the block cannot match any element outside the renders rail.
- The class `renders-list` exists in exactly ONE place in the entire source: `<div id="renders-list" class="renders-list">` (index.html); no JS file ever sets or references the class (app.js touches only the `#renders-list` ID). So `.renders-list …` is unambiguous and airtight.
- Cascade wins, confirmed via headless Chromium 133 computed styles (DOM built exactly as app.js `renderRendersList` emits):
  - Rail card: `width:100%` (800px in probe), `max-width:none` (beats 2796's `min(90%,680px)`), `grid-template-columns:34px 1fr` (736px), `gap:8px`, `padding:8px 10px` (beats 2796's `7px 9px`), `color:rgb(184,184,189)` = `--oe-ink-2` (beats 2803's green tint), `border:1px solid var(--oe-line)`, `border-radius:12px`, `align-self:stretch` (beats 2796's `flex-start`), `display:grid`, `cursor:pointer`. All 0-2-0 selectors appear later in the file than the 0-1-0 chat rules → they win on every property they set.
  - Thumb/sub visibility: `.renders-list .render-thumb/.render-sub { display:flex !important }` (0-2-0, later) beats the legacy `display:none !important` rules at 1826/2048 (0-2-0) — same specificity, later in source → **wins**. Probe: thumb `display:flex`, font-size 14px, sub `display:flex`, `flex-wrap:wrap`, `gap:4px 8px`.
  - Status colors: running thumb `rgb(234,179,8)` = `--oe-warn` ✓, failed `rgb(220,38,38)` = `--oe-danger` ✓, succeeded `rgb(22,163,74)` = `--oe-success` ✓ (0-3-0 beats 2635's 0-1-0 thumb color).

### 1c. No unintended effects on chat `.tool-card` / `.render-card` — PASS
- Chat's render-event card (`appendRenderEvent`, chat.js) emits `.render-card` with `.render-icon` **inside `#chat-log`** — it has no `.renders-list` ancestor, so none of the 8 selectors can match it. Same for `.tool-card`.
- Headless probe of a chat `.render-card` and `.tool-card` (built per chat.js): computed styles are **identical to pre-append behavior** — `width:680px` (`min(90%,680px)`), `max-width:88%`, `grid-template-columns:auto 1fr`, `gap:7px`, `padding:7px 9px`, success-tinted `color` (oklab mix from 2803), `align-self:flex-start`, `font-size:10px`. The block changes nothing outside `#renders-list`.

### 1d. No NEW dead selectors — PASS
- R3→R4 delta is bounded to the appended block: style.css mtime 01:26:04 (R3's was 01:14:30); all other files untouched since R3; every rule R3 quoted (2619/2633/2634/2662/2663/2796/2803/1822–1831/2044–2053/937–982) is byte-identical at the same line numbers → lines 1–2991 unchanged.
- All 8 new selectors match live DOM: `.renders-list` (index.html) + `.render-card`, `.render-thumb`, `.render-sub`, `.render-status-running|failed|succeeded` (all emitted by `renderRendersList`, app.js). 0 dead selectors added. (Dead count strictly decreased vs R3? No — R3's block was identical; the fix added only live selectors, so the pre-existing dead `.render-item` block at 938–982 remains the only dead code, unchanged and harmless.)

### 1e. Non-blocking notes (NOT introduced by this block)
- **N1:** rail cards still inherit `font-size:10px` from the 2796 chat rule (block sets no font-size on the card). Visual impact nil: `.render-name` sets 12px/600 and `.render-sub` sets `font:10px/1.25 mono` on their own elements; the 10px only affects the card's anonymous text nodes (none). Cosmetic only.
- **N2:** `animation: fadeInUp` from legacy 774 still applies to rail cards (pre-existing since before R3; block doesn't set `animation`). Harmless entrance animation.
- **N3:** `queued` renders have no thumb tint (block covers running/failed/succeeded only); queued cards show the default `--oe-ink-muted` emoji + "Queued" label — benign default, not a dead selector.

---

## 2. Syntax gate + contract sweep — PASS

### 2a. `node --check` — 7/7 PASS, exit 0, no output
app.js, js/api.js, js/assets.js, js/chat.js, js/dom.js, js/state.js, js/ws.js — all OK.

### 2b. Frontend contract suites (same 8 files as R3)
test_serve_chat_status, test_serve_search_assets, test_serve_cost_badge, test_serve_send_reconnect, test_serve_loading_state, test_serve_module_structure, test_serve_asset_stream, test_review_ui → **44 passed, 0 failed** (exit 0).

### 2c. IDs
- 81 CONTRACT `#id` tokens: 80 present in index.html; the 1 missing, `renders-degraded-warn`, is created on demand exactly as contracted in `refreshRendersList` (app.js: `el('div', { id: 'renders-degraded-warn', class: 'empty-state' })` inserted before `#renders-list`).
- 88 unique real `id="` attributes, **0 duplicates** (regex artifact eliminated with `(?<![\w-])id=`; the 26 apparent dupes are `id=` + `data-od-id=` pairs on the same element).
- `data-od-id`: exactly **30 unique**, set matches the CONTRACT list 1:1.

### 2d. Classes
- All 56 CONTRACT class tokens present in style.css (only exclusion: the false-positive `html` token). Every JS-emitted contract class (msg-user/msg-bot/msg-error, tool-card/gear/tool-body/tool-name/tool-input/tool-result, result-*, render-card, timeline-*, state-machine attrs, body classes, `.open`, `.hidden`) present.

### 2e. 12 `__testHooks`
`window.OpenEdit.__testHooks` = exactly **12** hooks — normalizeAssets, normalizeEdits, normalizeTimeline, normalizeRenders, normalizeNotes, summarizeOpPayload, openAssetPreview, createChatStatus, createCostBadge, appendSearchResults, sendChatMessage, handleSend — exact set match, nothing added/removed.

### 2f. Pinned strings
- `"Review artifact · 640×360"` **×2** (renderRendersList modeLabel; loadRenderInPreview badge) ✓
- `"Source media"` **×1** (preview badge) ✓
- `"Proxy 720p"` / `"540p"` **absent** ✓
- `id="cost-badge"` present ✓

### 2g. 3 inline var names
`--green` → final `#16a34a` ✓ · `--text-dim` → final `#85858b` ✓ · `--border` → final `rgba(255, 255, 255, .14)` ✓ (identical to R1's record).

---

## 3. Overall — PASS with 1 pre-existing hygiene nit

- **Only finding in the whole source:** style.css **line 2015** contains a stray editor annotation token embedded in a real rule:
  `[data-theme="light"] .crt-tv-screen { color: var(--text-primary);[od:file-window offset=2000 returnedLines=147 totalLines=2147] ... }`
  - **Pre-existing, NOT introduced by this round:** its own payload says the file was 2147 lines when written; the file R3 reviewed was already 2991 lines, and the R4 append brought it to 3028. All R3-quoted lines are byte-intact → the token predates R3 (R3 missed it; R3 ran no CSS parser).
  - **Browser-harmless:** headless Chromium error-recovery keeps the rule functional — probe confirms `text-shadow:none` still applies under `[data-theme="light"]`; postcss parse of the artifact-stripped file is fully clean (691 top-level nodes), i.e., it is the file's only irregularity.
  - **Recommendation (cleanup, not a blocker):** delete the token at line 2015 in any future style.css edit round.
- No regressions, no new dead selectors, no chat-impact, contract fully intact, 44/44 suites green, syntax 7/7.

## Verdict
**PASS — all 3 items.** R3's residual (chat 2796 rule constraining the renders rail) is resolved by a well-formed, correctly scoped, cascade-verified override block: it wins every property it targets, restores thumb/sub visibility against the legacy `display:none !important` rules, applies the three status colors, leaves chat `.tool-card`/`.render-card` pixel-identical to before, and adds zero dead selectors. The only source-level wart (line 2015 artifact) is pre-existing, harmless, and outside this change.
Confidence: **98/100** — every claim is source-verified plus engine-verified (postcss + Chromium computed styles + 44 suites). Not 100 only because (a) the line-2015 artifact remains (hygiene nit for a future round, not a defect of this change) and (b) final pixel aesthetics of the rail belong to reviewers D/F's screenshot pass.
