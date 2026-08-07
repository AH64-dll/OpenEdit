# STAGE 1 — Reference Layout & Components Study (ref-2)

**Source studied:** `/home/amr/Downloads/file/openedit-shell-explorer.html` (OpenEdit Review Studio — Shell Explorer, high-fidelity mock)
**Compared against:** `open_edit/serve/static/index.html` (current Review Studio)
**Mission doc:** `testrun/ui_PLAN_PROMPT.md`
**Date:** 2026-08-07 (stage-1 parallel study)

---

## 0. Big picture

The mockup is a **dark glass "Apple × Codex × NLE" studio shell**. The whole page is a two-column `explorer` grid:
`220px aspect-rail` (a **demo-only navigation** that switches between 5 mock "aspects": loaded / empty / agent / controls / density) + a
flex `stage-wrap` holding a `stage-header` (page title + token chips) and the actual **product shell** (`#shell`).

The product shell itself is a rounded, bordered, shadowed card (`border-radius:22px`, `backdrop-filter` glass panels) with a **3-row grid**:

```
shell grid rows:  48px topbar  |  minmax(0,1fr) workspace  |  auto timeline-panel
```

`data-aspect` / `data-mode` on `#shell` drive show/hide of states (`review` vs `agent`, `filled-only` vs `empty-only`, `density-only`, `review-only-ui` vs `agent-only-ui`). These data-attribute visibility switches are a core design idea to port.

---

## 1. Top bar (`header.topbar`, grid `1fr auto 1fr`, 48px, blurred glass)

**Left — `topbar-left`:**
| element | class | purpose |
|---|---|---|
| logo link | `logo` > `logo-mark` ("OE") + text **"open Edit"** | brand. NOTE: mark is a plain rounded tile w/ letters; mission spec supersedes (monitor-shape = O). Current app has `crt-tv-icon` with a literal "O" inside — must be replaced per mission non-negotiable |
| project select | `label.project-select` > `select#project-picker` + `span.meta#project-meta` ("1 asset") | inline project dropdown **with asset-count meta inline** |
| new project | `button.btn.btn-ghost.btn-xs#btn-new-project` ("+ New") | ghost text CTA next to the select (replaces current separate label/select/refresh trio) |

**Center — `topbar-center` (auto width, centered):**
| element | class | purpose |
|---|---|---|
| mode badge | `span.mode-badge` > `span.pulse` + `span#mode-label` ("Review · MCP" / "Agent · built-in") | **pill status badge with pulsing dot** — does NOT exist in current UI (current only has a colored conn dot) |
| provider select | `select.project-select` in `div.agent-only-ui.icon-btn-row` | agent-only compact provider dropdown (Claude/GPT/Local) — no model select in ref |

**Right — `topbar-right`:**
| element | class | purpose |
|---|---|---|
| connection status | `span.conn` > `<i>` + "Connected" | text + dot connection readout (current: bare colored dot) |
| command palette | `button.btn.btn-ghost.btn-icon#btn-cmd-k` (⌘ grid svg) | icon-only ghost button |
| theme toggle | `button.btn-ghost.btn-icon#btn-toggle-theme` (sun svg) | icon-only ghost button |
| left panel toggle | `btn.btn-ghost.btn-icon.review-only-ui#btn-toggle-left-panel` | icon-only, **review-only** visibility |
| right panel toggle | `btn.btn-ghost.btn-icon.review-only-ui#btn-toggle-right-panel` | icon-only, **review-only** visibility |
| settings | `btn.btn-ghost.btn-xs.agent-only-ui#btn-settings` ("Settings") | text ghost, **agent-only** |
| stop | `btn.btn-secondary.btn-xs.agent-only-ui#btn-topbar-stop` ("Stop") | secondary text, **agent-only** |

**Visibility pattern:** `review-only-ui` / `agent-only-ui` classes + `data-mode="review|agent"` on shell control which controls are visible. Current app uses the same idea (`review-only` / `agent-only`), keep the naming in sync during port.

---

## 2. Main shell: workspace + timeline

### 2a. Workspace (`div.workspace`, grid `240px minmax(0,1fr) 260px`)

**LEFT panel — `aside.panel.panel-left` (240px):**
- `div.rail-tabs` — segmented tab row (Assets / Edit graph), `data-left-tab` + `aria-selected`, no underline style — **capsule/segmented tabs** (current uses flat `.tab.active` underline-style).
- `div.panel-body#left-assets`:
  - `div.asset-drop#asset-drop` — **compact dashed drop zone** at top: `<strong>Drop media</strong>` + "Video, audio, or stills for this project". No icon, no file input in the mock. (Current: large icon dropzone + upload progress bar.)
  - `div.asset-list.filled-only` → `button.list-item.is-active`:
    - `span.thumb.film` — 34×34 rounded gradient thumbnail (`.film` variant)
    - `span.item-copy` > `span.name` ("hero_plate.mp4") + `span.sub` ("00:12.40 · h264")
    - `span.item-meta` ("src") — right-aligned meta tag
  - `div.empty-inline.empty-only` — "No assets yet / Ingest media or let the MCP agent add clips."
- `div.panel-body#left-graph` (hidden by default): `div.graph-list.filled-only` of same `list-item` rows (name = op kind, sub = id + params, meta = "ok") + `btn.btn-secondary.btn-sm` Undo / `btn.btn-danger.btn-sm` Delete row. (Current has a separate edit-detail inspection panel — ref keeps it simpler.)

**CENTER panel — `section.panel.panel-center` (flex-1), `div.center-stack` grid rows `minmax(0,1fr) auto`:**

1. `div.preview-panel#preview-panel` (flex column):
   - `div.preview-head` — `span.panel-title` "Preview" + `span.preview-mode-badge.muted` ("Proxy · 640×360")
   - `div.preview-stage` — **rounded (20px) letterbox stage**, grid centered, contains:
     - `div.preview-media` (video layer) + `div.preview-figure` (overlay/graphics layer) — stacked mock layers
     - `div.preview-badge#preview-live-badge` ("Review artifact · 640×360") — floating corner chip
     - `div.preview-empty#preview-empty` — empty state: `div.ring` (circular svg film icon) + `<h3>Waiting for proxy</h3>` + copy + `button.btn.btn-primary.btn-sm#btn-empty-proxy` ("Render proxy" CTA)
   - `div.transport` — **custom transport bar** (centered, gap 8): `btn.btn-ghost.btn-icon#btn-skip-back` (⏮), `btn.btn-primary.btn-icon#btn-play` (▶ — accent CTA), `btn.btn-ghost.btn-icon#btn-skip-fwd` (⏭), then `div.time` = `<strong id="tc-current">00:10.44</strong> <span>/ 00:12.40</span>` (bold current / muted total). **Current app has NO transport bar** — it relies on native `<video controls>`.
2. `div.agent-dock#chat-log-wrap` — **chat docks directly under the preview** (see §4).

**RIGHT panel — `aside.panel.panel-right` (260px):**
- `div.panel-head` — "Renders" title + `btn.btn-ghost.btn-xs#btn-refresh-renders` (Refresh)
- `div.panel-body` with **stacked `section-block`s** (each = own section w/ hairline separation):

  *Section: Renders*
  - `div.render-actions` — `btn.btn-secondary.btn-sm#btn-render-proxy` "Proxy" + `#btn-render-final` "Final" (side-by-side actions; current app additionally has an encoder GPU/CPU select)
  - `div.render-list.filled-only` → `button.list-item.is-active` rows: `span.thumb.film` + `item-copy` (`name` = filename, `sub` = "proxy · 640×360") + `span.status-pill` ("ready") / `span.status-pill.warn` ("stale") — **status pills on list rows** (current uses emoji thumbs + colored text status)
  - `div.empty-inline.empty-only` — "No renders / Proxy first for review, then final when the cut locks."

  *Section: Notes*
  - `div.section-label` — "Notes" + `btn.btn-ghost.btn-xs#btn-show-notes` "View"
  - `div.note-list.filled-only` → `button.list-item` with `thumb` (warn-tinted color block), name "Staff raise feels late", sub "@ 00:10.44"
  - `div.empty-inline.empty-only` — "No notes / Add a note at the playhead while reviewing."

  *Section: Style* — `div.section-label` "Style" + `div.empty-inline` informational copy ("Neutral · single accent").

### 2b. Timeline (`section.timeline-panel#timeline-panel`, bottom row of shell)

- `div.timeline-toolbar` (flex, wrap): `span.label` "Timeline" · `span.timecode#timeline-timecode-label` (mono) · `span.item-meta#timeline-duration-label` ("12.40s") · `btn.btn-ghost.btn-xs#btn-copy-timecode` "Copy time" · `btn.btn-ghost.btn-xs#btn-add-note-playhead` "Note here" · spacer · `#btn-timeline-zoom-in` "+" · `#btn-timeline-zoom-out` "−" · `#btn-timeline-fit` "Fit"
- `div.timeline-body` (grid `56px 1fr`, min-height 96px):
  - `div.track-labels#timeline-track-labels` — label rows `div.track-label` ("v1", "a1", "ov"); a1/ov wrapped in `density-only`
  - `div.timeline-canvas#timeline-canvas` — relative container, `cursor: ew-resize` (scrub anywhere):
    - `div.ruler#timeline-ruler` — 22px mono tick labels ("0s 3s 6s 9s 12s")
    - `div.tracks#timeline-tracks-area` → `div.track-row` (one per track) → `div.clip` absolutely positioned by `left%/width%`:
      - `clip` (video): **accent-blue gradient**, mono 9px clip id label
      - `clip.audio`: **green gradient** ("dialogue")
      - `clip.overlay`: **amber gradient** ("title")
    - `div.playhead#timeline-playhead` — 2px accent line, full height, glow
    - `div.timeline-empty#timeline-empty-msg` — "No clips yet — ingest media or ask the agent to build a cut."
- Global `div.toast#toast` — fixed bottom-right glass pill.

---

## 3. Component inventory (class → purpose)

### Buttons (`button.btn`, base = pill/capsule, font 11–13px, hover/active tokens)
| class | purpose |
|---|---|
| `btn btn-primary` | accent-blue filled CTA (Play, Send, Render proxy) |
| `btn btn-secondary` | glass-filled neutral (Proxy/Final render, Stop, Undo) |
| `btn btn-ghost` | transparent text button (Copy time, Note here, Zoom, Refresh, +New) |
| `btn btn-icon` | icon-only square ghost (cmd-k, theme, panel toggles, transport) |
| `btn btn-danger` | destructive (Delete edit op) |
| `btn btn-xs` / `btn btn-sm` | size modifiers (xs = topbar/toolbar, sm = panel actions) |

### Chips & pills
| class | purpose |
|---|---|
| `chip` (+ `chip.warn`) | stage-header meta chips w/ `span.dot` color dot ("Apple tokens", "CRT retired") |
| `mode-badge` (+ `span.pulse`) | topbar mode indicator (Review · MCP / Agent · built-in), pulsing live dot |
| `status-pill` (+ `.warn`) | tiny 10px rounded state tag on list rows / agent head ("ready", "stale", "verify · $0.04") |
| `preview-mode-badge.muted` | preview resolution chip in preview head |
| `prompt-chip` | editor-verb quick prompts in agent dock |
| `kicker` | aspect-rail only, small overline label |

### Lists & items
| class | purpose |
|---|---|
| `list-item` (button, grid `auto 1fr auto`) | universal row for assets / graph ops / renders / notes; `is-active` = selected |
| `thumb` (+ `thumb.film`) | 34×34 rounded media thumbnail (`.film` = video look) |
| `item-copy` > `name` + `sub` | two-line row text (title + mono meta line) |
| `item-meta` | right-side small tag ("src", "ok") or duration ("12.40s") |
| `rail-tab` | segmented tab in left rail (Assets / Edit graph) |
| `section-label` / `panel-title` / `panel-head` | section headers |

### Timeline clips
`clip` (accent) / `clip.audio` (green) / `clip.overlay` (amber) — colored gradient blocks, mono labels, absolutely positioned; `track-row` per track; `track-label` per label column; `ruler`; `playhead`.

### Agent dock (chat)
`agent-dock` / `agent-head` / `chat-log` / `bubble` (`user`, `agent`, `tool`) / `prompt-chips` / `prompt-chip` / `chat-compose`.

### States & utilities
| class | purpose |
|---|---|
| `filled-only` / `empty-only` | show content only when data exists / only when empty (sibling pattern) |
| `empty-inline` | inline empty-state copy (strong + paragraph) inside panels |
| `preview-empty` (+ `ring`) | centered empty stage: ring icon, h3, p, primary CTA |
| `asset-drop` | compact dashed drop zone |
| `density-only` | only visible in "density" aspect (timeline tracks a1/ov) |
| `review-only-ui` / `agent-only-ui` | visibility scoped to mode |
| `toast` | fixed bottom-right notification |

---

## 4. Chat / agent dock

- **Location:** directly **under the preview panel inside the center column** (`center-stack` grid row 2), NOT a full-height side column. `display:none` until `data-aspect="agent"` / agent mode; `max-height:210px`, glass panel with top hairline. **"Editor stage stays primary"** — the dock is compact and collapsible by design.
- **Header `agent-head`:** `panel-title` "Agent" + `status-pill#chat-cost-chip` ("verify · $0.04") — merges current app's separate verify-chip + cost-badge into one pill.
- **Log `chat-log`:** flex column, `overflow:auto`; bubbles:
  - `bubble.user` — right-aligned, accent-tinted fill, tail cut bottom-right
  - `bubble.agent` — left-aligned, neutral glass fill, tail cut bottom-left; optional `span.tool` ("tool · apply_silence_gaps") — mono tool-call annotation inside agent bubble (current app shows tool calls as separate messages/status instead)
- **Prompt chips `prompt-chips`:** row of editor-verb text chips — "Cut silence", "Proxy review", "Note at playhead" (current: emoji-labeled chips only inside welcome empty state).
- **Compose `chat-compose`:** grid `1fr auto`; `textarea#chat-input` rows=1 placeholder "Prompt to edit the cut… Enter to send" + `button.btn.btn-primary#btn-send` "Send" (no Stop button inside compose in ref — Stop lives in topbar).

---

## 5. In reference but NOT in current frontend

1. **`aspect-rail` explorer navigation** (5-aspect switcher) — demo/dev harness, not part of the product; candidate to drop or keep as a hidden dev tool.
2. **`mode-badge` with `pulse`** in topbar center — no mode indicator today.
3. **`conn` text+dot status** ("Connected") — current has bare dot.
4. **`logo-mark` tile + "open Edit" wordmark** — current has CRT icon with literal "O" inside (violates mission logo spec; must change to monitor-shaped O, no inner glyph).
5. **Custom `transport` bar** (skip-back / play / skip-fwd / time) — current uses native `<video controls>`.
6. **`preview-badge`** floating chip on stage; **`preview-media` + `preview-figure`** layered stage (current just has a `<video>`).
7. **Agent dock**: `agent-head` with `status-pill` (verify+cost merged), `bubble.user/agent/tool` pattern, prompt chips outside welcome state.
8. **`asset-drop` compact dashed zone** with copy "Drop media" — current has big icon dropzone + progress; ref also lacks upload progress UI (keep current upload progress).
9. **`status-pill`** on render rows (ready/stale/warn) and `item-meta` tags on rows.
10. **`empty-inline` + `filled-only`/`empty-only`** dual-state pattern per section — current uses single `empty-state` divs.
11. **`section-block` / `section-label`** stacked right-panel sections (current has flat panel-sections — similar but less structured).
12. **Timeline clip variants** `clip.audio` (green) / `clip.overlay` (amber) + `track-label` column with `density-only` — current renders tracks dynamically but without the visual clip-type language.
13. **Scrub-anywhere canvas** (whole `timeline-canvas` is `cursor: ew-resize` + pointer capture) — current scrubs only via playhead drag (verify in app.js).
14. **`chip` + `dot`** meta chips in stage header.
15. **`btn-danger`** on edit-graph actions (current does have `btn-danger` already — partial overlap).

**Currently present but NOT in ref** (keep for functionality): upload progress bar, edit-detail inspection panel, GPU/CPU encoder select, welcome empty state with emoji prompt chips, cmd-palette modal, new-project modal, asset-preview modal, notes modal, settings modal, mobile-only panel buttons, ⌘K kbd badge.

---

## 6. ASCII wireframe (loaded aspect, review mode)

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│ EXPLORER PAGE (grid 220px | 1fr)                                                    │
│┌─ aspect-rail ─────────┐ ┌─ stage-wrap ────────────────────────────────────────────┐│
││ kicker "Mockup pass·A" │ │ stage-header:  OpenEdit Review Studio      [● Apple]   ││
││ Shell Explorer (h1)    │ │               sub: High-fidelity shell mock [● Codex]  ││
││ [01 Loaded cut      ]  │ │                                         [● CRT retired]││
││ [02 Empty studio    ]  │ │ ┌─ shell ────────────────────────────────────────────┐ ││
││ [03 Agent mode      ]  │ │ │ topbar (48px):                                    │ ││
││ [04 Controls kit    ]  │ │ │ [OE open Edit] [video ▾ 1 asset] [+New]           │ ││
││ [05 Timeline density]  │ │ │                [● Review · MCP] [Provider ▾]      │ ││
││ aspect-note: Live      │ │ │        [● Connected] [⌘][☀][◧][◨][Settings][Stop] │ ││
││ aspect…               │ │ ├─ workspace: 240px | center 1fr | 260px ──────────┤ ││
││                        │ │ │ LEFT            CENTER            RIGHT           │ ││
││                        │ │ │ [Assets|EditGr] [Preview    ]     [Renders] [Refr]│ ││
││                        │ │ │ ┌─drop───┐     [Proxy·640×360]   [Proxy][Final]  │ ││
││                        │ │ │ │Drop    │     ┌──────────────┐  [▶ film] ready  │ ││
││                        │ │ │ │media   │     │ (stage)      │  [▶ film] stale  │ ││
││                        │ │ │ └────────┘     │  [Review art] │  "No renders…"   │ ││
││                        │ │ │ ▶ hero_plate   │  badge        │ ────────────────│ ││
││                        │ │ │   src          └──────────────┘  [Notes] [View]  │ ││
││                        │ │ │  00:12.40·h264  ⏮ ▶ ⏭ 00:10.44/00:12.40 │ ▶ note @10.44   │ ││
││                        │ │ │ "No assets…"   ────────────────   "No notes…"    │ ││
││                        │ │ │ (graph tab:    │ AGENT DOCK      ────────────────│ ││
││                        │ │ │  undo/delete)  │ Agent [verify·$0.04] │ [Style]      │ ││
││                        │ │ │                │ [user bubble       ] │ Neutral·accent││
││                        │ │ │                │ [agent bubble  tool] │               ││
││                        │ │ │                │ [Cut silence][Proxy…]│               ││
││                        │ │ │                │ [textarea………] [Send] │               ││
││                        │ │ ├─ timeline-panel ─────────────────────────────────┤ ││
││                        │ │ │ Timeline 00:10.44 12.40s [Copy][Note]   [+][−][Fit]││
││                        │ │ │ v1 │ 0s 3s 6s 9s 12s  │                          ││
││                        │ │ │ a1 │ ████████████  ▓▓▓  (v=accent,a=green,      ││
││                        │ │ │ ov │         ▓▓▓       ov=amber, | playhead)     ││
││                        │ │ └──────────────────────────────────────────────────┘││
│└────────────────────────┘ └──────────────────────────────────────────────────────┘│
│  toast (fixed, bottom-right)                                                        │
└────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Key takeaways for PLAN.md

1. **Shell = one rounded card**: topbar (48px) / workspace (240|1fr|260) / timeline — with glass panels + hairline borders + one outer shadow.
2. **Center column stacks preview → agent dock** (`grid-template-rows: minmax(0,1fr) auto`); dock max-height 210px, hidden in review mode, chips outside welcome.
3. **Universal row component** (`list-item` = thumb + name/sub + meta/pill) reused across assets, graph, renders, notes — big simplification win vs current bespoke item markup.
4. **Dual-state pattern** (`filled-only`/`empty-only` + `empty-inline`) per section — port to all panels.
5. **Custom transport bar** replaces native video controls; keep real `<video>` element underneath.
6. **Mode/pulse badge, conn text, status pills, clip color language (blue/green/amber)** are the main new visual vocabulary.
7. **Aspect rail is demo tooling** — do not ship in product UI (or hide behind dev flag).
8. Keep current functional extras (upload progress, edit-detail, encoder select, modals) unless orchestrators decide otherwise — they live fine inside the new component system.
