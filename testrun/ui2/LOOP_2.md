# Loop 2 — Typography and icon system

## Designer findings
The live UI still had emoji/glyph controls in render cards, command palette commands, transport play state, timeline kind badges, dependency/upload statuses, and imported asset/chat modules. These varied by platform font and undermined alignment.

## Changes
- `open_edit/serve/static/js/dom.js`: added a small `icon()` SVG vocabulary with 15×15 viewBox, inherited currentColor, accessible hidden semantics, and stroke geometry.
- `app.js`: converted render thumbnails, command palette icons, play/pause state, timeline badges, dependency rows, and upload outcomes to SVG nodes.
- `js/assets.js`: converted media-type emojis to shared SVG icons.
- `js/chat.js`: converted gear/status/warning/cross glyphs to shared icons or neutral text labels.
- `index.html`: bumped style/app cache-busters to `20260807-loop2-icons-loop3-type`.

## Verification
- Broad emoji scan over all imported static JS plus index/style: **0 hits**.
- `node --check` app.js, dom.js, assets.js, chat.js: **all pass**.
- Targeted UI tests: `54 passed` (`test_review_ui.py` + `test_html_overlay.py`).
- Screenshot: `testrun/ui2/shots/review_after_loop3.png`.

**LOOP 2 VERDICT: PASS — confidence 98%; all live glyph controls replaced, syntax/tests clean, and screenshot confirms aligned controls.**
