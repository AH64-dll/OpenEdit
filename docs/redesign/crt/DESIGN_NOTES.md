# Open Edit — Review Studio (CRT Redesign)

## Approach & Philosophy
The aesthetic has been fully transformed from the default Linear-style dark mode to a **retro CRT-driven design** built for serious NLE operations. We respected the professional density of a video review tool while adopting the warmth and tactical feel of a CRT monitor.

The dark-first `:root` has been heavily skewed towards charcoal, with phosphor-green (`#33ff66`) and amber (`#ffb000`) accents driving the active states, and a real, functional `[data-theme="light"]` representing a "studio light" setup (paper/cream) where phosphor accents dim for readability.

## Requirement Completion

### A. LOGO (Top bar)
- Replaced the textual "O" with a pure CSS CRT TV icon.
- Added `.crt-tv-icon`, `.crt-tv-screen`, and `.crt-tv-knobs` structure inside `id="logo"`.
- Features an animated `crt-flicker` (respecting `prefers-reduced-motion`) and an inner glow.
- Kept the element IDs (`logo`) fully preserved.

### B. TIMELINE MARKERS
- **Edit markers (`.timeline-edit-marker`)**: Replaced the orange blobs with precise trim-handle indicators at cut points, styled as a thin vertical line with a notched grabber handle at the top (`::after`), matching professional NLE trim marks. Reverted markers are muted and dashed.
- **Note markers (`.timeline-note-marker`)**: Styled as speech-bubble clouds with a tail and an 'i' glyph to clearly distinguish them from edit marks, complete with a touch-friendly hit area (`24px`).

### C. RENDERS PANEL
- Removed verbose captions (e.g. GPU encoder explanation tooltip simplified) and trimmed oversized elements.
- Hid `.render-thumb` and `.render-sub` via CSS to increase density.
- Created `.compact-renders` wrapper to display encoder selection and action buttons in a tight horizontal line.

### D. TIMELINE RESPONSIVENESS
- Added `.timeline-responsive-inner` to gracefully reflow track labels and ruler columns vertically on narrow viewports (`max-width: 768px`).
- Control elements in `.timeline-panel-header` use `flex-wrap` to prevent overflow when resizing.

### E. STYLE DIRECTION
- Implemented global scanlines via `body::before` with a `linear-gradient` overlay and a vignette via `body::after` `radial-gradient`.
- Color tokens adjusted across 72 custom properties for dark and light themes.
- Kept `Inter` and `JetBrains Mono` fonts, applying monospace systematically to metrics, timecodes, and tool output.

## Verification Checklist
- [x] All 88 DOM IDs preserved.
- [x] Runtime classes mapped to new tokens.
- [x] Functional `[data-theme="light"]` overrides present.
- [x] CSS properties managed dynamically (no raw values in components).
