# Review Studio Visual Review — Vision R3

**Reviewer:** review-vision R3 (GPT-5.6 Luna, vision)  
**Date:** 2026-08-07  
**Scope:** A (design fidelity), B (logo), D (layout), plus the two post-R2 visual fixes (notes timecode and renders-rail `.render-card`).

## Evidence inspected

- `testrun/ui/shots/main-r3.png` — 1600×913 fresh capture with `e2e-demo (9 assets)` selected and the Review notes modal open.
- `testrun/ui/shots/main-project-wide.png` — 1600×913 prior selected-project capture, used for the unobscured studio/rail comparison.
- Supplementary fresh 1600×913 CDP capture of the same review-only page (`/tmp/r3-live.png`) and computed styles, solely to inspect the rail behind the modal backdrop.

## Verdict summary

| Item | Verdict | Evidence |
|---|---|---|
| A — dark graphite + blue studio / no CRT treatment | **PASS** | Unobscured selected-project capture is neutral graphite with blue controls; no scanline/vignette/CRT-green/amber treatment is visible. Exact pixel counts in `main-project-wide.png`: `#33ff66` = 0, `#ffb000` = 0. |
| B — monitor-O logo | **PASS** | Topbar visibly reads monitor mark + “pen Edit”; the mark is a rounded blue monitor/squircle with inset screen/bezel and no inner glyph. |
| D — desktop layout | **PASS** | 1600×913 frame keeps a broad center preview, narrow right RENDERS rail, and full-width bottom timeline; `e2e-demo (9 assets)` is selected and no rail/center swap or collapse is visible. |
| Notes timestamp fix | **PASS** | `main-r3.png` modal visibly shows `[00:05.00]`, `[00:10.00]`, `[00:05.00]` rather than wall-clock dates/1970. |
| Renders rail `.render-card` styling fix | **FAIL (partial)** | Fresh unobscured capture still shows name-only rows: no visible thumb or metadata subline. CDP computed styles confirm each `.render-card` is ~210.3px wide in the 260px rail (90%-width override), `.render-thumb` is `display:none`, and `.render-sub` is `display:none`. `cursor:pointer` and the hover selector exist, but the required full studio card presentation is not rendered. |

## A — Design fidelity: **PASS**

The selected-project view retains the dark graphite studio shell: charcoal topbar, center surface, right rail, pale gray text, and blue action/play accents. The prior unobscured capture (`main-project-wide.png`) shows no CRT scanlines, vignette, flicker, or neon green/amber chrome. Saturated color bars are confined to the preview media and muted green/amber timeline semantics, not the studio shell. The fresh R3 image is dimmed by the notes modal backdrop, as expected, but no visual regression is apparent in the underlying shell.

As a pixel sanity check on the unobscured frame, exact prohibited CRT colors are absent: `#33ff66` count **0** and `#ffb000` count **0** in the complete 1600×913 screenshot.

## B — Logo: **PASS**

The top-left mark is visibly a blue rounded monitor/squircle replacing the O position, followed by the `pen Edit` wordmark. It has a rounded outer bezel, inset screen, blue gradient/glow treatment, and no literal inner O/play glyph. Its optical scale is balanced with the wordmark; the previous R2 logo sizing regression is not visible in the R3 topbar.

## D — Layout: **PASS**

The 1600×913 selected-project capture maintains the expected arrangement: a broad center preview/player, a compact right RENDERS rail, and the timeline spanning the bottom. The `e2e-demo (9 assets)` project control is selected. The left rail remains out of the desktop composition without stealing center width; the center preview remains dominant and the right rail remains in place. The notes modal dims/blur the image in `main-r3.png`, but this is modal behavior rather than a layout regression; the unobscured comparison confirms the geometry.

## Post-R2 fix: notes timestamps — **PASS**

The fresh R3 notes modal directly shows timeline timecodes:

- `[00:05.00] · typed · pending`
- `[00:10.00] · typed · pending`
- `[00:05.00] · typed · pending`

This resolves the previous `1/1/1970` presentation problem and is legible in the supplied R3 evidence.

## Post-R2 fix: renders rail cards — **FAIL (partial)**

The supplied unobscured comparison and a fresh unmodalized capture show the renders rail as a stack of rounded name-only pills. The expected thumb + metadata composition is not visible. Direct live computed-style evidence from the fresh capture:

- first card class: `render-card render-status-succeeded`;
- card rect: approximately `x=1351`, `width=210.3125px`, `height=32.5px` while the rail is 260px wide;
- `cursor: pointer` is present;
- `.render-thumb`: `display: none`, 0×0 rect;
- `.render-sub`: `display: none`, 0×0 rect;
- card width resolves to the later `width: min(90%, 680px)` rule rather than the full rail width.

Therefore the class rename is present and pointer behavior/hover selectors are present, but the visual acceptance criterion (“full-width cards with thumb+meta”) is not met. This is a concrete presentation regression/partial fix, not a concern about the modal or media content.

**Recommended fix/re-verify:** scope the chat `.tool-card` styling away from rail render cards (or add a later, higher-specificity `.renders-list .render-card` override), remove the rail card hiding rules for `.render-thumb`/`.render-sub`, and force `width: 100%` within `.renders-list`. Recapture at 1600×913 with the notes modal closed; confirm visible 34px thumb + name/sub metadata, full rail width, pointer cursor, hover border/background, and no name-only pills.

## Final verdict

- **A — PASS**
- **B — PASS**
- **D — PASS**
- **Notes timecode — PASS**
- **Renders rail card visual fix — FAIL (partial)**

**VERDICT: FAIL** — the main studio, logo, layout, and notes timestamp fix pass, but the renders-rail card styling does not yet visually satisfy the requested thumb + metadata/full-width criterion.

**Confidence: 99/100.** The failure is directly visible in the fresh unmodalized capture and corroborated by computed styles; 100% is not claimed because the supplied `main-r3.png` itself has the rail behind a blur backdrop.
