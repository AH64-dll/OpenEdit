# OpenEdit Review Studio — Round-2 Fresh-Eyes Re-Verification

Date: 2026-08-07  
Reviewer: independent round-2 browser verification  
Servers: `http://127.0.0.1:8000/` (review-only), `http://127.0.0.1:8001/` (full)  
Browser: fresh `/usr/bin/google-chrome-stable` headless profile, CDP port 9571  
Viewport matrix: 1600×1000 and 1200×800 (CDP device-metric override; `innerWidth/innerHeight` verified)  
Themes/screenshots: dark and light

## Evidence protocol

- Did not modify application/source files, run a build, or run the pytest suite.
- Both pages loaded the requested cache-buster live from disk: `style.css?v=20260807-fix4-round2` and `app.js?v=20260807-fix4-round2`.
- Used `window.OpenEdit.selectProject('bd2dd83f126d')`, opened **Edit graph**, clicked the first live `.edit-card`, and expanded the left panel with `#btn-toggle-left-panel`.
- The populated `e2e-demo` timeline rendered 16 live `.timeline-clip` elements.
- Screenshots:
  - [`r2/edit-detail-dark.png`](r2/edit-detail-dark.png) — 1600px dark live edit-detail state.
  - [`r2/edit-detail-light-1200x800.png`](r2/edit-detail-light-1200x800.png) — 1200×800 light live edit-detail state.

## Re-verification table

| Item | Live measurement / screenshot evidence | Result |
|---|---|---|
| **1. Edit-detail panel collisions and long-value wrapping** | At 1200×800 (and again at 1600×1000), `#edit-detail-panel` was `219px` wide (payload `197px`). Every field had key right edge `77.1875px` and value left edge `84.1875px` — a 7px gap, with **0** key/value overlaps. The long `new_asset_hash` value was contained at right edge `218px` (panel right `229px`) and wrapped to `40.5px`/three lines; `clip_id` wrapped to two lines. Computed live styles: field grid `56.1875px 133.812px`, key `min-width: 0px`, `overflow-wrap: anywhere`; no value extended beyond the panel. Evidence is visible in both edit-detail screenshots. | **PASS** |
| **2. Timeline label contrast** | In populated `e2e-demo` (16 clips), live computed styles were video `background-color: rgb(47, 111, 176)` and `color: rgb(255, 255, 255)`, WCAG contrast **5.2219:1**; audio `background-color: rgb(43, 122, 84)` and `color: rgb(255, 255, 255)`, contrast **5.2310:1**. Both exceed the required 4.5:1. The same values/ratios were confirmed on both servers and in light theme. | **PASS** |
| **3. Review/full mode badge identity** | On `:8000`, live `window.OpenEdit.state.reviewOnly === true` and `#mode-label.textContent === "Review · MCP"`. On `:8001`, `reviewOnly === false` and the badge text is exactly **`Agent · built-in`**. Both labels’ data attributes were also present and correct. | **PASS** |
| **4. Duplicate mobile panel toggle buttons** | At both 1600×1000 and 1200×800 on both servers, `#btn-left-panel` and `#btn-right-panel` had `display: none`, zero-size rects, and `offsetParent === null`. In review mode (`:8000`), the desktop pair `#btn-toggle-left-panel` / `#btn-toggle-right-panel` was live and visible (`display: flex`, `offsetParent !== null`) at both widths. On full/agent mode (`:8001`), those controls are deliberately classed `review-only` and are also hidden by the mode-gating rule; therefore the agent UI has no duplicate pair, rather than showing the review-only pair. | **PASS** (duplicate defect fixed; see mode note) |

## New defects observed

No new blocking or major production-quality defects were observed in the exercised surfaces. At the deliberately narrow 219px detail panel, long field **keys** can break at arbitrary characters because `overflow-wrap: anywhere` is the mechanism that prevents collision; they remain within their column and do not overlap values. This is a narrow-rail presentation tradeoff, not the previously blocking collision.

## Final verdict

VERDICT: 100% PASS
