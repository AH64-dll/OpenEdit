# STAGE 1 — Reference Study (ref-3): Interactions, Motion & Responsiveness

**Source read directly:** `/home/amr/Downloads/file/openedit-shell-explorer.html` (59 KB; CSS 1,152 lines, JS 212 lines, HTML body ~19.8 KB)
**Focus:** interactions, motion, accessibility, responsive behavior, glass/effects.
**Mission context:** `testrun/ui_PLAN_PROMPT.md` (read first — Stage 1/ref-3 output).

---

## 0. Executive summary

The reference is an **Apple-tokens × Codex-glass × NLE-density** shell. Its interaction language is deliberately *quiet*:
everything interactive transitions **background / border-color / color / transform in 150 ms** with one shared cubic-bezier
ease; pressed buttons **scale 0.97**; selection state is always a **tinted accent wash (12–16 % accent) plus a 40 % accent
border**, never a hard fill. There is exactly **one keyframe animation** (`softPulse`, a box-shadow halo) and one JS-driven
motion (the pointer-scrubbed playhead). Glass is `backdrop-filter` blur 10–18 px over `color-mix` tints; status is conveyed
by **glowing dots** (box-shadow rings) and the playhead carries a 12 px accent glow. Keyboard users get a soft 4 px
`--focus-ring` halo **only via `:focus-visible`**, and `prefers-reduced-motion: reduce` nukes *all* animation and
transition globally. Responsiveness is three-stage: explorer rail folds at **1100 px**, 3-column workspace → stacked rows
at **900 px**, topbar collapses at 900 px.

---

## 1. Hover / active / focus states

### 1.1 Buttons (`.btn` family) — the core interaction pattern

```css
.btn {
  display: inline-flex; align-items: center; justify-content: center;
  gap: 6px;
  min-height: 28px;
  padding: 0 12px;
  border-radius: var(--radius-pill);   /* 980px — everything is a capsule */
  border: 1px solid transparent;
  font-size: 12px; font-weight: 600;
  transition:
    background var(--motion-fast) var(--ease-standard),
    border-color var(--motion-fast) var(--ease-standard),
    color var(--motion-fast) var(--ease-standard),
    transform var(--motion-fast) var(--ease-standard);
}
.btn:active { transform: scale(0.97); }   /* tactile press — the ONLY transform on buttons */
.btn-primary { background: var(--accent); color: var(--accent-on); }
.btn-primary:hover  { background: var(--accent-hover); }   /* #0071e3 → #0077ed */
.btn-primary:active { background: var(--accent-active); }  /* → #0066cc */
.btn-secondary {
  background: color-mix(in oklab, var(--bg) 10%, transparent);
  border-color: var(--studio-line-strong);
  color: var(--studio-ink);
}
.btn-secondary:hover { background: color-mix(in oklab, var(--bg) 14%, transparent); } /* 10% → 14% white lift */
.btn-ghost { color: var(--studio-ink-2); background: transparent; }
.btn-ghost:hover { background: color-mix(in oklab, var(--bg) 7%, transparent); color: var(--studio-ink); }
```

Pattern notes:
- **Hover = background lift only** (white mixed 4–14 %), never a border or scale change; **active = 0.97 scale** + darker
  primary fill. This is the entire button motion vocabulary.
- All buttons share the same transition list: `background / border-color / color / transform` @ `150ms var(--ease-standard)`.
- Sizes: `.btn-xs` (26 px min-height, 10 px padding), `.btn-sm` (30 px), `.btn-icon` (28×28 round, 14 px inline SVG).
- `.btn-danger` (red-tinted ghost: `danger 18%` bg, `danger 40%` text) has **no hover rule** in the mock — it stays flat.

### 1.2 Chips & badges

```css
.chip {  /* static status chip — NO hover */
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 10px; border-radius: var(--radius-pill);
  border: 1px solid var(--studio-line-strong);
  background: color-mix(in oklab, var(--bg) 5%, transparent);
  font-size: 11px; color: var(--studio-ink-2);
}
.chip .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }
.chip.warn .dot { background: var(--studio-warn); }

/* Interactive prompt chip — hover = accent border, no bg change */
.prompt-chip { padding: 5px 10px; border-radius: var(--radius-pill);
  border: 1px solid var(--studio-line-strong);
  background: color-mix(in oklab, var(--bg) 4%, transparent); font-size: 11px; color: var(--studio-ink-2); }
.prompt-chip:hover {
  border-color: color-mix(in oklab, var(--accent) 40%, transparent);
  color: var(--studio-ink);
}

/* Mode badge — the only element using --motion-base (220ms) for hover-ish state change */
.mode-badge {
  padding: 5px 11px; border-radius: var(--radius-pill); font-size: 11px; font-weight: 600;
  border: 1px solid var(--studio-line-strong);
  background: color-mix(in oklab, var(--bg) 4%, transparent); color: var(--studio-ink-2);
  transition: background var(--motion-base) var(--ease-standard), border-color var(--motion-base) var(--ease-standard);
}
.shell[data-mode="agent"] .mode-badge {
  border-color: color-mix(in oklab, var(--accent) 45%, transparent);
  background: color-mix(in oklab, var(--accent) 14%, transparent);
  color: var(--studio-ink);
}
```

### 1.3 List items (assets, graph ops, renders, notes)

```css
.list-item {
  display: grid; grid-template-columns: auto 1fr auto; gap: 10px; align-items: center;
  padding: 8px 10px; border-radius: var(--radius-md);   /* 12px — cards, not capsules */
  border: 1px solid transparent;
  background: color-mix(in oklab, var(--bg) 3%, transparent);
  cursor: pointer; text-align: left; width: 100%;
  transition: background var(--motion-fast) var(--ease-standard), border-color var(--motion-fast) var(--ease-standard);
}
.list-item:hover     { background: color-mix(in oklab, var(--bg) 6%, transparent); }        /* 3% → 6% lift */
.list-item.is-active { border-color: color-mix(in oklab, var(--accent) 40%, transparent);
                       background: color-mix(in oklab, var(--accent) 12%, transparent); }  /* accent wash */
```

Selection = **accent 12 % wash + 40 % accent border** (same recipe as selected aspect buttons and tabs). No left
indicator bar, no icon change — just the wash. Active state is toggled in JS by removing/adding `.is-active` within the
parent group (no transition on class add beyond the CSS transition, so it fades in 150 ms).

### 1.4 Tabs — left aspect rail (`.aspect-btn`)

```css
.aspect-btn {
  text-align: left; padding: 10px 12px; border-radius: var(--radius-md);
  border: 1px solid transparent; background: transparent; color: var(--studio-ink-2);
  transition:
    background var(--motion-fast) var(--ease-standard),
    border-color var(--motion-fast) var(--ease-standard),
    color var(--motion-fast) var(--ease-standard),
    transform var(--motion-fast) var(--ease-standard);
}
.aspect-btn:hover { background: color-mix(in oklab, var(--bg) 6%, transparent); color: var(--studio-ink); }
.aspect-btn[aria-selected="true"] {
  background: color-mix(in oklab, var(--accent) 16%, transparent);
  border-color: color-mix(in oklab, var(--accent) 40%, transparent);
  color: var(--studio-ink);
}
.aspect-btn[aria-selected="true"] .aspect-num { color: color-mix(in oklab, var(--accent) 70%, var(--bg)); }
/* aspect-num: 10px mono kicker above 13px semibold title + 11px muted description */
```

Selection is **ARIA-driven** (`aria-selected` set in JS via `setAspect()`), not a class — good pattern to copy. The
selected state tints the index number ("01") accent-colored for a subtle "active" read.

### 1.5 Rail tabs inside left panel (`.rail-tab`)

```css
.rail-tab { flex: 1; padding: 7px 8px; border-radius: var(--radius-sm); font-size: 12px; font-weight: 600;
  color: var(--studio-ink-muted); background: transparent; }
.rail-tab:hover { color: var(--studio-ink); background: color-mix(in oklab, var(--bg) 5%, transparent); }
.rail-tab[aria-selected="true"] { color: var(--studio-ink); background: color-mix(in oklab, var(--accent) 16%, transparent); }
```

Note: no transition on `.rail-tab` at all — it snaps. (Inconsistency in the mock; selected tab uses accent-16% wash, same as aspect buttons.)

### 1.6 Project select (`.project-select`)

```css
.project-select {
  display: inline-flex; align-items: center; gap: 8px; max-width: 220px;
  padding: 6px 10px; border-radius: var(--radius-pill);
  border: 1px solid var(--studio-line-strong);
  background: color-mix(in oklab, var(--bg) 5%, transparent); color: var(--studio-ink);
}
.project-select select { border: 0; background: transparent; color: inherit; max-width: 140px; outline: none; }
```

The native `<select>` is styled transparent inside a pill wrapper; **`outline: none` removes the default focus** and the
generic `:focus-visible` rule does **not** cover `select`/`textarea` (only buttons/tabindex/aspect-btn/rail-tab) — so the
project picker has **no visible focus ring in the mock** (gap to flag). The meta span (e.g. "1 asset") is 10px mono.

### 1.7 Playhead & timeline canvas (scrub interaction)

```css
.timeline-canvas {
  position: relative; border-radius: var(--radius-md); border: 1px solid var(--studio-line);
  background: linear-gradient(180deg, color-mix(in oklab, var(--bg) 3%, transparent), transparent 40%),
              color-mix(in oklab, black 25%, var(--studio-elev-2));
  overflow: hidden; cursor: ew-resize; user-select: none;   /* scrub affordance */
}
.playhead {
  position: absolute; top: 0; bottom: 0; width: 2px; background: var(--accent);
  box-shadow: 0 0 0 1px color-mix(in oklab, var(--accent) 30%, transparent),
              0 0 12px color-mix(in oklab, var(--accent) 40%, transparent);  /* glow line */
  z-index: 3; pointer-events: none;
}
.playhead::before {          /* rounded "cap" handle at top */
  content: ""; position: absolute; top: 0; left: 50%; transform: translateX(-50%);
  width: 10px; height: 10px; border-radius: 2px 2px 50% 50%; background: var(--accent);
}
```

JS scrub (pointer events with capture, not mouse events — touch-friendly):

```js
canvas.addEventListener("pointerdown", (e) => { dragging = true; canvas.setPointerCapture(e.pointerId); scrub(e.clientX); });
canvas.addEventListener("pointermove", (e) => { if (dragging) scrub(e.clientX); });
canvas.addEventListener("pointerup", () => { dragging = false; });
canvas.addEventListener("pointercancel", () => { dragging = false; });
// scrub() clamps x to canvas, sets playhead.style.left = pct + "%",
// and derives MM:SS.CS timecode (12.4s timeline) into both #tc-current and #timeline-timecode-label
```

Playhead position is `left: %` (JS inline style) — a pure layout move, **no CSS transition on the playhead** so it tracks
the pointer 1:1 with zero lag. Timecode display uses `font-variant-numeric: tabular-nums` + mono so numbers don't jitter.

---

## 2. Motion tokens & animations

### 2.1 Tokens

```css
--motion-fast: 150ms;
--motion-base: 220ms;
--ease-standard: cubic-bezier(0.28, 0, 0.22, 1);   /* Apple's "ease" — fast in, fast out */
```

Usage map:
| token | used by |
|---|---|
| `--motion-fast` (150ms) | `.btn`, `.aspect-btn`, `.list-item`, `.asset-drop`, `.prompt-chip` (implicit), `.rail-tab` (absent), any hover/focus transition |
| `--motion-base` (220ms) | `.mode-badge`, `.preview-media`, `.preview-figure`, `.preview-badge`, `.preview-empty`, `.toast` (opacity + transform) |
| `--ease-standard` | every transition + the `softPulse` animation timing function |

### 2.2 The single keyframe animation — `softPulse` (attention halo)

```css
.controls-spotlight .btn,
.shell[data-aspect="controls"] .btn-primary,
.shell[data-aspect="controls"] .btn-secondary,
.shell[data-aspect="controls"] .prompt-chip {
  animation: softPulse 1.8s var(--ease-standard) infinite;
}
@keyframes softPulse {
  0%, 100% { box-shadow: 0 0 0 0 color-mix(in oklab, var(--accent) 0%, transparent); }
  50%      { box-shadow: 0 0 0 4px color-mix(in oklab, var(--accent) 18%, transparent); }
}
```

Used to spotlight the "controls kit" aspect: primary/secondary buttons + prompt chips breathe a 4 px accent ring every
1.8 s. This is the **only** `@keyframes`/`animation` in the file — the mock's motion budget is tiny on purpose.

### 2.3 Static "pulse" dots (status glyphs — no animation, just halo shadow)

```css
.mode-badge .pulse { width: 6px; height: 6px; border-radius: 50%; background: var(--meta); }
.shell[data-mode="agent"] .mode-badge .pulse {
  background: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in oklab, var(--accent) 25%, transparent);   /* halo ring */
}
.conn i { width: 7px; height: 7px; border-radius: 50%; background: var(--success); display: block;
  box-shadow: 0 0 0 3px color-mix(in oklab, var(--success) 25%, transparent); }  /* "Connected" green dot */
```

The halo-ring dot (6–7 px dot + 3 px soft ring) is the mock's status idiom: `mode-badge` (grey→accent when agent mode)
and connection dot (green). `.chip .dot` reuses the 6 px dot without halo.

### 2.4 State crossfades (data-aspect-driven, 220 ms)

Preview layer content fades in/out as the shell aspect changes — opacity transitions on `--motion-base`:

```css
.preview-media, .preview-figure, .preview-badge {
  opacity: 0;
  transition: opacity var(--motion-base) var(--ease-standard);
}
.shell[data-aspect="loaded"] .preview-media,
.shell[data-aspect="agent"] .preview-media, ... { opacity: 1; }
.preview-empty {
  opacity: 0; pointer-events: none; transition: opacity var(--motion-base) var(--ease-standard);
}
.shell[data-aspect="empty"] .preview-empty { opacity: 1; pointer-events: auto; }
```

(Note: `.preview-figure` and `.preview-badge` share the same pattern. Timeline empty-state swap is **not** animated —
`display: grid` / `display: none`.)

### 2.5 Toast — the only enter/exit motion

```css
.toast {
  position: fixed; right: 24px; bottom: 24px;
  padding: 10px 14px; border-radius: 14px;
  background: color-mix(in oklab, var(--studio-elev-3) 92%, transparent);
  border: 1px solid var(--studio-line-strong);
  backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  color: var(--studio-ink); font-size: 12px;
  box-shadow: var(--elev-raised);               /* 0 12px 32px rgba(0,0,0,0.08) */
  opacity: 0; transform: translateY(8px); pointer-events: none;
  transition: opacity var(--motion-base) var(--ease-standard),
              transform var(--motion-base) var(--ease-standard);
  z-index: 50;
}
.toast.show { opacity: 1; transform: translateY(0); }
```

JS: class `.show` added; removed after **1600 ms** timer (every mock action toasts). Slide-up 8 px + fade in 220 ms.

---

## 3. Focus rings & accessibility patterns

### 3.1 Focus ring

```css
--focus-ring: 0 0 0 4px color-mix(in oklab, var(--accent), transparent 65%);   /* soft blue halo, no offset */

button:focus-visible,
[tabindex]:focus-visible,
.aspect-btn:focus-visible,
.rail-tab:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}
::selection { background: color-mix(in oklab, var(--accent) 35%, transparent); }
```

- **`:focus-visible` only** — rings appear for keyboard navigation, not mouse clicks. `outline: none` replaced by the
  4 px accent halo (same soft-accent language as selection washes).
- `.chat-compose textarea:focus` gets the same recipe on its border:
  `border-color: color-mix(in oklab, var(--accent) 50%, transparent); box-shadow: var(--focus-ring);`
- **Gaps to flag:** `.project-select select` has `outline: none` and is *not* in the `:focus-visible` list → no visible
  focus on the project picker. `.prompt-chip`, `.list-item`, `.btn` get the generic rule only if they're
  `button`/`[tabindex]` (they are `<button>`, so they're covered). The `.chip` spans and `.conn` are non-interactive.

### 3.2 ARIA & semantics inventory

- **Tablist pattern:** aspect rail `<div class="aspect-list" role="tablist" aria-label="Aspects">` with
  `role="tab"` + `aria-selected` on each `.aspect-btn` (JS updates via `setAttribute`). Same for left-panel rail tabs
  (`data-left-tab` toggle sets `aria-selected` + `hidden` on panels).
- **Live region:** toast `<div class="toast" id="toast" role="status" aria-live="polite">` — all action feedback.
- **Labels:** `aria-label` on the rail aside, the shell, project `<select>`, provider select, and every icon button
  (with matching `title` tooltips: e.g. `btn-cmd-k`, `btn-toggle-theme`).
- **Decorative isolation:** `aria-hidden="true"` on all inline SVGs, thumbnails, dots (`mode-badge .pulse`,
  `.conn i`), and the preview media/figure layers.
- **State text, not just color:** mode badge carries a text label ("Review · MCP" / "Agent · built-in"); status pills
  say "ready"/"stale" in text; preview badge "Review artifact · 640×360".
- **Keyboard:** chat textarea sends on `Enter` (Shift+Enter for newline); all interactive elements are real
  `<button>`/`<select>`/`<textarea>` so Tab order works. Tabs are buttons, not arrow-key roving tabindex (mock-level
  simplification).
- **Pointer:** scrub uses `setPointerCapture` + pointercancel handling (touch/pen safe); `user-select: none` on canvas.
- **Persistence:** aspect choice saved to `localStorage` (restored on load, wrapped in try/catch).

### 3.3 Reduced motion — global kill switch

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation: none !important;
    transition: none !important;
  }
}
```

Blunt but complete: every animation and transition is disabled for users who prefer reduced motion. Since all motion is
progressive enhancement (hover tints, state washes, toast, pulse), nothing breaks — states still snap. **Copy this
approach verbatim.**

---

## 4. Responsive behavior

### 4.1 Container tokens

```css
--container-max:            1024px;
--container-gutter-desktop: 22px;
--container-gutter-tablet:  18px;
--container-gutter-phone:   16px;
--section-y-desktop: 100px;  --section-y-tablet: 64px;  --section-y-phone: 40px;
```

(These marketing-page tokens exist but the shell itself uses `--space-5` (20px) padding on `.stage-wrap` — the shell is
an app chrome, not a marketing container. `--container-max` isn't applied anywhere; the app is fluid full-width.)

### 4.2 Base grid (desktop)

```css
.explorer { display: grid; grid-template-columns: 220px minmax(0, 1fr); min-height: 100vh; min-height: 100dvh; }
.aspect-rail { position: sticky; top: 0; align-self: start; height: 100vh; height: 100dvh; ... }
.stage-wrap { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-4); min-width: 0; }
.shell { flex: 1; min-height: 720px; display: grid; grid-template-rows: 48px minmax(0, 1fr) auto;
  border-radius: 22px; overflow: hidden; border: 1px solid var(--studio-line-strong); ... }
.workspace { display: grid; grid-template-columns: 240px minmax(0, 1fr) 260px; min-height: 0; overflow: hidden; }
```

- dvh with vh fallback; sticky rail; timeline is the `auto` row (grows with content); center column min-width 0 so the
  preview can shrink.
- `.stage-header` is `flex-wrap: wrap`; `.chip-row`, `.timeline-toolbar`, `.prompt-chips` all wrap.

### 4.3 ≤ 1100 px — rail becomes horizontal strip

```css
@media (max-width: 1100px) {
  .explorer { grid-template-columns: 1fr; }
  .aspect-rail { position: relative; height: auto; border-right: 0; border-bottom: 1px solid var(--studio-line); }
  .aspect-list { flex-direction: row; overflow-x: auto; padding-bottom: 4px; }   /* horizontal scroll */
  .aspect-btn { min-width: 160px; flex: 0 0 auto; }
  .workspace { grid-template-columns: 200px minmax(0, 1fr) 220px; }              /* panels slim 240→200 / 260→220 */
}
```

### 4.4 ≤ 900 px — workspace stacks, topbar collapses

```css
@media (max-width: 900px) {
  .workspace {
    grid-template-columns: 1fr;
    grid-template-rows: 180px minmax(260px, 1fr) 180px;   /* left / center / right as fixed-height rows */
  }
  .panel-left  { border-right: 0; border-bottom: 1px solid var(--studio-line); }
  .panel-right { border-left: 0; border-top: 1px solid var(--studio-line); }
  .topbar { grid-template-columns: 1fr; padding: 8px 12px; gap: 8px; }
  .topbar-center { order: -1; justify-content: flex-start; }   /* mode badge + provider move to first row */
}
```

### 4.5 Observations / gaps

- No query below 900 px (phone): at small widths the 3-row workspace (180 px panels + 260 px min center) plus 48 px
  topbar will overflow — the mock stops at "tablet" fidelity. The 2-col topbar→1-col at 900 px is the only topbar reflow.
- Timeline keeps its 56px label column + scrollable content; `.timeline-body` has no media query — it stays in place.
- `.shell` min-height: 720 px forces vertical scroll on short viewports (deliberate "studio" minimum).
- `.agent-dock` max-height 210 px with internal `overflow: auto` chat log (bounded chat, no page growth).

---

## 5. Glass, backdrop & special effects

### 5.1 Glass recipe

```css
--studio-glass: color-mix(in oklab, var(--studio-elev-2) 78%, transparent);   /* token defined, used via mixes */

.topbar {
  background: color-mix(in oklab, var(--studio-elev-1) 88%, transparent);
  backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);   /* strongest blur */
}
.agent-dock { background: color-mix(in oklab, var(--studio-elev-2) 85%, transparent);
  backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); }
.preview-badge { background: color-mix(in oklab, black 45%, transparent); border: 1px solid color-mix(in oklab, var(--bg) 14%, transparent);
  backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); }
.toast { background: color-mix(in oklab, var(--studio-elev-3) 92%, transparent); backdrop-filter: blur(12px); ... }
```

Pattern: **glass = color-mix tint at 85–92 % opacity + blur 10–18 px + hairline border**. Topbar is the frosted band;
panels below use flat tints (`elev-1 70%`) — only the chrome above content is blurred. Always ship the
`-webkit-` prefix alongside `backdrop-filter`.

### 5.2 Elevation & ambient glow

```css
.shell { box-shadow:
    0 0 0 1px color-mix(in oklab, var(--bg) 4%, transparent),   /* hairline inner rim */
    0 24px 64px color-mix(in oklab, black 45%, transparent); }  /* deep drop shadow */
.shell::before {   /* ambient accent glow bleeding from top */
  content: ""; position: absolute; inset: 0; pointer-events: none; z-index: 0;
  background: radial-gradient(80% 50% at 70% -10%, color-mix(in oklab, var(--accent) 12%, transparent), transparent 60%);
  opacity: 0.7;
}
.aspect-rail { background:
    radial-gradient(120% 80% at 0% 0%, color-mix(in oklab, var(--accent) 18%, transparent), transparent 55%),
    var(--studio-elev-1); }
```

The "Codex glass" glow = a **radial accent gradient bleeding from one corner/top edge** over a dark elevation fill.
Inside the shell, `.shell > * { position: relative; z-index: 1; }` keeps content above the glow layer.

### 5.3 Preview stage lighting

```css
.preview-stage { background: color-mix(in oklab, black 55%, var(--fg));
  box-shadow: inset 0 0 0 1px color-mix(in oklab, var(--bg) 4%, transparent); }
.preview-media { background:
    radial-gradient(60% 50% at 50% 42%, color-mix(in oklab, var(--accent) 18%, transparent), transparent 70%),
    linear-gradient(180deg, #243044 0%, #121821 55%, #0b1018 100%); }   /* navy scene + center key light */
.preview-figure { width: 28%; aspect-ratio: 3/5; bottom: 8%; left: 50%;
  border-radius: 40% 40% 28% 28%;  /* stylized "person" silhouette */
  background: linear-gradient(180deg, #f4efe4 0%, #e8d9b8 35%, #c9a86a 70%, #8d6a3a 100%);
  box-shadow: 0 18px 40px color-mix(in oklab, black 40%, transparent); }
```

### 5.4 Accent-colored artifacts

- **Logo mark:** 22×22, radius 7, `linear-gradient(145deg, var(--accent), var(--accent-active))` + `0 4px 12px accent 35%`
  glow — the gradient-glow tile is reused by `.thumb` placeholders (`accent 35%` → elev-3 gradient).
- **Timeline clips:** horizontal gradient `accent 55% → accent 28%` over elev-3, 1 px accent border, `0 4px 12px accent
  20%` glow; audio clips = success-green recipe, overlay = warn-yellow recipe. Clips are the colorful objects in an
  otherwise graphite UI.
- **Status pills:** tinted washes + tinted text (`success 16%` bg / `success 30%` text; `.warn` = yellow recipe).
- **Film thumbs:** two-layer gradient (`white 18%` sheen + blue-black `#3a4658 → #0f1420`) to read as video frames.
- **Empty-state ring:** 56 px circle, `border: 1px solid --studio-line-strong`, 4% white fill, centered play icon.
- **Bubbles:** user = accent 22 % wash with `border-bottom-right-radius: 5px` (speech tail); agent = white 6 % wash with
  `border-bottom-left-radius: 5px`; inline `.tool` chips = 10 px mono pills.
- **Danger affordance:** red-tinted ghost (18 % wash, 40 % red text) — destructive actions are *quiet*, not loud.

### 5.5 Color-mix note

Every tint in the file is `color-mix(in oklab, X, Y)` — no rgba literals except the token-level elevation shadows
(`rgba(0,0,0,0.08)`) and `--elev-raised`. This makes the whole system themeable by swapping `--bg`/`--fg`/`--accent`.
The file header even carries a light-theme note in a toast string ("light overrides come in CSS pass").

---

## 6. Interaction patterns worth copying (checklist for PLAN.md)

1. **One motion language:** 150 ms hover/active transitions + `scale(0.97)` on `:active` + 220 ms for state crossfades.
2. **Selection recipe:** `accent 12–16%` background + `accent 40%` border + text to ink. Used identically for buttons,
   list items, tabs.
3. **`:focus-visible` only** focus halo (`--focus-ring` = 4 px accent at 65 % transparent) replacing `outline: none`.
4. **`prefers-reduced-motion: reduce` global kill switch** (`animation: none !important; transition: none !important`).
5. **Pointer-captured scrub** on the timeline (pointerdown/move/up/cancel + `setPointerCapture`, `left: %`, no
   transition on the playhead), `cursor: ew-resize`.
6. **Glow dots** for status (dot + 3 px halo ring); single `softPulse` keyframe for attention (1.8 s, 4 px accent ring).
7. **Glass:** color-mix 85–92 % + blur 10–18 px + hairline border, `-webkit-` prefix included; ambient radial accent
   glow via `::before` on the shell and rail.
8. **ARIA:** tablist/tab + `aria-selected` state driving selection styles; `role="status" aria-live="polite"` toast;
   `aria-hidden` on all decorative glyphs; text labels paired with every status color.
9. **Responsive:** rail→horizontal strip at 1100 px; workspace 3-col→3-row at 900 px; topbar collapses with center
   moved first via `order: -1`.
10. **Known mock gaps to improve on:** no focus ring on project `<select>`; `.rail-tab` has no transition; no phone
    (< 900 px) layout; tabs lack arrow-key navigation.

---

*Report by study agent ref-3 (interactions/motion/responsiveness). All snippets extracted verbatim from the reference file.*
