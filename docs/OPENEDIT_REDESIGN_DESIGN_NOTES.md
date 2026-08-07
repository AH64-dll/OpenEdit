# DESIGN NOTES — Open Edit Review Studio redesign

## Chosen design system: `linear-app`

Linear's dark-mode-native "precision engineering" voice is the closest match for a
pro video review tool:

- **Darkness as the native medium** — near-black `#08090a` canvas with
  luminance-stepped surfaces instead of flat greys. NLEs live in this world;
  panels, timeline, and the preview surface read as one continuous instrument.
- **Single desaturated accent** — indigo-violet `#5e6ad2` / `#7170ff`, reserved for
  CTAs, active tabs, focus rings, the playhead. Replaces the old saturated
  teal + rainbow-y status glow. One accent, used at most twice per surface.
- **Weight 510–590 emphasis** — headings at 600 with tight negative tracking,
  body at 400/500, and **tabular numerics** everywhere a timecode, byte count, or
  duration appears (JetBrains Mono kept — it is already the app's mono CDN).
- **Semi-transparent white borders** `rgba(255,255,255,0.08)` and elevation via
  background luminance stepping — no heavy opaque shadows on dark.

## What changed

### Tokens (`:root` + `[data-theme="light"]`)
- Kept the full custom-property architecture (`--bg`, `--accent`, `--radius`,
  `--font-sans`, `--border`, semantic `--green/--yellow/--red`, chat bubble vars).
- **Real light theme**: `[data-theme="light"]` now overrides every token
  (surfaces → `#f5f6f7`/`#fff`, ink → `#1a1b1e`, borders → `rgba(16,17,20,…)`).
  The existing theme toggle is now a working no-op-to-flip — it actually flips.
- Fonts unchanged (Inter + JetBrains Mono via the same Google Fonts CDN);
  `font-feature-settings: "cv01","ss03"` gives Inter Linear's geometric alternates.

### Visual fixes (per brief)
- Pure-black → tinted near-black `#08090a` with a faint radial accent lift on the
  center panel and a **subtle film-grain overlay** (`body::after`, feTurbulence
  noise at ~3% opacity, overlay blend) — texture without noise.
- Consistent tinted shadows: `--shadow-card` / `--shadow-modal` layered stacks with
  a hairline light ring, used on cards, the cmd palette, modals, toasts, and the
  mobile drawer.
- Hierarchy: panel/timeline section headers tightened to `0.06em` uppercase caps
  (was `0.5–0.6px`), display headings get `-0.01em` tracking + `text-wrap: balance`,
  body copy capped at ~65ch (chat bubbles, welcome, empty states).
- **Polish states everywhere**: `:hover` + `:active` + `:focus-visible` rings on
  every button, select, tab, chip, card, and marker; styled scrollbars
  (thumb + hover, `scrollbar-color` for Firefox); loading spinners kept and
  restyled; `prefers-reduced-motion` guard added.

### Structural / a11y
- All **82 element ids preserved** — app.js binds against every one.
- Runtime-built classes all styled: `timeline-clip` (+ `video-clip`/`audio-clip`),
  `timeline-edit-marker` (+`.reverted`), `timeline-note-marker`, `track-kind-badge`
  (+`.video/.audio`), chat `.msg-*`, `.tool-card`, `.render-card`,
  `.user-bubble/.bot-bubble/.tool-bubble` vars, `.btn-*`.
- Added classes the old stylesheet never styled: the **command palette**
  (`.cmd-palette-card`, `.cmd-item`, `.cmd-input-container`) and `.welcome-title`
  previously fell back to unstyled defaults — both now match the system.
- Same 3-column layout, topbar, timeline panel, modals, and toast behaviour;
  review-only / agent-only / collapsed-panel modes unchanged.
- Semantic markup kept identical in intent; added `data-od-id` attributes on
  regions, headings, buttons, and key controls for Inspect/Picker.

## Files
- `index.html` — redesigned markup, same ids, same structure.
- `style.css` — full restyle, dark + real light themes, self-contained.
- `app.js` / `js/*` — **untouched**.
