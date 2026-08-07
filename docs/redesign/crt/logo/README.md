# CRT Logo — OpenEdit redesign (CRT Logo Specialist)

Deliverable for the retro-CRT redesign of OpenEdit's front-end. The OpenEdit
"O" becomes a CRT television whose SCREEN is the letter "O".

## Files

| File | Purpose |
| --- | --- |
| `crt_logo_snippet.html` | Drop-in replacement for the `<span class="logo" data-od-id="logo">` block in `open_edit/serve/static/index.html` (comments included) |
| `crt_logo.css` | Self-contained stylesheet — pure CSS + inline SVG, no images/fonts/JS |
| `demo.html` | Standalone demo: dark+light topbar context, 18→64px size ramp, phosphor variants (accent / green / amber), 110px detail preview |
| `logo_dark.png`, `logo_light.png` | Headless-Chrome screenshots of `demo.html` (and `?theme=light`) |
| `verify_logo.py` | Contract verification against the live app source + screenshots |

## How to integrate (for the designer)

1. Replace the logo `<span>` in `index.html` with the markup from
   `crt_logo_snippet.html`.
2. Copy `crt_logo.css` to `open_edit/serve/static/` and link it **after**
   `style.css`:
   ```html
   <link rel="stylesheet" href="/crt_logo.css">
   ```
3. Nothing else. The logo region has **zero JS dependencies** (verified:
   `app.js` and `js/*.js` never query the logo).

## Contract preserved

- `.logo` class + `data-od-id="logo"` (82-element id set unchanged)
- `.logo-badge` kept, extended with `.crt-logo` (old chip styles are the
  fallback if `.crt-logo` is ever removed)
- Wordmark text `Open&nbsp;Edit` untouched
- Dark-first; `[data-theme="light"]` overrides via CSS variables (app sets
  `data-theme` on `<html>`; the demo additionally scopes panels)

## Design anatomy (26px badge default)

- **TV body**: rounded bezel (inline SVG `<rect>`), fill `--crt-body`
- **Screen = letter O**: phosphor ring (`--crt-phosphor`, default `var(--accent)`)
  around a glass disc; the hole between the ring's inner edge is the O counter
- **Scanlines**: `repeating-linear-gradient` overlay clipped to the screen circle
- **Curvature vignette**: `radial-gradient` overlay clipped to the screen circle
- **Phosphor glow**: SVG halo ring + CSS `drop-shadow`
- **Glass sheen**: dashed arc (convex-tube highlight)
- **Controls**: channel + volume knobs, power LED (`--green`) with pulse
- **Flicker**: `@keyframes crt-flicker` with `steps(1, end)` ≈ 10–13 fps on the
  screen group, scanlines and vignette (offset timings); sub-pixel `crt-jitter`
  on the SVG; `prefers-reduced-motion` disables all motion
- **Legs + foot bar**: two angled legs

## Tuning knobs (CSS custom properties)

All on `.logo .logo-badge.crt-logo` (dark defaults; `[data-theme="light"]`
overrides):

- `--crt-size` — badge size (set on `.logo`; default 26px; keep square)
- `--crt-phosphor`, `--crt-glow`, `--crt-glow-soft` — screen color/glow
- `--crt-wash-c` — phosphor haze inside the tube
- `--crt-glass`, `--crt-scan-dark`, `--crt-scan-bright`, `--crt-vignette` — tube interior
- `--crt-body`, `--crt-body-stroke`, `--crt-knob`, `--crt-knob-dot`, `--crt-leg`, `--crt-led`

Override any of them inline (see demo's phosphor variants) or in a theme block.

## Verification

```bash
python3 verify_logo.py          # or .venv/bin/python
```

Checks: snippet contract (ids/classes/wordmark), zero JS coupling, CSS
self-containment (no `url()`/`@import`/fonts), theme + reduced-motion coverage,
demo/snippet markup identity, screenshot existence.

## Notes / gotchas found

- **CSS comment trap**: a literal `*/` inside a comment (e.g. `--bg*/--text`)
  terminates the comment early; Chrome's error recovery then silently drops the
  NEXT rule. Use `--bg* / --text` in comments.
- **SVG gradient fills are unreliable in Chrome**: `fill: radial-gradient(...)`
  was dropped at computed-value time and the circle fell back to the SVG UA
  default `fill: black` (invisible on dark glass, black hole on light glass).
  Fixed with solid tint + CSS `mask-image` radial gradient.
