# STAGE 1 — Reference Study: Design Language & Tokens

**Source studied (directly read):** `/home/amr/Downloads/file/openedit-shell-explorer.html` (58,820 bytes; 1 inline `<style>` block of 31,043 chars + body markup + mock JS).
**Focus (ref-1):** Design language & tokens.
**Companion reports:** ref-2 layout/components, ref-3 interactions/motion/typography, cur-1 current UI inventory, cur-2 gap analysis/logo spec.
**Method note:** All values below are quoted verbatim from the reference file. Where a token is a `color-mix(in oklab, …)` expression, the *approximate rendered hex* is given in brackets, computed with the CSS Color 4 OKLab mixing algorithm (perceived over the studio background where the mix includes `transparent`).

---

## 0. Design language in one paragraph

The mockup's own caption says it: **"Apple calm × Codex glass × NLE density."** It is a **dark graphite studio** built from a light Apple token set inverted via OKLab `color-mix` (the header comment: *"Studio shell derived from Apple tokens (dark chapter + graphite steps)"*). Neutrals are warm gray-graphite (never pure black), the single accent is **Apple action blue `#0071e3`** used only for play/active/CTAs, text is high-contrast off-white with 3 ink steps, separation is done with **translucent white hairlines (14–22% alpha)** instead of solid borders, and depth comes from **frosted glass (backdrop blur) + soft layered shadows + one ambient accent radial glow**. Timecodes/labels are always mono with tabular numerals. The shell is one big **22px-radius rounded "app card"** floating on a dimmer page background with a sticky explorer rail on the left.

---

## 1. CSS custom properties — complete `:root` inventory

The reference pastes Apple's design-system tokens verbatim, then defines a `--studio-*` block that derives the dark shell from them. Full list (name: value, verbatim):

### 1a. Core Apple tokens (light-theme sources)

| Token | Value |
|---|---|
| `--bg` | `#ffffff` |
| `--surface` | `#f5f5f7` |
| `--surface-warm` | `#fbfbfd` |
| `--fg` | `#1d1d1f` |
| `--fg-2` | `#424245` |
| `--muted` | `#6e6e73` |
| `--meta` | `#86868b` |
| `--border` | `#d2d2d7` |
| `--border-soft` | `#e8e8ed` |
| `--accent` | `#0071e3` |
| `--accent-on` | `#ffffff` |
| `--accent-hover` | `#0077ed` |
| `--accent-active` | `#0066cc` |
| `--success` | `#16a34a` |
| `--warn` | `#eab308` |
| `--danger` | `#dc2626` |

### 1b. Fonts

| Token | Value |
|---|---|
| `--font-display` | `"SF Pro Display", "SF Pro Icons", "Helvetica Neue", Helvetica, Arial, sans-serif` |
| `--font-body` | `"SF Pro Text", "SF Pro Icons", "Helvetica Neue", Helvetica, Arial, sans-serif` |
| `--font-mono` | `"SF Mono", ui-monospace, "JetBrains Mono", Menlo, Monaco, Consolas, monospace` |

### 1c. Type scale / leading / tracking

| Token | Value | | Token | Value |
|---|---|---|---|---|
| `--text-xs` | `12px` | | `--leading-body` | `1.47` |
| `--text-sm` | `14px` | | `--leading-tight` | `1.05` |
| `--text-base` | `17px` | | `--tracking-display` | `-0.015em` |
| `--text-lg` | `21px` | | | |
| `--text-xl` | `28px` | | | |
| `--text-2xl` | `40px` | | | |
| `--text-3xl` | `56px` | | | |
| `--text-4xl` | `80px` | | | |

### 1d. Spacing / section rhythm

| Token | Value | | Token | Value |
|---|---|---|---|---|
| `--space-1` | `4px` | | `--space-6` | `24px` |
| `--space-2` | `8px` | | `--space-8` | `32px` |
| `--space-3` | `12px` | | `--space-12` | `48px` |
| `--space-4` | `16px` | | `--section-y-desktop` | `100px` |
| `--space-5` | `20px` | | `--section-y-tablet` | `64px` |
| | | | `--section-y-phone` | `40px` |

### 1e. Radii, elevation, focus, motion

| Token | Value |
|---|---|
| `--radius-sm` | `8px` |
| `--radius-md` | `12px` |
| `--radius-lg` | `18px` |
| `--radius-pill` | `980px` |
| `--elev-flat` | `none` |
| `--elev-ring` | `0 0 0 1px var(--border)` |
| `--elev-raised` | `0 12px 32px rgba(0, 0, 0, 0.08)` |
| `--focus-ring` | `0 0 0 4px color-mix(in oklab, var(--accent), transparent 65%)` |
| `--motion-fast` | `150ms` |
| `--motion-base` | `220ms` |
| `--ease-standard` | `cubic-bezier(0.28, 0, 0.22, 1)` |
| `--container-max` | `1024px` |
| `--container-gutter-desktop` | `22px` |
| `--container-gutter-tablet` | `18px` |
| `--container-gutter-phone` | `16px` |

### 1f. Studio shell tokens (the actual dark design system — verbatim)

```css
/* Studio shell derived from Apple tokens (dark chapter + graphite steps) */
--studio-bg: color-mix(in oklab, var(--fg) 94%, black);
--studio-elev-1: color-mix(in oklab, var(--fg) 88%, var(--bg) 12%);
--studio-elev-2: color-mix(in oklab, var(--fg) 82%, var(--bg) 18%);
--studio-elev-3: color-mix(in oklab, var(--fg) 76%, var(--bg) 24%);
--studio-ink: color-mix(in oklab, var(--bg) 92%, var(--fg));
--studio-ink-2: color-mix(in oklab, var(--bg) 72%, var(--fg));
--studio-ink-muted: color-mix(in oklab, var(--bg) 48%, var(--fg));
--studio-line: color-mix(in oklab, var(--bg) 14%, transparent);
--studio-line-strong: color-mix(in oklab, var(--bg) 22%, transparent);
--studio-glass: color-mix(in oklab, var(--studio-elev-2) 78%, transparent);
--studio-warn: var(--warn);
```

---

## 2. Color palette (concrete values)

### 2a. Dark theme layer stack (graphite steps, light rises with elevation)

Computed approximate rendered values (OKLab mixing):

| Layer | Expression | ≈ Rendered |
|---|---|---|
| `--studio-bg` (page + shell base) | `fg 94% black` | **`#1a1a1c`** |
| `--studio-elev-1` (rail, panels, topbar base) | `fg 88% bg 12%` | **`#333435`** |
| `--studio-elev-2` (docks, timeline canvas mix) | `fg 82% bg 18%` | **`#3f3f41`** |
| `--studio-elev-3` (toast, thumbs base) | `fg 76% bg 24%` | **`#4c4c4d`** |
| `--studio-glass` (elev-2 @ 78% α over bg) | elev2 78% transparent | **≈ `#373739`** |

The **elevation direction is inverted from the light theme**: higher surfaces are *lighter* (more white mixed in), lower/dimmer surfaces darker. All neutrals are warm graphite with a faint blue-gray cast — never pure black (pure black appears only as 25–55% mixes *inside* the preview stage and timeline canvas).

### 2b. Ink (text) ramp

| Token | Expression | ≈ Rendered | Use |
|---|---|---|---|
| `--studio-ink` | `bg 92% fg` | **`#eaeaeb`** | primary text, names, headings, topbar |
| `--studio-ink-2` | `bg 72% fg` | **`#b9b9b9`** | secondary text, subs, button labels |
| `--studio-ink-muted` | `bg 48% fg` | **`#808081`** | meta, kickers, section labels, placeholders |

### 2c. Accent (single accent policy — "Neutral · single accent, Apple action blue for CTAs only")

| Token | Value | Use |
|---|---|---|
| `--accent` | **`#0071e3`** | primary buttons, play button, active list item, selected rail tab, playhead, clip (video), dot |
| `--accent-hover` | `#0077ed` | primary hover |
| `--accent-active` | `#0066cc` | primary pressed |
| `--accent-on` | `#ffffff` | text/icon on primary |

Accent is used **sparingly**: selected states are a translucent wash (`color-mix(in oklab, var(--accent) 16%, transparent)` background + 40% border), not solid blue. The only solid-accent surfaces are `.btn-primary`, `.logo-mark`, the play button, `.playhead` and video `.clip`s. Accent appears as ambient light via radial gradients: rail `radial-gradient(120% 80% at 0% 0%, accent 18% → transparent 55%)`, shell `radial-gradient(80% 50% at 70% -10%, accent 12% → transparent 60%)`, preview stage `radial-gradient(60% 50% at 50% 42%, accent 18% → transparent 70%)`.

### 2d. Semantic colors

| Token | Value | Use pattern |
|---|---|---|
| `--success` | `#16a34a` | `.conn i` status dot (+ 3px 25% glow), audio clips, `.status-pill` (bg 16% α, text `success 30% + bg` ≈ `#c4e4c8`) |
| `--warn` | `#eab308` | `.status-pill.warn` (bg 16% α, text `warn 35% + bg` ≈ `#f8e5bd`), overlay clips, note thumb (`warn 35% + elev-3`) |
| `--danger` | `#dc2626` | `.btn-danger` (bg 18% α, border 30% α, text `danger 40% + bg` ≈ `#fbb3a9`) |
| `--studio-warn` | `var(--warn)` | chip dot in warn state |

Semantic colors are **never solid on dark**: always `color-mix` at 16–40% alpha over graphite, with tinted (not bright) text. `.status-pill` is a translucent pill (bg 16% α, radius-pill, 10px/600 weight text).

### 2e. Gold/bronze accents

There is **no gold token**. Two hard-coded "film" gradients carry warm bronze/orange as *content imagery*, not chrome:

```css
.thumb.film {
  background:
    linear-gradient(160deg, color-mix(in oklab, var(--bg) 18%, transparent), transparent 40%),
    linear-gradient(35deg, #3a4658, #1a2030 60%, #0f1420);   /* steel-blue film still */
}
.preview-figure {
  background: linear-gradient(180deg, #f4efe4 0%, #e8d9b8 35%, #c9a86a 70%, #8d6a3a 100%);
  /* warm statue figure — champagne → bronze */
}
.preview-media {
  background:
    radial-gradient(60% 50% at 50% 42%, color-mix(in oklab, var(--accent) 18%, transparent), transparent 70%),
    linear-gradient(180deg, #243044 0%, #121821 55%, #0b1018 100%);
}
```

### 2f. Hairlines (the border system)

| Token | Expression | ≈ over bg | Use |
|---|---|---|---|
| `--studio-line` | `bg 14% transparent` | ≈ `#3a3a3c` | borders: topbar bottom, panel edges, timeline canvas, section dividers |
| `--studio-line-strong` | `bg 22% transparent` | ≈ `#4c4c4e` | elevated edges: shell border, chips, pills, secondary buttons, preview stage, toast |

Borders are **translucent white at 14%/22% alpha**, not solid grays — this is what gives the "glass edge" look on dark.

---

## 3. Typography

### 3a. Families & base

- **Display:** `--font-display` — SF Pro Display stack. Used for: `.logo` (600, 14px, `-0.02em`), `.aspect-brand h1` (600, 18px), `.stage-header h2` (600, 22px), `.preview-empty h3` (600, 16px).
- **Body/UI:** `--font-body` — SF Pro Text stack. Default for `html, body` (`font-size: var(--text-sm)` = 14px, `line-height: 1.35`, antialiased). Everything else inherits it unless mono/display.
- **Mono:** `--font-mono` — SF Mono / JetBrains Mono stack. Used for **all timecodes, numeric meta, kickers, labels**: `.kicker` (10px, `.08em` uppercase), `.aspect-num` (10px, `.06em`), `.project-select .meta` (10px), `.item-copy .sub` (10px), `.item-meta` (10px), `.track-label` (10px), `.preview-badge` (10px), `.ruler` (9px), `.clip` labels (9px), `.transport .time` (12px), `.timecode` (13px), `.bubble .tool` (10px).

### 3b. Sizes & weights — application map

| Class / role | Family | Size | Weight | Tracking / other |
|---|---|---|---|---|
| body base | body | 14px (`--text-sm`) | 400 | `line-height: 1.35`; antialiased |
| `.stage-header h2` | display | 22px | 600 | `-0.015em` (`--tracking-display`) |
| `.aspect-brand h1` | display | 18px | 600 | `-0.015em`, `l-height 1.15` |
| `.logo` | display | 14px | 600 | `-0.02em` (tighter than display default) |
| `.preview-empty h3` | display | 16px | 600 | `-0.015em` |
| `.preview-mode-badge` (muted) | body | 11px | — | muted color |
| `.panel-title`, `.section-label`, `.timeline-toolbar .label` | body | 11px | 600 | `0.06em`, **uppercase** |
| `.aspect-btn .aspect-title` | body | 13px | 600 | — |
| `.aspect-btn .aspect-desc` / `.aspect-note` | body | 11px | 400 | `l-height 1.35–1.45` |
| `.item-copy .name` | body | 12px | 600 | ellipsis nowrap |
| `.btn` | body | 12px | 600 | pills; `.btn-xs` 11px |
| `.chip`, `.prompt-chip`, `.mode-badge` | body | 11px | 400/600 | pill |
| `.timecode`, `.transport .time` | mono | 13px / 12px | 400 (strong 700 via `<strong>`) | `font-variant-numeric: tabular-nums` |
| `.ruler` | mono | 9px | 400 | — |
| `.kicker`, `.aspect-num`, `.item-meta`, `.item-copy .sub`, `.track-label`, `.preview-badge` | mono | 9–10px | 400 | uppercase + `.08em`/.06em on kicker & num |

**Key patterns:**
- **Mono = data/timecode/meta; sans = names/actions; display = only brand + section titles.**
- Uppercase micro-labels (11px, 600, `0.06em` tracking, `--studio-ink-muted`) for all section headers (`panel-title`, `section-label`, `timeline label`).
- **All timecodes use `font-variant-numeric: tabular-nums`** so numbers don't jitter while scrubbing.
- Negative tracking (`-0.015em` to `-0.02em`) only on display-family headings/logo.

---

## 4. Glassmorphism + elevation

### 4a. Backdrop-filter surfaces (5 occurrences)

| Surface | Background | Blur | Notes |
|---|---|---|---|
| `.topbar` | `color-mix(in oklab, var(--studio-elev-1) 88%, transparent)` | **blur(18px)** | full-width frosted bar |
| `.agent-dock` | `color-mix(in oklab, var(--studio-elev-2) 85%, transparent)` | **blur(14px)** | chat dock over timeline |
| `.preview-badge` | `color-mix(in oklab, black 45%, transparent)` | **blur(10px)** | floating mono badge over media |
| `.toast` | `color-mix(in oklab, var(--studio-elev-3) 92%, transparent)` | **blur(12px)** | toast |
| (`.shell` root) | solid `--studio-bg` | — | card itself is opaque; glass is inside it |

Pattern: **frosted panels = elev-N mixed 85–92% with transparent + blur 12–18px + 1px `--studio-line-strong` edge.** Both `backdrop-filter` and `-webkit-backdrop-filter` are always emitted.

### 4b. color-mix usage patterns (the whole system is built on these)

1. **Elevation:** `color-mix(in oklab, var(--fg) X%, var(--bg) Y%)` — gray steps.
2. **Alpha fills:** `color-mix(in oklab, <color> N%, transparent)` — hover fills (bg 5–7%), selected states (accent 12–16%), danger (18%), semantic pills (16%).
3. **Tinted borders:** `color-mix(in oklab, var(--accent) 40–50%, transparent)` for active/selected edges.
4. **Tinted text:** `color-mix(in oklab, <semantic> N%, var(--bg))` — light pastel text on dark (success 30%, warn 35%, danger 40%).
5. **Glass:** `color-mix(in oklab, var(--studio-elev-N) 85–92%, transparent)`.
6. **Ambient gradients:** radial accent glows at 12–18% alpha.
7. **Focus ring:** `0 0 0 4px color-mix(in oklab, var(--accent), transparent 65%)` — 4px soft blue halo (replaces `outline`; `outline: none` set on focus-visible).

### 4c. Shadows

| Token / rule | Value | Used on |
|---|---|---|
| `--elev-raised` | `0 12px 32px rgba(0,0,0,0.08)` | toast |
| `.shell` | `0 0 0 1px color-mix(in oklab, var(--bg) 4%, transparent), 0 24px 64px color-mix(in oklab, black 45%, transparent)` | the big app card (1px light inner ring + deep 64px drop) |
| `.logo-mark` | `0 4px 12px color-mix(in oklab, var(--accent) 35%, transparent)` | accent-tinted glow |
| `.clip` | `0 4px 12px color-mix(in oklab, var(--accent) 20%, transparent)` | video clips |
| `.playhead` | `0 0 0 1px accent 30% α, 0 0 12px accent 40% α` | glow line |
| `.preview-figure` | `0 18px 40px color-mix(in oklab, black 40%, transparent)` | media depth |
| `.conn i`, `.mode-badge .pulse` | `0 0 0 3px color-mix(… 25%, transparent)` | status halo (ring not blur) |

Shadow recipe: **ambient dark drop (40–64px, 40–45% black α) + hairline light ring + optional accent-tinted glow (20–35% α).** Inner shadows: `.preview-stage` `inset 0 0 0 1px color-mix(in oklab, var(--bg) 4%, transparent)`.

### 4d. Radii

| Token | Value | Used on |
|---|---|---|
| `--radius-sm` 8px | `.rail-tab` | |
| `--radius-md` 12px | `.aspect-btn`, `.list-item`, `.timeline-canvas`, `.aspect-note`, `.empty-inline`, `.track-row` (7px hardcoded), `.clip` (6px hardcoded) | |
| `--radius-lg` 18px | `.asset-drop` | |
| `--radius-pill` 980px | `.btn`, `.chip`, `.mode-badge`, `.project-select`, `.prompt-chip`, `.status-pill`, `.preview-badge`, `.bubble .tool`, `.transport` buttons (`.btn-icon` = `50%` circle) | |
| hardcoded | `.shell` **22px**, `.preview-stage` 20px, `.toast` 14px, `.bubble` 14px (5px tail corner), `.logo-mark` 7px, `.timeline-body` track rows 7px, `.clip` 6px, `.playhead::before` 2px top corners | |

**Hierarchy: cards/surfaces 18–22px → controls/lists 12px → pills 980px → micro elements 6–8px.** Buttons, chips, badges, selects are ALL pills. Surfaces nest: page → explorer + 22px shell card → panels with 12px items.

### 4e. Border styles

- Default: `1px solid` translucent hairline (see 2f).
- `.asset-drop`: `1px dashed` `bg 22% transparent`; on hover/drag `accent 50%` + `accent 8%` fill.
- `.shell`: `1px solid var(--studio-line-strong)` + extra 1px light ring via box-shadow.
- `:focus-visible` on buttons/tabs: `outline: none` + `box-shadow: var(--focus-ring)`.

---

## 5. Spacing / layout tokens

### 5a. Page & shell structure

| Property | Value |
|---|---|
| `.explorer` grid | `grid-template-columns: 220px minmax(0, 1fr)`; `min-height: 100vh/100dvh` |
| `.aspect-rail` | sticky, `height: 100dvh`, `padding: var(--space-5) var(--space-4)` (20/16px), `gap: var(--space-5)`, `z-index: 5`, right hairline |
| `.stage-wrap` | `padding: var(--space-5)` (20px), `gap: var(--space-4)` (16px) |
| `.shell` | `grid-template-rows: 48px minmax(0, 1fr) auto`; `min-height: 720px`; `border-radius: 22px` |
| `.topbar` | `grid-template-columns: 1fr auto 1fr`; `padding: 0 var(--space-4)`; height from 48px row; internal gaps 8px |
| `.workspace` | `grid-template-columns: 240px minmax(0, 1fr) 260px` (left/center/right); `overflow: hidden` |
| `.panel-body` | `padding: 10px` |
| `.timeline-panel` | `padding: 8px 12px 12px` |
| `.preview-panel` | `padding: 12px 14px 10px` |
| `.center-stack` | `grid-template-rows: minmax(0, 1fr) auto` (preview / optional agent dock) |
| `.agent-dock` | `max-height: 210px`; rows `auto minmax(0,1fr) auto` |

### 5b. Gaps (the rhythm)

- 4px: icon rows, rail tabs
- 6px: chips, lists (`gap: 6px` in asset/render/graph/note lists), aspect buttons, track gaps, render actions
- 8px: topbar clusters, buttons+icon gaps, transport, chat compose, timeline toolbar, panel heads
- 10px: list-item internal (grid `auto 1fr auto`), preview head margins, asset-drop margin
- 12–14px: section-block separation (`margin-top: 14px`), preview padding

### 5c. Grid & component sizes (for layout porting)

- Left rail 220px / workspace panels 240px + 260px; breakpoints: 1100px (rail collapses to horizontal strip, workspace 200/220px), 900px (stacked rows 180px/260px/180px).
- `.btn` min-height 28px, xs 26px, sm 30px; `.btn-icon` 28px circle; icons 14px.
- `.thumb` 34×34, radius 8px; `.list-item` padding 8px 10px.
- Timeline: `grid-template-columns: 56px 1fr`; track rows 28px (24px in density mode); ruler 22px; `.timecode` min-width 72px; transport `.time` min-width 120px.
- `.chip` padding 5px 10px; `.mode-badge` 5px 11px; `.project-select` max-width 220px, `padding 6px 10px`.
- `.preview-stage` min-height 220px, radius 20px; `.preview-figure` width 28%, aspect 3/5, bottom 8%.
- Container max/gutters (`--container-max` 1024px etc.) are **declared but unused** in this mockup (it's a full-viewport app) — keep for the design system, the app itself is edge-to-edge.

---

## 6. Key snippets to port verbatim

### 6a. Studio token block (drop-in for a dark app)

```css
:root {
  color-scheme: dark;
  --bg: #ffffff; --fg: #1d1d1f;
  --accent: #0071e3; --accent-hover: #0077ed; --accent-active: #0066cc; --accent-on: #ffffff;
  --success: #16a34a; --warn: #eab308; --danger: #dc2626;
  --studio-bg: color-mix(in oklab, var(--fg) 94%, black);
  --studio-elev-1: color-mix(in oklab, var(--fg) 88%, var(--bg) 12%);
  --studio-elev-2: color-mix(in oklab, var(--fg) 82%, var(--bg) 18%);
  --studio-elev-3: color-mix(in oklab, var(--fg) 76%, var(--bg) 24%);
  --studio-ink: color-mix(in oklab, var(--bg) 92%, var(--fg));
  --studio-ink-2: color-mix(in oklab, var(--bg) 72%, var(--fg));
  --studio-ink-muted: color-mix(in oklab, var(--bg) 48%, var(--fg));
  --studio-line: color-mix(in oklab, var(--bg) 14%, transparent);
  --studio-line-strong: color-mix(in oklab, var(--bg) 22%, transparent);
  --studio-glass: color-mix(in oklab, var(--studio-elev-2) 78%, transparent);
}
```

### 6b. Glass recipe

```css
background: color-mix(in oklab, var(--studio-elev-1) 88%, transparent);
backdrop-filter: blur(18px);
-webkit-backdrop-filter: blur(18px);
```

### 6c. App card elevation

```css
border-radius: 22px;
border: 1px solid var(--studio-line-strong);
background: var(--studio-bg);
box-shadow:
  0 0 0 1px color-mix(in oklab, var(--bg) 4%, transparent),
  0 24px 64px color-mix(in oklab, black 45%, transparent);
```

### 6d. Ambient accent glow layer (shell::before)

```css
background:
  radial-gradient(80% 50% at 70% -10%, color-mix(in oklab, var(--accent) 12%, transparent), transparent 60%);
opacity: 0.7;
```

### 6e. Mono timecode (anti-jitter)

```css
font-family: var(--font-mono);
font-size: 13px;
font-variant-numeric: tabular-nums;
```

### 6f. Micro-label (uppercase section header)

```css
font-size: 11px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase;
color: var(--studio-ink-muted);
```

### 6g. Focus ring

```css
box-shadow: 0 0 0 4px color-mix(in oklab, var(--accent), transparent 65%);
```

---

## 7. Design rules distilled (for PLAN.md)

1. **Single accent, restraint.** Blue `#0071e3` only on primary CTAs, play, active/selected, playhead, video clips; everything else graphite.
2. **Elevation = lightness.** Darkest = page/shell base (`#1a1a1c`); each raised surface mixes in 6% more white; glass surfaces add blur 10–18px + 14–22% white hairline.
3. **No solid borders on dark.** All borders/edges are `color-mix(…, transparent)` hairlines; semantic colors 16–40% alpha with tinted pastel text.
4. **Pills for everything interactive** (buttons, chips, badges, selects, status), 12px radius for lists/canvas, 18–22px for surfaces.
5. **Mono = data.** Every timecode, duration, hash, kicker, and meta label is `--font-mono` 9–13px with tabular-nums; uppercase 11px/600/0.06em labels head every section.
6. **Motion:** 150ms fast / 220ms base, single easing `cubic-bezier(0.28,0,0.22,1)`, `prefers-reduced-motion` kills all animation/transition; `:active` scale(0.97) on buttons.
7. **Ambient light:** 1–2 radial accent glows (12–18% α) per large surface; deep 40–64px black shadows with a 1px light ring for the app card.
8. **Current OpenEdit contrast:** today's CSS is a CRT green/amber terminal (`#33ff66` text, `#ffb000` accent, `#0d0f0e` bg, 2px radii, glow shadows). The reference replaces every one of those tokens: bg `#0d0f0e` → `#1a1a1c`, accent amber → blue `#0071e3`, radius 2px → 8–22px + pills, glow shadows → hairline+glass, mono-only text → display/body/mono hierarchy. Font stacks overlap (`JetBrains Mono`/`SF Mono`); the reference prefers SF-first stacks with JetBrains Mono fallback — keep JetBrains Mono as fallback for the mono stack and Inter can become the body fallback if SF Pro is unavailable on Linux.
