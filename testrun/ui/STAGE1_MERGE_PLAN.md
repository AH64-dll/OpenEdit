# STAGE 1 — Merge Plan: Gap Analysis + Merge Strategy + Logo Design Spec

**Agent:** cur-2 (Study Agent, Stage 1) · **File:** `testrun/ui/STAGE1_MERGE_PLAN.md`
**Date:** 2026-08-07 · **Status:** complete · **Sibling reports (read at write-time):** `STAGE1_REF_TOKENS.md` (ref-1), `STAGE1_REF_LAYOUT.md` (ref-2), `STAGE1_REF_MOTION.md` (ref-3), `STAGE1_CUR_INVENTORY.md` (cur-1) — all cross-checked, consistent with this report (see §8 reconciliation). Coordinator merges all five into `PLAN.md`.
**Mission:** `testrun/ui_PLAN_PROMPT.md` — redesign Review Studio (`open_edit/serve/static/`) toward the reference shell (`/home/amr/Downloads/file/openedit-shell-explorer.html`), **inspired, not copied**, all features must keep working, new monitor=O logo.

---

## 0. Executive summary

- The reference is a **mockup scaffold** (aspect rail + product shell) around an Apple-token / Codex-glass design language. **Only the product shell language ports**; the explorer/aspect-rail chrome does not.
- The current app is a **fully featured, JS-driven ES-module app** (app.js + js/state,dom,api,assets,chat,ws) with a CRT/Linear green-amber skin. Its JS has **zero dependency on computed CSS** — verified: no `getComputedStyle`, no CSS-var reads in JS, only geometry (`clientWidth`, `getBoundingClientRect`) and three inline `var(--…)` strings. **→ A near-total CSS rewrite is LOW RISK.**
- The binding contract is 68 DOM IDs + a set of JS-generated class names + 3 CSS var names (`--green`, `--text-dim`, `--border` used inline in app.js). Keep those and the app keeps working.
- `style.css` (2,156 lines) contains **duplicated legacy blocks** (two copies of `body::before`, `.crt-tv-*`, `.timeline-edit-marker`, …) — the file grew by appending. A clean rewrite is safer than patching.
- Logo: monitor-squircle that **IS** the O, sized via a cap-height ratio against the wordmark. Three implementations specced below (CSS squircle / SVG with stand / CSS ring).

---

## 1. Sources read (directly)

| Source | What was extracted |
|---|---|
| `testrun/ui_PLAN_PROMPT.md` | Mission, non-negotiables (edit-only production edits, dev server stays up, pytest green, no inner O) |
| `Downloads/file/openedit-shell-explorer.html` (59.4 KB) | Full token set, shell CSS, component markup, mockup JS |
| `open_edit/serve/static/index.html` (17.2 KB) | Current markup, all IDs, mode classes |
| `open_edit/serve/static/style.css` (54.4 KB, 2,156 ln) | Full selector inventory (385 rules), token sets, light theme, duplicated legacy blocks |
| `open_edit/serve/static/app.js` (69.1 KB) + `js/{state,dom,api,assets,chat,ws}.js` | Feature inventory, ID/class contract, boot flow, test hooks |
| `tests/_node_harness.py`, `test_serve_loading_state.py`, `test_serve_chat_status.py`, `test_serve_cost_badge.py`, `test_serve_verify_chip.py`, `test_serve_asset_stream.py`, `test_serve_send_reconnect.py` | Test contract: JS-API-only (DOM is stubbed), so HTML changes are test-safe |

> Reconciliation with siblings: values in this report were independently extracted from the same sources and agree with ref-1 (token values), ref-2 (component map), ref-3 (motion/easing/focus/reduced-motion), cur-1 (feature inventory, CRT logo, review-only deployment). One divergence is flagged in §8.

---

## 2. Current frontend — what exists and what must NOT break

### 2.1 Features (must all survive the redesign)

**Topbar:** project select/create/refresh (auto-select single project), provider+model selects (LLM config, agent mode), tools-warn badge, ⌘K command palette, light/dark toggle (real `[data-theme]` overrides), left/right panel toggles (review mode), settings modal (runtimes + BYOK keys), stop button, WS connection dot.
**Left panel:** Assets tab (dropzone drag&drop + upload progress) · Edit graph tab (op list, detail panel, undo/delete, 5 s auto-refresh).
**Center:** preview player (auto-loads proxy/source, stale-proxy detection), empty state, agent chat (log, chat-status pill, cost badge, verify chip, prompt chips, input with Enter/Shift+Enter, Stop, search-assets results inline).
**Right panel:** Renders list (statuses, click-to-preview, refresh, degraded warn), Proxy/Final render buttons + GPU/CPU encoder select (10-min polling), Notes summary + modal, Style section.
**Timeline (DOM-based, richer than reference):** zoomable ruler (2–60 s steps), track rows with clips (video/audio), overlay markers, remotion markers (pending state), edit markers (reverted state), note markers, playhead + click-to-seek, copy-timecode, note-at-playhead, fit-to-window.
**Modes:** review-only (MCP) vs agent; mobile off-canvas panels; WS reconnect (online/focus events); `window.OpenEdit.__testHooks` (pinned by 7+ Node-sandbox tests).

### 2.2 The JS→DOM contract (KEEP THESE — full list)

**68 IDs queried by JS** (`$('#…')` / `querySelector`), grouped:

- Topbar: `project-select`, `btn-new-project`, `btn-refresh-project`, `llm-provider-select`, `llm-model-select`, `llm-tools-warn`, `btn-cmd-k`, `btn-toggle-theme`, `btn-toggle-left-panel`, `btn-toggle-right-panel`, `btn-settings`, `btn-topbar-stop`, `btn-left-panel`, `btn-right-panel`, `conn-status`
- Left: `assets-list`, `dropzone`, `file-input`, `upload-progress`, `edit-graph-list`, `edit-detail-panel`, `edit-detail-kind`, `edit-detail-status`, `edit-detail-author`, `edit-detail-id`, `edit-detail-payload`, `btn-edit-undo`, `btn-edit-delete`
- Center: `preview-player`, `preview-empty`, `preview-mode-badge`, `chat-log`, `chat-input`, `btn-send`, `btn-stop`, `chat-status`, `cost-badge`, `verify-chip` (plus inner `.chat-status-text` / `.cost-badge-text` / `.verify-chip-text` children — chat.js mounts into them)
- Right: `renders-list`, `btn-refresh-renders`, `render-encoder-select`, `btn-render-proxy`, `btn-render-final`, `renders-degraded-warn`, `notes-summary`, `btn-show-notes`
- Timeline: `timeline-timecode-label`, `timeline-duration-label`, `timeline-track-labels`, `timeline-ruler-col`, `timeline-ruler`, `timeline-tracks-area`, `timeline-playhead`, `timeline-empty-msg`, `btn-copy-timecode`, `btn-add-note-playhead`, `btn-timeline-zoom-in/out/fit`
- Modals/chrome: `modal-cmd-k`, `cmd-input`, `cmd-list`, `modal-new-project`, `new-project-name`, `btn-create-project`, `modal-asset-preview`, `asset-preview-title`, `asset-preview-video`, `modal-notes`, `notes-list`, `modal-settings`, `settings-runtimes-list`, `key-anthropic`, `key-openai`, `key-opencode`, `key-antigravity`, `btn-save-settings-keys`, `toast`

**JS-generated classes (CSS must style these; JS never renames them):** `empty-state`, `loading-state`, `spinner`, `asset-card`(+`asset-filename/sub/icon/meta`), `edit-card`(+`edit-kind/summary/status/author/header`, `edit-card-selected`), `edit-detail-field/key/val`, `render-item`(+`render-status-queued/running/failed/succeeded`, `render-thumb/meta/name/sub`), `note-item`(+`note-ts/text`), `msg/msg-user/msg-bot/msg-error`, `tool-card`(+`tool-body/name/input/result/gear`), `search-results*` (head/error/grid/result-*/license-badge/attribution/import-btn/empty/placeholder), `chat-status`/`cost-badge`/`verify-chip` (data-state driven), `cmd-item`(+`active`, `cmd-item-label`), `timeline-ruler-tick`(+`-line`, `-label`), `timeline-track-row`, `timeline-track-label-row`, `track-kind-badge`(.video/.audio), `timeline-clip`(.video-clip/.audio-clip), `timeline-overlay-marker`, `timeline-remotion-marker`(.pending), `timeline-edit-marker`(.reverted), `timeline-note-marker`, `bar/bar-fill` (upload progress), `kbd-badge`, `hidden`, `open` (mobile panels), `dragover` (dropzone).

**CSS-var names used inline in JS (must keep existing names):** `--green`, `--text-dim`, `--border` (3 occurrences in app.js: settings runtime dot, "Not detected" label, timeline track-label placeholder border).

**Structural contracts (CSS + JS):** `html[data-theme=dark|light]`; `body.has-timeline > .site-wrapper` (flex column); `main.layout` grid `var(--sidebar-w) 1fr var(--sidebar-w)`; `body.review-only-mode` + `.agent-only`/`.review-only` + `.panel-left-collapsed`/`.panel-right-collapsed`; `.panel-tabs .tab` + `.tab-content[data-tab=…]`; `.modal` + `.modal-backdrop` + `[data-modal-close]` + `.hidden` (showModal/hideModal rely on `.hidden` display:none — never redefine); `#left-panel`/`#right-panel` + `.open`; `#toast`; `<script type="module" src="/app.js?v=…">` (bump the `?v=` cache-buster on every changed asset); localStorage keys `open-edit-theme`, `open_edit.current_project_id`, `open_edit.conversation_id`; `window.OpenEdit` + `__testHooks` exports.

**Tests are HTML-agnostic:** the Node harness stubs `document` entirely, so index.html can change freely as long as app.js keeps its exports/hooks and the real DOM keeps the IDs above.

---

## 3. Reference design language (what we are porting)

| Token group | Reference value | Port? |
|---|---|---|
| Accent | `#0071e3` / hover `#0077ed` / active `#0066cc` (Apple blue, CTAs only) | ✅ |
| Studio bg | `fg 94% + black` ≈ #1c1c1e; elev-1/2/3 graphite steps; ink 92% white | ✅ |
| Lines | `studio-line` = white 14% alpha; `studio-line-strong` = 22% | ✅ |
| Glass | topbar/panels `backdrop-filter: blur(14–18px)` over `color-mix(elev 70–92%, transparent)` | ✅ |
| Radius | sm 8 / md 12 / lg 18 / pill 980 px | ✅ |
| Elevation | flat ring `0 0 0 1px line`; raised `0 12px 32px rgba(0,0,0,.08)`; shell `0 24px 64px black 45%` | ✅ (reduced for full-bleed app) |
| Type | SF Pro Display/Text (fallback Helvetica) display tracking `-0.015..-0.02em`; SF Mono for timecodes/numbers | ⚠️ keep Inter + JetBrains Mono (metric-near; SF unavailable off-Apple) |
| Type scale | 12/14/17/21/28/40… px; uppercase 10–11 px kicker labels, `letter-spacing .06em` | ✅ |
| Buttons | pill, min-height 28 px, 12 px/600, active `scale(.97)`, focus ring `0 0 0 4px accent@65%` | ✅ |
| Motion | 150/220 ms, `cubic-bezier(.28,0,.22,1)`, softPulse on primary CTAs, `prefers-reduced-motion` kill-switch | ✅ |
| Status | mode badge pill (pulse dot + halo), conn dot 7 px + 3 px halo, status pills (success/warn tints) | ✅ |
| Logo | `.logo-mark` 22×22, radius 7 px (≈31.8%), gradient 145° accent→active, glow `0 4px 12px accent@35%` | ✅ (reworked per mission, §6) |
| Timeline | 22 px ruler, 28 px track rows (24 px density), 6 px gaps, clip gradient + accent border, 2 px playhead + glow | ✅ (restyle current DOM, keep richer markers) |
| Light theme | tokens exist in reference (`--bg:#fff`, `--surface:#f5f5f7`, `--fg:#1d1d1f`, `--border:#d2d2d7`, same blue) | ✅ retint current real light theme |

**Mockup chrome that does NOT port:** `.explorer`/`.aspect-rail`/`.aspect-btn`/`.stage-wrap`/`.stage-header`/`.chip-row`, the `shell[data-aspect=…]`/`[data-mode=…]` attribute state machine, and the mock transport buttons (skip/play) unless we later adopt custom controls.

---

## 4. Gap analysis

### 4.1 What the reference has that the current app lacks (visually + structurally)

| # | Reference | Current | Gap |
|---|---|---|---|
| G1 | Apple-blue neutral graphite palette | CRT green-on-black + amber accents | Full palette replacement (conflict C1) |
| G2 | Hairline translucent borders, glass blur, layered elevation, inner rings | Solid `rgba(51,255,102,.2)` borders, flat opaque surfaces | Replace border/surface system |
| G3 | Squircle radii (8–18 px) + pills | `--radius: 2px` (sharp) everywhere | Replace radius tokens + spot-fix thumbs/progress bars |
| G4 | Stroke SVG icon set (16 px, 1.2–1.3 stroke) | Emoji icons (🌙 ☀️ ⚙️ 🎬 ⏹ ◧ ◨ ☰ ≡ ⏳ 🎞️ ♪ ▶ ⚠) | Swap static topbar buttons to inline SVG (safe); JS-generated emoji can stay or be patched later |
| G5 | Logo: gradient squircle mark + display wordmark | CRT TV icon with a literal **O glyph inside the screen** + "pen Edit" | New monitor=O mark (§6) — also fixes mission violation |
| G6 | Product shell frame (radius 22, border, big shadow, radial accent glow) | Full-bleed edge-to-edge app | Optional/partial: adopt glow + hairline; full frame only if a page background is introduced |
| G7 | Mode badge (Review·MCP / Agent) + inline provider select in topbar center | provider/model selects + tools warn only | Add static badge element (no JS needed initially; wire later) |
| G8 | Preview stage card (radius 20, media backdrop, live badge, empty state with ring icon + CTA button) | Bare `<video controls>` + plain empty text | Wrap player in `.preview-stage` card; restyle empty state (add icon ring + CTA) |
| G9 | Chat as a bounded dock under preview (bubbles, glass, prompt chips, compose) | Chat as full-height column (agent mode) | Keep current placement (feature), restyle to bubbles/glass; reference dock structure is optional |
| G10 | Richer empty states (strong + copy + CTA) | Plain "No assets yet…" text | Copy/visual upgrade (safe — static text or JS-owned `.empty-state` styling) |
| G11 | Uppercase kicker labels, tabular mono timecode, tighter display type | 13.5 px Inter, green mono | Typography pass (tokens + component classes) |
| G12 | Status pills + halo dots; softPulse on CTAs; reduced-motion kill | plain dots + green pulse keyframes | Restyle; add pill styles; keep reduced-motion |
| G13 | Focus ring (4 px accent halo) on all interactive elements | 2 px amber ring | Token swap |
| G14 | Light-mode tokens as first-class Apple light | Real light mode exists but CRT-tinted | Retint `[data-theme="light"]` block |

### 4.2 What the current app has that MUST stay (features the reference lacks entirely)

1. Real backend wiring: project CRUD + select, asset upload, render jobs + polling + stale detection, WS event stream, LLM config + BYOK settings, review-only/MCP mode, auto-proxy.
2. Edit graph list + detail + undo/delete + auto-refresh.
3. Renders list with per-status styling, encoder select, degraded warn, click-to-preview.
4. Notes summary + modal, note-at-playhead, timeline note markers.
5. Rich DOM timeline: zoom, overlay markers, **remotion markers**, **edit markers (reverted)**, seek, copy-timecode, fit.
6. Command palette, chat status/cost/verify chips, prompt chips, search-assets results UI.
7. Real light/dark toggle, mobile off-canvas panels, panel collapse (review mode), film-grain-free alternative aesthetics, `window.OpenEdit` test hooks.
8. The ES-module architecture (`js/*.js` imports) — do NOT merge files or change the module graph; tests import `app.js` by path.

### 4.3 Conflicts (must be resolved explicitly)

- **C1 CRT identity vs Apple/glass:** green-amber palette, `--radius:2px`, film grain (`body::after` noise), scanline flicker keyframes, CRT logo — all directly contradict the reference. → Delete grain/flicker/CRT blocks; replace palette+radius wholesale. The reference itself ships the chip "**CRT retired**".
- **C2 Emoji vs stroke SVG:** static buttons can be swapped safely; JS-generated icons (`render-thumb` ⏳/🎞️, cmd palette emoji, `edit-kind` icons, dropzone SVG) — patch only if time permits; emoji in those is not a rubric blocker.
- **C3 Richer-current vs simpler-reference timeline:** the reference timeline is a *simplified* mock. Restyle the current DOM; do NOT drop markers/density. Also do NOT port the reference's flex-span ruler (current ruler is JS-generated absolute ticks at px positions).
- **C4 Mockup chrome vs product:** aspect rail, stage header chips, `data-aspect` states are scaffolding. Copying them into the product would add dead UI. Exclude (call out in PLAN.md so Stage 2 workers don't port them).
- **C5 Reference logo optical mismatch:** reference `.logo-mark` 22 px sits next to a 14 px wordmark (O ≈ 10 px cap) — the mission **overrides** this: mark must optically equal a capital O (~22–26 px). → cap-height-ratio sizing (§6).
- **C6 Chat placement:** reference docks chat under the preview; current uses a full-height chat column (agent mode). Keep current placement (it's a feature with status/cost/verify mounts) — restyle only.
- **C7 Current light theme:** the reference mockup only renders dark, but its token file defines light. Keep the real light toggle and retint with Apple light tokens (don't delete the mechanism).
- **C8 `--topbar-h:44px`:** the new logo needs a taller bar (≈52 px). `.layout` height is `calc(100vh - var(--topbar-h))` — change the token, not the rule.

---

## 5. Merge strategy (port reference language with MINIMAL JS breakage)

### 5.1 Core principle

**CSS is a free variable; HTML IDs/classes and JS are the contract.** Verified: JS never reads computed styles or CSS vars; it only toggles classes/attributes and measures layout boxes. So:

> **Replace ~95% of style.css wholesale; edit index.html only in the "safe" list below; patch app.js in exactly 1 place (theme-toggle icon) — optionally 2 (nothing else required).**

### 5.2 Reference-component → existing-DOM-hook map

| Reference component | Current hook (keep) | Action |
|---|---|---|
| `.topbar` (blur, 1fr auto 1fr) | `header.topbar` + `.topbar-left/center/right` | Restyle only (markup already matches) |
| `.logo` + `.logo-mark` | `#logo` (`span.logo` + `.crt-tv-icon` + `.logo-text`) | Replace internals with new mark (§6). JS never touches logo (verified) |
| `.project-select` pill (select + meta) | `#project-select` bare `<select>` | Wrap in pill `<label>`; keep ID on the `<select>` |
| `.mode-badge` + `.conn` | `#conn-status` dot; add `.mode-badge` (new, static) | Restyle conn; add badge element (no JS) |
| `.btn` family | `.btn`, `.btn-primary/secondary/ghost/outline/danger`, `.btn-xs/sm`, `.kbd-badge` | Restyle (names identical) |
| `.workspace` grid | `main.layout` grid | Restyle via `--sidebar-w` tokens (240/1fr/260) |
| `.panel-left/right/center` | same classes | Restyle only |
| `.rail-tabs/.rail-tab` | `.panel-tabs .tab` + `.tab-content[data-tab]` | Restyle only (JS binds these exact selectors) |
| `.panel-head/.panel-title` | `.panel-section-header` (right rail), `.preview-panel-header`, `.timeline-panel-header` | Restyle; may add `.panel-head` wrappers (safe) |
| `.asset-drop` | `#dropzone` | Restyle (dashed pill card), keep `dragover` class + ID |
| `.list-item` (thumb/copy/meta) | `.asset-card`, `.edit-card`, `.render-item`, `.note-item` | Restyle each to the list-item look (keep class names — JS creates them) |
| `.empty-inline` | `.empty-state` | Restyle (JS creates `.empty-state` in 6 places) |
| `.preview-stage/.preview-media/.preview-badge` | `#preview-panel` > `video#preview-player` + `#preview-empty` | Wrap video in a `.preview-stage` div (safe: JS refs only the video ID); restyle header + empty state; keep `body.review-only-mode .preview-panel{flex:1}` semantics |
| `.agent-dock/.bubble/.chat-compose` | `#chat-log` + `.msg/.msg-user/.msg-bot` + `#chat-input` + `#btn-send` | Restyle messages as bubbles; keep IDs/classes |
| `.prompt-chips` | `.prompt-chips-container .prompt-chip[data-prompt]` | Restyle (keep data-prompt) |
| `.render-actions` grid | `.render-buttons.compact-renders` | Restyle |
| `.status-pill` | `.verify-chip` (+`data-state`), render status colors | Restyle; keep data-state contract |
| `.timeline-*` | `.timeline-panel` / `-header` / `-timecode` / `-body` / `-track-labels` / `-ruler-col` / `-ruler` / `-tracks-area` / `-track-row` / `-clip` / `-playhead` + all markers | Restyle only; JS generates this DOM with inline px styles — never switch to % or flex-span layout |
| `.toast` | `#toast` | Restyle |
| — (new) | `#toast`/modals | Restyle `.modal-card`, `.text-input`, `.cmd-palette-card`, `.notes-list`, settings blocks |

### 5.3 CSS: replace wholesale vs surgical

**WHOLESALE (rewrite in new style.css):** everything except the blocks below. The rewrite should be structured: tokens → light overrides → base → topbar → buttons → layout/panels → lists/cards → chat → timeline → modals → toast → responsive → reduced-motion. **Use the §2.2 class inventory as the completeness checklist** (style every class JS can emit).

**SURGICAL / keep-alive rules for the rewrite:**
1. Keep var names `--green`, `--text-dim`, `--border` (JS inline usage) — alias them to new-token values (e.g., `--green: var(--success)`).
2. Keep `.hidden { display:none !important }` (modal machinery).
3. Keep `body.review-only-mode` visibility rules + `.agent-only`/`.review-only`/`.mobile-only` semantics.
4. Keep `body.has-timeline .site-wrapper` column layout + `main.layout` grid + `--sidebar-w`/`--topbar-h` tokens (change values, not names).
5. Delete: film grain (`body::after` noise), scanline/flicker keyframes, `.crt-tv-*` blocks, duplicated legacy tail blocks.
6. `@keyframes pulse` for status dots must survive (ws.js-driven `.conn-status` classes animate via CSS) — restyle, don't remove.

### 5.4 Markup changes — SAFE list (index.html edits that cannot break JS)

1. `#logo` internals (`.crt-tv-icon` → `.logo-mark`; keep `#logo`, add `aria-label="Open Edit"`). **Verified: no JS references logo internals.**
2. Static button icon content (emoji → inline SVG) for: `btn-refresh-project`, `btn-cmd-k`, `btn-send`, `btn-refresh-renders`, `btn-toggle-left-panel`, `btn-toggle-right-panel`, `btn-left-panel`, `btn-right-panel`, `btn-topbar-stop`, `btn-settings`. Keep all IDs. **Exception:** `#btn-toggle-theme` — `applyTheme()` sets `textContent = '🌙'|'☀️'` → either keep the emoji or patch that one line (recommended: patch to swap two inline SVGs via `innerHTML`, or keep text-based and style it).
3. Wrap `#project-select` in a `<label class="project-select">` pill (ID stays on the `<select>`; JS binds change on the ID only).
4. Add `.preview-stage` wrapper around `#preview-player` (JS refs the video by ID; CSS selectors in the "review-only-mode" block target `.preview-panel`, which stays).
5. Add static `.mode-badge` element in `.topbar-center` (no JS wiring needed; can be wired in Stage 2 phase 3).
6. All static copy: empty states, panel headers, footer hints, welcome screen, modal headings, `<title>`, meta, font links.
7. Adding wrapper divs inside panels (e.g., `.panel-head`, `.section-block`) — safe as long as listed IDs/classes remain queryable and `.tab-content[data-tab]` structure is untouched.
8. Reordering children inside `.topbar-left/center/right` (flex) — safe.

**UNSAFE (do not touch without JS changes):** any ID in §2.2's list; `.panel-tabs .tab` / `.tab-content[data-tab]`; `.agent-only`/`.review-only`/`.mobile-only`/`.hidden`; `.modal`/`.modal-backdrop`/`[data-modal-close]`; `#toast`; `<html data-theme>` + `body.has-timeline`/`.site-wrapper`/`main.layout`; the `<script type="module" src="/app.js…">` tag; localStorage key names; `window.OpenEdit`.

### 5.5 app.js changes (complete list — keep minimal)

| # | Change | Why | Risk |
|---|---|---|---|
| J1 | `applyTheme()` icon swap (1 line) | theme-toggle button icon becomes SVG | none |
| J2 (optional) | bump `?v=` cache-buster on style.css/app.js links in index.html | avoid stale cache | none |
| J3 (optional) | wire mode badge label from `state.reviewOnly` (1–2 lines in `boot()`) | new topbar badge | low |
| J4 (optional) | JS-generated emoji → SVG for `render-thumb` (`⏳`/`🎞️`) and cmd palette icons | polish | low |
| J5 (do NOT) | do not rename/merge modules, do not touch `window.OpenEdit`/`__testHooks` | test contract | — |

Everything else is CSS.

---

## 6. LOGO DESIGN SPEC (most important deliverable)

### 6.1 Requirements (from mission + plan prompt)

1. Reads **"Open"**: wordmark = `[monitor-mark]` + `"pen Edit"` (current `.logo-text` stays `pen&nbsp;Edit` → "Open Edit").
2. The mark is a **monitor/screen with rounded corners that IS the letter O** — a rounded square that reads as both. **No letter "O" glyph anywhere inside the monitor.**
3. **Optical sizing:** mark height = capital-O cap-height of the wordmark font. Target **22–26 px** canonical.
4. Style must match reference: Apple blue gradient, radius ≈30% (ref: 7 px on 22 px), elevation/glow (`0 4px 12px accent@35%`), glass (inner screen sheen).

### 6.2 Typography math (the sizing contract)

- Inter (current app font; keep): **cap-height = 0.728 em** (1491/2048). SF Pro ≈0.70–0.73; Helvetica ≈0.72.
- Rule: `--logo-font-size = --logo-mark-size / 0.728`.
- Canonical sets:
  - Topbar: mark **22 px** → wordmark font ≈ **30.2 px** (topbar grows `--topbar-h` 44 → 52 px).
  - Hero/welcome: mark **24 px** → wordmark ≈ **33 px**.
  - Dense fallback (explicit deviation, only if layout forces): mark 18 px → font ≈ 24.7 px; flag in REVIEW_RUBRIC if used.
- Calibration: if the font stack resolves to something other than Inter (e.g., SF on macOS via fallbacks), adjust `--logo-cap-ratio` in one place (0.70–0.73).

### 6.3 Mark geometry (shared anatomy, all options)

- Outer: **square, side = mark size** (22–24 px), `border-radius ≈ 0.30 × size` (squircle corner; 6.6–7.2 px).
- Fill: `linear-gradient(145deg, #4da3ff 0%, #0071e3 45%, #0057b8 100%)` (Apple blue, richer at top-left).
- Bezel: inner ring `inset 0 0 0 1.5px rgba(255,255,255,.22)` + top sheen `inset 0 2px 3px rgba(255,255,255,.25)`.
- Screen glass (the monitor's display — NOT a glyph): inner rounded rect at `inset ≈ 0.21 × size` (≈5 px), `border-radius ≈ 0.17 × size`, gradient `rgba(255,255,255,.34)→.10→.03→rgba(0,0,0,.16)` at 155°, inner glow.
- Elevation: `0 4px 12px rgba(0,113,227,.35)` (glow) — reference-consistent.
- No stand at 22–24 px (adds noise; stand only in the SVG option ≥24 px and in large hero usage).
- The O-read: the rounded square's silhouette = a capital O; the glass inset mirrors an O counter without drawing a glyph.

### 6.4 Option A — Pure CSS squircle-screen (RECOMMENDED DEFAULT)

Zero markup beyond one span; fully themeable via CSS vars; no asset/ID collisions.

**Markup (replaces `.crt-tv-icon` block in `index.html`):**
```html
<a class="logo" id="logo" data-od-id="logo" aria-label="Open Edit">
  <span class="logo-mark" aria-hidden="true"></span>
  <span class="logo-text">pen&nbsp;Edit</span>
</a>
```

**CSS:**
```css
/* Logo sizing contract: mark == cap-height of wordmark */
.logo {
  --logo-mark-size: 22px;              /* topbar; 24px for hero */
  --logo-cap-ratio: 0.728;             /* Inter cap-height / em; calibrate 0.70–0.73 */
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: calc(var(--logo-mark-size) / var(--logo-cap-ratio));  /* ≈30.2px */
  line-height: 1;
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--text);                  /* new studio ink token */
  text-decoration: none;
}

/* The mark: a monitor squircle that IS the letter O (no inner O glyph) */
.logo-mark {
  width: var(--logo-mark-size);
  height: var(--logo-mark-size);
  flex: 0 0 auto;
  position: relative;
  display: inline-block;
  border-radius: calc(var(--logo-mark-size) * 0.30);          /* ≈6.6px */
  background: linear-gradient(145deg, #4da3ff 0%, #0071e3 45%, #0057b8 100%);
  box-shadow:
    inset 0 0 0 1.5px rgba(255, 255, 255, 0.22),              /* bezel ring */
    inset 0 2px 3px rgba(255, 255, 255, 0.25),                /* top sheen */
    0 4px 12px rgba(0, 113, 227, 0.35);                       /* accent glow */
}
/* Screen glass — the monitor display, not a glyph */
.logo-mark::after {
  content: "";
  position: absolute;
  inset: calc(var(--logo-mark-size) * 0.21);                  /* ≈4.6px bezel */
  border-radius: calc(var(--logo-mark-size) * 0.17);          /* ≈3.7px */
  background: linear-gradient(155deg,
    rgba(255, 255, 255, 0.34) 0%,
    rgba(255, 255, 255, 0.10) 38%,
    rgba(255, 255, 255, 0.03) 55%,
    rgba(0, 0, 0, 0.16) 100%);
  box-shadow: inset 0 0 6px rgba(255, 255, 255, 0.18);
  pointer-events: none;
}
/* Light theme: same blue, slightly lighter glow */
[data-theme="light"] .logo-mark {
  box-shadow:
    inset 0 0 0 1.5px rgba(255, 255, 255, 0.35),
    inset 0 2px 3px rgba(255, 255, 255, 0.40),
    0 4px 12px rgba(0, 113, 227, 0.28);
}
```
Notes: `--logo-mark-size` is the single scaling knob — topbar (22) vs hero (24) both keep the optical match automatically. `aria-hidden` on the span; the link carries the accessible name.

### 6.5 Option B — Inline SVG monitor with stand (best fidelity / scalable)

For hero placements ≥24 px and anywhere a stand strengthens the "monitor" read. viewBox keeps the body a rounded square = O.

**Markup + SVG:**
```html
<a class="logo logo--svg" id="logo" data-od-id="logo" aria-label="Open Edit">
  <svg class="logo-mark" viewBox="0 0 24 24" width="22" height="22"
       aria-hidden="true" focusable="false">
    <defs>
      <linearGradient id="oeLogoGrad" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#4da3ff"/>
        <stop offset="0.45" stop-color="#0071e3"/>
        <stop offset="1" stop-color="#0057b8"/>
      </linearGradient>
    </defs>
    <!-- Monitor body = the O: rounded square, NO inner O glyph -->
    <rect x="1.2" y="2" width="21.6" height="17.4" rx="6.5" fill="url(#oeLogoGrad)"/>
    <rect x="1.2" y="2" width="21.6" height="17.4" rx="6.5" fill="none"
          stroke="rgba(255,255,255,0.30)" stroke-width="0.9"/>
    <!-- Screen glass -->
    <rect x="5.4" y="5.6" width="13.2" height="10.2" rx="3.4" fill="rgba(255,255,255,0.22)"/>
    <path d="M5.4 6.6c2.6-0.9 6.4-1.2 13.2-0.2v1.5c-6.8-1.1-10.4-0.7-13.2 0.2z"
          fill="rgba(255,255,255,0.30)"/>
    <!-- Stand (optional: delete for pure squircle) -->
    <rect x="10.6" y="19.4" width="2.8" height="2.2" rx="0.7" fill="url(#oeLogoGrad)"/>
    <rect x="8.2" y="21.6" width="7.6" height="1.6" rx="0.8" fill="url(#oeLogoGrad)"/>
  </svg>
  <span class="logo-text">pen&nbsp;Edit</span>
</a>
```
```css
.logo--svg .logo-mark {
  width: var(--logo-mark-size);
  height: calc(var(--logo-mark-size) * 0.94);  /* body incl. stand ≈ 22/23.4; tune optically */
  filter: drop-shadow(0 4px 12px rgba(0, 113, 227, 0.35));
}
```
Exact geometry: body x 1.2→22.8 (21.6 w), y 2→19.4 (17.4 h), rx 6.5 (30% of body height); glass inset 4.2/3.6 px; stand 8.2→15.8 × 21.6→23.2. **Warning:** gradient IDs must be unique per page — if the mark appears twice (topbar + hero), suffix the id (`oeLogoGradTop`, `oeLogoGradHero`) or move `<defs>` to a single hidden svg. This option reads most clearly as a monitor; the O-read is via the rounded-square body silhouette.

### 6.6 Option C — CSS ring monitor (strongest O letterform, bolder read)

The monitor is drawn as an outline (gradient border) with a translucent glass center and a small stand — the hollow rounded square reads as a capital O even at small sizes. **Flag:** the transparent center is the screen, not a glyph, but this is the option most likely to trip a strict "no inner O" review — verify against rubric item B; use A/B as default.

**Markup:** same as Option A (`<span class="logo-mark logo-mark--ring">`).

**CSS:**
```css
.logo-mark--ring {
  width: var(--logo-mark-size);
  height: calc(var(--logo-mark-size) * 0.94);
  border-radius: calc(var(--logo-mark-size) * 0.30);
  border: 2.2px solid transparent;
  background:
    linear-gradient(var(--bg-surface), var(--bg-surface)) padding-box,
    linear-gradient(145deg, #4da3ff, #0057b8) border-box;   /* gradient ring */
  box-shadow: 0 4px 12px rgba(0, 113, 227, 0.35);
  position: relative;
  display: inline-block;
}
.logo-mark--ring::after {          /* glass screen (not a glyph) */
  content: "";
  position: absolute;
  inset: 4.5px;
  border-radius: calc(var(--logo-mark-size) * 0.15);
  background: linear-gradient(160deg,
    rgba(0, 113, 227, 0.20) 0%, rgba(255, 255, 255, 0.06) 60%, transparent 100%);
}
.logo-mark--ring::before {         /* stand */
  content: "";
  position: absolute;
  left: 50%;
  bottom: -4.5px;
  transform: translateX(-50%);
  width: 34%;
  height: 4px;
  border-radius: 2px;
  background: linear-gradient(90deg, #0057b8, #4da3ff);
}
```
Note: the stand pokes below the em box — add `margin-bottom: 4.5px` on `.logo` when using this option so the wordmark baseline stays aligned.

### 6.7 Logo do/don't checklist (for Stage 2 + reviewers)

- ✅ Do keep `.logo-text` exactly `pen&nbsp;Edit` (mark supplies the "O").
- ✅ Do size via `--logo-mark-size` + `--logo-cap-ratio` (never hand-tune font-size independently).
- ✅ Do verify optical match in a screenshot at 2× zoom (topbar + hero) before sign-off.
- ✅ Do give the mark `box-shadow` glow + bezel + glass sheen (reference style: colors/gradient/radius/elevation/glass).
- ✅ Do add `aria-label="Open Edit"` on the logo link, `aria-hidden="true"` on the mark.
- ❌ Never render a letter "O" (text or path) inside the monitor.
- ❌ No "OE" initials inside the mark (reference mock has them; mission forbids an inner glyph — the monitor IS the O).
- ❌ No scanline/CRT styling on the mark.
- ❌ Don't mix options: pick A (default) or B per placement; C only with explicit rubric sign-off.

---

## 7. Stage 2 implementation order + risk notes

**Recommendation: interleaved, style-first with a token gate — not strict waterfall.** CSS has zero JS coupling (verified §5.1), so the design can land before backend work; but the logo + theme-icon touch 1 line of JS, so the two orchestrators must coordinate on `index.html` ownership.

### Phase 0 — Token gate (Orchestrator A, ~30 min; both orchestrators wait)
Replace `:root` + `[data-theme="light"]` tokens with the Apple-derived set (§3) **while aliasing legacy names** (`--green`, `--text-dim`, `--border`, `--radius`, `--sidebar-w`, `--topbar-h`, `--font-sans`, `--font-mono`). Delete grain/scanline/CRT blocks. **Gate:** app renders with new colors, old layout; screenshot; pytest quick pass.
*Risk: low. Watch:* aliases for the 3 JS-inline vars; `.hidden` untouched.

### Phase 1 — CSS-only component restyle (A, 1 worker)
All component styling per §5.2 map, using §2.2 class inventory as the checklist (every JS-emitted class must be styled). No markup edits.
*Gate:* screenshot review vs reference (Luna vision); functional smoke (project select → assets → render → timeline) unchanged.
*Risks:* missing a JS-emitted class (unstyled but functional — catch in review); accidentally redefining `.hidden` or review-only visibility rules; timeline markers.

### Phase 2 — Safe markup pass (A, 1 worker; B watches)
Apply §5.4 safe edits: logo (§6 Option A), SVG icon swaps, project-select pill, preview-stage wrapper, mode badge, empty-state copy. **One coordinated JS patch (J1)** by the worker who owns app.js. Bump `?v=` cache-busters.
*Gate:* full browser smoke; logo optical-match screenshot (rubric B).
*Risks:* theme-toggle icon regression (J1 is 1 line — test toggle in both themes); preview wrapper must keep `body.review-only-mode .preview-panel{flex:1}` working; never touch §2.2 IDs.

### Phase 3 — Backend-connect verification + polish (B, 2 workers; A reviews)
Run the real stack: dev server on 8000, project select/create, upload, proxy/final render, preview streaming, renders list, notes, chat send + WS status/cost/verify chips, cmd palette, settings/BYOK, review-only mode. `pytest tests/ -q --timeout=120 -p no:cacheprovider` must stay green. Optional J3/J4 polish (mode badge wiring, JS emoji→SVG) — only after functional sign-off.
*Gate:* all features verified end-to-end; tests green.
*Risks:* WS/chat is the most JS-coupled surface — do not restructure chat DOM (keep `#chat-log`, mounts); review-only vs agent mode class rules.

### Why not strict "style first, then backend"?
The 1-line JS patch (theme icon) and the logo markup land in Phase 2; if backend work started only after all styling, those touchpoints would be discovered late. Interleaving phases 1–2 (A) with B's regression watch keeps breakage surface tiny. Keep a shared `testrun/ui/` scratch for screenshots + a `CHANGES.md` log so the two orchestrators don't edit index.html/app.js simultaneously (file-lock by convention: A owns index.html/style.css, B owns app.js until Phase 3 hands it back).

### Risk register (consolidated)

| # | Risk | Mitigation |
|---|---|---|
| R1 | Forgetting legacy var aliases (`--green`, `--text-dim`, `--border`) → broken settings modal + timeline placeholder | Phase-0 alias checklist; grep `var(--` in js/ |
| R2 | Full CSS rewrite drops JS-emitted classes (`.loading-state`, `.timeline-remotion-marker`, `.search-results-*`, `.verify-chip`, …) | §2.2 inventory as style-completeness checklist |
| R3 | Porting mockup chrome (aspect rail, `data-aspect`, chips) into product | Explicit exclusion list in PLAN.md + rubric |
| R4 | Timeline restyle breaking JS layout (inline px positions, absolute ticks) | Restyle only; no %/flex-span conversion; keep `.timeline-ruler-tick` positioning |
| R5 | Logo optical mismatch (mark ≠ cap-O) or accidental inner O | §6 spec; screenshot at 2×; rubric item B |
| R6 | Theme-toggle button breaks after emoji→SVG swap | J1 patch with `applyTheme`; test both themes |
| R7 | Chat/WS regression from restyling (mount points `.chat-status-text`, `.cost-badge-text`, `.verify-chip-text`, data-state attrs) | Don't move mounts; keep IDs; Phase-3 end-to-end chat test |
| R8 | `--topbar-h` change breaks `.layout` height calc | Change token value only |
| R9 | Stale caches during dev | Bump `?v=` on style.css/app.js at each phase gate |
| R10 | Both orchestrators editing index.html/app.js concurrently | Ownership convention + shared CHANGES.md in `testrun/ui/` |

---

## 8. Reconciliation with sibling STAGE-1 reports

All five reports agree on: token values (`--accent:#0071e3`, radii 8/12/18/pill, graphite `--studio-*` scale, white-alpha hairlines, blur 10–18 px), motion (150/220 ms, `cubic-bezier(.28,0,.22,1)`, `scale(.97)`, 4 px focus ring, reduced-motion nuke, breakpoints 1100/900 px), the current CRT skin + literal-O logo being the top mission violation, and the JS/DOM contract (§2 here == cur-1's inventory).

**One flagged divergence — the `data-aspect`/`data-mode` attribute system:** ref-2 calls the reference's attribute-driven visibility "a core design idea to port"; this report treats it as mockup scaffolding (C4). Adjudication for PLAN.md:
- The **concept** is already implemented in the current app via body classes (`review-only-mode`, `.agent-only`, `.review-only`, `.panel-*-collapsed`) — no port needed for functionality.
- Optional zero-risk gesture: add `data-mode="review|agent"` on `<body>` in `boot()` (1 line, alongside the existing `review-only-mode` class) so CSS can use attribute selectors if the new skin wants it. **Do not** port the full `data-aspect` state machine (5 states, localStorage, mock actions) — it has no product meaning here.

Also from cur-1: the deployed server runs `--review-only` (mode=review), so Stage 2 must smoke-test review-only mode first and agent mode second; the review-only visibility rules (§5.3.3) are the highest-risk CSS to touch.

---

## 9. Verification checklist (maps to REVIEW_RUBRIC items)

- [ ] A: screenshot diff vs reference for: topbar, buttons, panels, list items, timeline, modals, empty states (Luna vision review).
- [ ] B: logo = monitor squircle; NO inner O glyph; mark height ≈ cap-height of wordmark (22–26 px); gradient/radius/glow/glass match reference style; reads "Open Edit".
- [ ] C: every §2.1 feature works; `pytest tests/ -q --timeout=120 -p no:cacheprovider` green; dev server smoke on 127.0.0.1:8000.
- [ ] D: no JS changes beyond J1–J4; `window.OpenEdit.__testHooks` intact; no module-graph changes; no IDs removed.
- [ ] E: verdict format per rubric; loop until 100% PASS.
