# Review Studio Visual Review — Vision R1

**Scope:** Stage 3 visual review of A (design fidelity), B (logo), and D (layout/responsive) only. Evidence was inspected directly; Stage 2 claims were not used as evidence.

**Evidence inspected**

- Post-fix selected-project views: `testrun/ui/shots/main-project-wide.png` (1600x1000 at inspection time) and `/tmp/ui_v4_cdp.png` (1600x913).
- `/tmp/ui_v3_main.png` and the supplied `shots/main.png`, `timeline.png`, `renders.png`, and `chat.png`.
- `/tmp/ui_logo_crop.png` (2x top-bar crop).
- Live DOM/CSS at `http://127.0.0.1:8000/`, source `open_edit/serve/static/{index.html,style.css}`, and live CDP computed styles at 1600x1000, 1440x900, and 800x900.

## A — Design fidelity: **PASS (with concerns)**

### Direct visual/pixel evidence

- The post-fix selected view is a dark graphite studio: sampled chrome pixels include `(28,28,30)`, `(30,30,32)`, and `(35,35,37)` rather than the former CRT-green/amber palette. The center video is present and is clearly media content, not UI chrome.
- In `main-project-wide.png`, exact pixel counts for `#33ff66` and `#ffb000` are both **0**; the same exact counts are 0/0 in `/tmp/ui_v4_cdp.png`. The topbar and right rail each have 0 bright-green and 0 bright-amber pixels under the region test.
- The very large bright-green/amber counts in the full post-fix frame are confined to the supplied color-bar video (`114,402` bright-green and `2,029` bright-amber pixels in the video viewport). The timeline contains only a small muted semantic warning hue (`111` bright-amber-threshold pixels); it is not `#ffb000`. This distinction matters: pixel-sampling the entire screenshot without excluding the video would misattribute the test media to the studio UI.
- The supplied older `shots/main.png`, `timeline.png`, `renders.png`, and `chat.png` visibly show alternating CRT scanlines and an unselected/empty project. A row-median test in their right-rail region has a strong 4-row correlation (`~0.999`) versus `~0.15` in the post-fix frame. These are stale/contradictory captures and should not be used as final-state visual evidence; they do warrant recapture (see concerns).

### CSS/DOM/computed-style evidence

- `style.css` defines the studio palette as `--studio-bg: #1a1a1c`, `--studio-elev-1: #1c1c1e`, `--studio-accent: #0071e3`, and radius tokens 8/12/18/980. The final compatibility palette likewise uses `--accent: #0071e3`; prohibited literal `#33ff66` and `#ffb000` do not occur in the stylesheet.
- Live computed styles at 1600x1000: `body` background `rgb(26,26,28)`, `.panel-center` background `rgb(26,26,28)`, and `.topbar` has `backdrop-filter: blur(18px)`. Play and playhead both compute to `rgb(0,113,227)` (`#0071e3`); active tab uses an accent-tinted background.
- Live `body::before` and `body::after` both compute to `content: none`, `display: none`, `opacity: 0`, `background-image: none`, and `animation: none`. No scanline/grain/vignette/flicker is rendered in the post-fix screenshots.

**A concern:** The stylesheet still contains duplicated legacy CRT declarations/keyframes (including old `body::before/after`, `.crt-tv-screen`, and `crt-flicker`) earlier in the file; the final shutdown override makes them inert and the DOM has no `.crt-tv-screen`. Removing the dead declarations would reduce regression risk. There are also muted semantic `--studio-success: #16a34a` and `--studio-warn: #eab308` colors for audio/status/markers. They are not the prohibited neon values and are not visible in the topbar, but if “single Apple-blue accent” is intended to ban *all* semantic hues, those timeline/status selectors need an explicit product decision.

## B — Logo: **FAIL (optical-size mismatch; monitor construction itself passes)**

### Direct visual/DOM evidence

- `/tmp/ui_logo_crop.png` clearly shows a blue rounded monitor/squircle in the O position, with a bezel/screen inset, gradient, and blue glow. There is no literal O glyph inside it; visually the wordmark is the mark followed by `pen Edit`.
- `index.html` lines 20–23 are:

  ```html
  <a class="logo" ... aria-label="Open Edit">
    <span class="logo-mark" aria-hidden="true"></span>
    <span class="logo-text">pen&nbsp;Edit</span>
  </a>
  ```

  `.logo-mark` has no text node, `.crt-tv-screen` is absent from the live DOM, and `logo-mark.textContent === ""`.
- At live 1600x1000 CDP: `.logo-mark` is `22px × 22px`, border-radius `7px`, with a blue linear-gradient background and a 1px bezel. Its `::after` pseudo-element has `inset: 5px`, a 1px border, rounded corners, a screen gradient, and an inset highlight/glass shadow. This satisfies the monitor/squircle construction and glow requirements.
- However `.logo-text` computes to **font-size 13.5px / line-height 13.5px**, due the earlier `.logo-text { font-size: 13.5px; }` rule (around `style.css` line 200). Its rect is 51.89×13.5px while the mark is 22px high. Thus text-font/mark ratio is **0.614**, not the rubric's approximately 0.72–0.75 (about 16/22); the mark is visibly about 1.63× the text font in the crop. The later `.logo { font-size: 16px; }` does not override the child’s explicit 13.5px size.

**Required fix/re-verify:** Set the final `.logo-text` font size/line-height to the intended ~16px (or otherwise tune the mark/text optical proportions), reload the live page, re-run CDP `getComputedStyle` and rect checks, and recapture `/tmp/ui_logo_crop.png`. Re-review that the monitor remains 22px and no inner O text appears.

## D — Layout & responsive: **PASS**

### Live CDP computed evidence

- At **1600×1000** with `body` classes `review-only-mode panel-left-collapsed`: layout grid is exactly `0px 1340px 260px`; left panel is a 0px hidden track, center is visible at 1340px, right rail starts x=1340 and is 260px wide. The preview video is visible at x=13, width=1314, height=680.
- At **1440×900**: grid is `0px 1180px 260px`; center is visible at 1180px and video is visible at 1154px wide; right rail remains 260px at x=1180.
- At **800×900**: responsive layout has one `780px` column; center preview is visible at 780×390 and video is visible at 754×425. The collapsed left/right rails are absolute off-canvas (`x=-320` / `x=780`) with the expected ±320px transforms, so they do not steal width or create a zero-width preview. Timeline remains a separate responsive row. This confirms no zero-width center track or rail swap at the tested narrow width.
- The post-fix selected screenshots visually agree with the 1600 layout: broad center video, narrow 260px renders rail, and no visible left assets rail.

## Concern list / re-verification

1. **Mission-critical logo size:** fix `.logo-text` from computed 13.5px to approximately 16px, then repeat DOM/computed-size and crop checks. This is the reason B is FAIL.
2. **Stale screenshot set:** the older four `shots/*.png` captures still visibly contain CRT scanlines and no selected project. Re-capture them from the post-fix selected state before using them as release evidence.
3. **Dead CRT CSS:** remove or isolate duplicated legacy scanline/vignette/grain/flicker declarations, or retain the final shutdown override plus a regression assertion that pseudo-elements remain inert and `.crt-tv-screen` is absent/hidden.
4. **Semantic hue interpretation:** if reviewers interpret “single Apple-blue accent” literally, decide whether the muted green audio/status and amber warning marker should be recolored; current direct pixel evidence shows no prohibited neon green/amber in chrome.

## Vision verdict

- **A: PASS (with source/stale-evidence concerns)**
- **B: FAIL (optical sizing; monitor/no-inner-glyph construction passes)**
- **D: PASS**
- **Overall confidence: 93/100** for these visual/layout findings.
- **VERDICT: FAIL** (not eligible for `VERDICT: PASS`; B has a concrete computed-style mismatch and there are listed evidence concerns).
