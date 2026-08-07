# CRT redesign — Renders Panel (specialist deliverable)

Owner: Renders-Panel specialist (child agent of the CRT redesign coordinator).
Target: `open_edit/serve/static/index.html` right panel — `#right-panel` →
`#renders-list` → `.render-item` cards (built by `app.js → renderRendersList()`).

## Files

| File | Purpose |
|---|---|
| `renders_panel.css` | **The deliverable.** Append-safe CSS override (dark-first, `[data-theme="light"]` overrides included). Zero JS/markup changes required. |
| `renders_panel.patch.html` | Optional index.html region patch (old→new snippet, same ids/classes) + optional one-line app.js hook for per-mode card colors. |
| `demo.html` | Old-vs-new side-by-side demo. Left column = current `style.css` rules extracted verbatim; right column = same markup + this CSS. `?theme=light` presets light theme. |
| `renders_demo.png` | Screenshot, dark (default). |
| `renders_demo_light.png` | Screenshot, light theme (bonus evidence). |
| `build_demo.py` | Rebuilds `demo.html` from the real `style.css` + `renders_panel.css`. |
| `verify_renders_contract.py` | Contract verification (ids, runtime classes, no static changes, CSS hygiene, pixel evidence). |

## What changed (declutter)

**Kept:** render name (now mono), mode + status line, click-to-load preview
(primary action), encoder select, Render proxy / Render final, refresh button,
empty state. All ids/classes identical to what app.js builds.

**Removed/softened (CSS-only):**
- 34px emoji tile → 26px status-tinted tile (emoji demoted to a quiet glyph).
- Noisy meta tail (`· 24.6 MB · 8/6/2026, 4:12:03 PM`) → truncated to one dim
  mono line via ellipsis (mode + status always visible; text nodes can't be
  split without JS, truncation removes the visual noise).
- Full-width 110px-min buttons → compact auto-width, color-coded actions.
- Unbounded list that pushed Notes/Style out of the panel → list owns the
  remaining height and scrolls internally (thin CRT-green scrollbar).
- Floating emoji as the only status signal → status LED bar + border/glow
  color coding (single `--crt-led` source per card).

**Color coding** (via `--crt-led`, falls back to status colors when the
optional mode classes are absent):
- succeeded = phosphor green `#3dffa2` · running/queued = cyan `#3fd9f0` ·
  failed = red `#ff5d5d` (dark); light theme flips to `--green`/`#0e7490`/`--red`.
- Optional: `render-mode-proxy` (cyan) / `render-mode-final` (green) per-card
  colors activate if app.js adds one additive class token (patch §3).

## Install

```html
<link rel="stylesheet" href="style.css">
<link rel="stylesheet" href="css/renders_panel.css">   <!-- append after style.css -->
```

## Verify

```bash
cd docs/redesign/crt/renders
/home/amr/apps/mlt-pipeline/.venv/bin/python verify_renders_contract.py
# rebuild the demo after edits:
/home/amr/apps/mlt-pipeline/.venv/bin/python build_demo.py
```

Known contract facts honored: real aside id is `right-panel` (class
`panel-right`); render cards carry only `render-status-*` classes (no mode
class — see patch §3 for the optional hook); `setRenderButtonsBusy()` rewrites
button textContent, so button text is untouched.
