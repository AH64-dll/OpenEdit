# OpenEdit Review Studio — Independent Final Review

Date: 2026-08-07
Reviewer: independent final reviewer (fresh Chrome/CDP session)
Repo: `/home/amr/apps/mlt-pipeline`
Servers checked: `http://127.0.0.1:8000/` (review-only) and `http://127.0.0.1:8001/` (full)
Viewport matrix: 1600×1000 and 1200×800; dark and light themes.

## Evidence protocol

- Started a new headless `/usr/bin/google-chrome-stable` process with a new profile and CDP port 9456; no prior page/session was reused.
- Captured all screenshots in this directory. Screenshots with project data use `e2e-demo` so the note, timeline, render and edit surfaces are real populated DOM states.
- Clicked `#btn-add-note-playhead` after selecting `e2e-demo`; for deterministic CDP interaction `window.prompt` was supplied `Fresh review note`. The resulting note appears in the Review notes modal. Also clicked `#btn-show-notes` directly.
- Clicked `.tab[data-tab="edits"]`, then `.edit-card`, to open the actual `#edit-detail-panel` in both modes.
- Measured logo, pseudo-elements, icon boxes and controls through `Runtime.evaluate`/`getBoundingClientRect`; evidence is in `logo_computed.json`, `full_mode_computed.json`, `review_mode_computed.json`, `review_1200_computed.json`, and `timeline_contrast.json`.
- No application/source files were changed by this review. `FINAL_REVIEW.md` and evidence artifacts are the requested review output.

## Criterion 1 — NO “AI Ray”; professional note and edit surfaces: **FAIL**

### Note component: PASS
The populated Review notes modal is restrained and coherent in both themes. It has an intentional modal hierarchy, consistent note cards, readable timestamp/status treatment, and no gradients/glows/decorative clutter that reads as generated. Evidence:

- `full_dark_1600x1000_note_component.png`
- `full_dark_1200x800_note_component.png`
- `full_light_1600x1000_note_component.png`
- `review_light_1200x800_note_component.png` (review-only mode)

`full_dark_1600x1000_note_component.png` visibly includes the freshly created `Fresh review note`, proving the create-note path was exercised, not just an empty modal opened.

### Edit detail panel: FAIL — **BLOCKING ISSUE 1 (High)**
The edit panel is visibly malformed at the real 240px left rail width. Field labels and values collide/overprint instead of forming a two-column readable detail view. This is especially clear for `originating_note_id`/`null` and `new_asset_hash`/its hash.

Repro:
1. Open either server, select `e2e-demo`.
2. Open **Edit graph** and click the first edit card.
3. Inspect `#edit-detail-panel .edit-detail-field` at 1200×800 (also reproducible at 1600×1000).

Evidence:
- `review_light_1200x800_edit_panel.png`
- `review_edit_panel_zoom.png` (native crop, magnified solely for inspection)
- `full_dark_1200x800_edit_panel.png`
- `full_light_1600x1000_edit_panel.png`

CDP evidence: `#edit-detail-payload` is only 197px wide; its grid is `197px` with the first column resolving to about 56px, while the key labels have no wrapping/overflow protection. The screenshot shows the actual overlapping text, not a theoretical CSS concern. This fails the explicit requirement that the edit panel look professionally designed.

## Criterion 2 — Logo reads as O + classic monitor/TV with antennas and subtle CRT details: **PASS**

The mark reads as a monitor/TV silhouette functioning as the O, followed by `pen Edit`; at native size it is not a blue square. The zoomed crop visibly shows the pair of antennas, inset screen, scanline bands and a restrained diagonal glass/glitch sheen.

Evidence:

- `logo_actual_zoom.png` (native 24×21 mark enlarged for inspection)
- `review_dark_1600x1000_default.png`
- `review_light_1600x1000_default.png`
- `full_light_1600x1000_edit_panel.png`
- `logo_computed.json`

CDP measurements from the live DOM: `.logo-mark` is `24px × 21px`; `::before` has empty content, antenna gradients, `16px × 8px`, `top: -7px`; `::after` has empty content, `16px × 12px`, screen border, inset shadow and a repeating scanline gradient. The details are actually rendered rather than merely implied in source.

## Criterion 3 — Icon positioning, overlap, spacing and hierarchy: **FAIL**

### Icon geometry: PASS
Every visible `.btn svg.icon-svg` checked in the live pages was inside its button bounding box. Header/transport/render SVGs were centered with 14px boxes; no visible interactive-control pair had a positive-area overlap in the pairwise CDP check. Evidence: `review_1200_computed.json`, plus the screenshots above.

### Duplicate desktop/mobile panel controls: **MAJOR, non-blocking but production-defect**
`.mobile-only` panel buttons are visible at desktop widths because a later generic `.btn { display: inline-flex; }` rule overrides the earlier `.mobile-only { display: none; }`. At 1200px review mode, both pairs are simultaneously present:

- `#btn-toggle-left-panel` / `#btn-toggle-right-panel` at x=1005 and 1045
- `#btn-left-panel` / `#btn-right-panel` at x=1085 and 1129

Both pairs are visually identical panel-toggle affordances, creating redundant controls and a noisy/confusing topbar hierarchy. It is also present in full mode at 1600px (`#btn-left-panel`/`#btn-right-panel` at x=1485 and 1529). Evidence: `review_light_1200x800_default.png`, `review_dark_1600x1000_default.png`, `full_light_1600x1000_edit_panel.png`, and exact live measurements in `review_1200_computed.json` and `full_mode_computed.json`.

This is not counted as a blocking issue because the controls do not overlap and remain operable, but it must be fixed for production-quality hierarchy.

## Criterion 4 — Production quality in dark/light and review/full modes: **FAIL**

### Timeline clip labels are effectively unreadable — **BLOCKING ISSUE 2 (High)**
On populated timelines in both themes, video clip labels use `rgb(0,119,237)` over `rgb(60,131,198)`, a measured WCAG contrast of approximately **1.08:1**. Audio labels use `rgb(22,163,74)` over `rgb(47,128,90)`, approximately **1.46:1**. The labels are visibly near-invisible in the captured timeline, undermining the primary review surface.

Repro: select `e2e-demo` and inspect the timeline at the bottom of any populated project screenshot. The issue is in the live rendered CSS for `.timeline-clip.video-clip` and `.timeline-clip.audio-clip`, and is identical in dark and light because the final background rules do not reset the earlier low-contrast text colors.

Evidence:

- `review_light_1200x800_edit_panel_timeline.png`
- `full_dark_1200x800_edit_panel_timeline.png`
- `full_light_1600x1000_project_timeline.png`
- exact DOM colors/rectangles in `timeline_contrast.json`

### Full mode announces the wrong mode — **BLOCKING ISSUE 3 (High)**
At `http://127.0.0.1:8001/`, the live DOM visibly exposes full editing controls (`#llm-provider-select`, model select, chat input and Settings), and `document.body` is not review-only, but `#mode-label` still reads `Review · MCP`. Its own data attributes say `data-agent-label="Agent · built-in"`; that label is never applied. This is a production context/hierarchy error: a user in the full server is told they are in review/MCP mode.

Evidence:

- `full_dark_1200x800_project.png`
- `full_light_1600x1000_edit_panel.png`
- `full_mode_computed.json` (`bodyClass: has-timeline`, `providerVisible: true`, `chatVisible: true`, `modeLabel: Review · MCP`, agent label available as `Agent · built-in`)

### General mode/theme sweep
Fresh default/project captures were taken for both servers, themes and requested viewports:

- Review dark: `review_dark_1600x1000_default.png`
- Review light: `review_light_1600x1000_default.png`, `review_light_1200x800_default.png`
- Full dark: `full_dark_1600x1000.png`, `full_dark_1200x800_project.png`
- Full light: `full_light_1600x1000_edit_panel.png`
- Populated modal/edit states are listed in Criterion 1.

The main graphite/light surfaces, logo and populated note cards are visually coherent, but the edit-panel collision, unreadable timeline labels and wrong full-mode identity prevent a production-quality PASS.

## Final verdict

Three blocking issues remain: (1) edit-detail field collisions, (2) timeline label contrast, and (3) incorrect full-mode badge. The duplicate desktop/mobile panel controls are an additional major non-blocking defect.

VERDICT: FAIL — 3 blocking issues
