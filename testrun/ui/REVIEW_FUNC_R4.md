# REVIEW FUNC R4 — DeepSeek V4 Flash (review-func)

**Target:** live http://127.0.0.1:8000 (e2e-demo) · project `bd2dd83f126d`
**Date:** 2026-08-07 · **Method:** Playwright (chromium headless-shell 151) real computed styles, real mouse events, CDP network/log/runtime capture; direct SQLite read; documented pytest command
**Scope:** R3 residual (renders rail presentation via appended `.renders-list .render-card` override) + full regression sweep

---

## 1. Renders rail (`#renders-list`) — **PARTIAL (4/5 sub-items PASS, hover FAIL)**

Appended override verified in `open_edit/serve/static/style.css` lines 2992–3027 (`.renders-list .render-card` block after the studio `.render-card:hover` rule at line 2633).

| Criterion | Result | Evidence (live computed styles, 1440×900) |
|---|---|---|
| Card width ≈ full rail | **PASS** | `.renders-list .render-card` width **239px** = 100% of rail content (rail 239px inside 260px right panel, 10px section padding each side; `width:100%; max-width:none; align-self:stretch`). Target ~229px = full rail. ✓ |
| Thumb flex (🎞️) | **PASS** | `.render-thumb` `display:flex`, visible, 34×34 box, text `🎞️` (U+1F39E+FE0F), font 14px; 13/13 cards have thumb (`display:flex !important` from override). |
| Sub flex + text visible | **PASS** | `.render-sub` `display:flex; flex-wrap:wrap`, visible, box 175×12.5; text: `Review artifact · 640×360 · Ready · 1.4 MB · 8/7/2026, 1:04:15 AM` (card 1). 13/13 subs rendered. |
| Hover changes background | **FAIL** | Real mouse move over card: `:hover` **matches** (`matches(':hover')=true`) but `backgroundColor` **unchanged**: `oklab(0.290253 0.00150616 -0.00518039 / 0.4)` before, during, after (400–500 ms waits; transition is 150 ms). BorderColor also unchanged. **Root cause:** appended `.renders-list .render-card` (line 2998) has equal specificity (0,2,0) to `.render-card:hover` (line 2633) and appears **later** in source order → it permanently wins for `background`, killing the hover overlay (`color-mix(white 7%)`). Fix: append `.renders-list .render-card:hover { background: color-mix(in oklab, white 7%, transparent); }` after line 3027. This is a **regression introduced by the R4 fix itself** — in R3 the same hover changed bg to `oklab(0.999994 …/0.07)` (verified then). |
| Status colors on thumb | **PASS** | Synthetic cards: running `rgb(234,179,8)` = `#eab308` = `--oe-warn` ✓; failed `rgb(220,38,38)` = `#dc2626` = `--oe-danger` ✓; succeeded `rgb(22,163,74)` = `#16a34a` = `--oe-success` ✓ (queued → muted, unspecified). Real cards: 2 succeeded thumbs green, 6 failed thumbs red — matches. |

Rail structure: 13 `.render-card`, **0 `.render-item`** page-wide (both sessions). Cards: `display:grid; grid-template-columns:34px 175px; gap:8px; padding:8px 10px; border-radius:12px; cursor:pointer; background oklab(0.29…/0.4)`.

---

## 2. Regression sweep — **PASS (all items)**

### pytest — PASS
`cd /home/amr/apps/mlt-pipeline && source .venv/bin/activate && python -m pytest tests/ -q --timeout=120 -p no:cacheprovider`
→ **EXIT=0** · progress: **1504 passed, 7 skipped** (3 × timeline-test fixture, 4 × strace fixtures — same set as R2/R3) · **0 FAILED / 0 ERROR**. Logs: `testrun/logs/pytest_r4_reviewfunc.log` (re-run) + `/tmp/pytest_r4b.log`.

### Console / network — PASS
Full-load CDP capture (fresh tab, e2e-demo, exercised play/skip/theme/notes/render-click):
- Responses ≥400: **0** (favicon never requested — inline SVG icons)
- `Runtime.exceptionThrown`: **0** · console error/warning entries: **0** · `Log.entryAdded` errors: **0**
- 6 `Network.loadingFailed` all `net::ERR_ABORTED`, canceled — benign: video element source switches + the 1-byte `_renderEndpointIsReachable` probe (same signature as R3).

### Transport / timeline / theme — PASS
- Play (real click): `▶`→`❚❚`, `paused=false`, `currentTime` 1.417 s, `#tc-current` live `00:01.22`; pause → `paused=true`.
- Skip fwd +5 s: `currentTime` 6.60 s, `#tc-current` `00:06.59`, `#timeline-playhead` left `395.4px` (syncs).
- Timeline: panel present, 3 track rows, 16 clips, 30 edit/note markers, timecode label `00:00.00`.
- Theme: `#btn-toggle-theme` dark→light→dark; `<html data-theme>` toggles; `localStorage['open-edit-theme']` persisted (`light` mid-state).

### Notes timecodes — PASS
Notes modal (JS-actuated `#btn-show-notes`): 3 items with `[00:05.00]`, `[00:10.00]`, `[00:05.00]` — **still `[00:05.00]` format, no 1970 dates, no regressions**.

### Renders dates — PASS
All 13 `.render-sub` dates in **2026** (`8/7/2026, 1:04:15 AM` … `8/6/2026…`); **0** matches for `1970`.

### D2 render job in DB — PASS
`/home/amr/Videos/e2e-demo/.open_edit/render_jobs.db` (direct SQLite):
- Latest row `ca409fa99300495b979308d9b805c9e1` · e2e-demo · proxy · **status=`succeeded`** · created 1786053829.75 (2026-08-07 01:03:49) · updated 1786053855.67 (01:04:15) · `error=null`
- result_json `ok:true`, QC checks passing (`render_completed`, `proxy_render`; 10/10 in R3's full dump), artifact `renders/project_0c4bbbb617bc.mp4` exists **1,440,468 B**
- Live UI: preview auto-loaded `/api/projects/bd2dd83f126d/renders/ca409fa99300495b979308d9b805c9e1/file`, `readyState 4`, 640×360, duration 28.77 s.

---

## Caveat (pre-existing, out of R4 scope)
On 1440×900 the notes `View`/`Note here` buttons at the bottom of the right panel sit at y≈945 and **cannot be clicked** via hit-testing: `.layout { height: calc(100vh - var(--topbar-h)) }` (legacy) makes the right panel extend under the full-width `.timeline-panel` (z-index 2, rows `48px 1fr 180px`), which covers the bottom 180 px (y 720–900); even fully scrolled the button tops out at y=757. JS `.click()` opens the modal fine (content verified). Not caused by the R4 override (CSS block touches only `.renders-list` children); present in R3 as well.

---

## Verdict
- **Item 1 (renders rail): PARTIAL — FAIL on hover** (width/thumb/sub/status colors all live-verified PASS; hover background dead, regressed by the appended override's specificity/order).
- **Item 2 (regression sweep): PASS** — pytest exit 0 (1504/7/0), console clean, transport/timeline/theme OK, notes `[00:05.00]` intact, render dates all 2026, D2 job `succeeded` in DB with artifact on disk.
- **Confidence: 88/100** — every claim reproduced live (computed styles, real mouse, CDP events) across 4 independent browser sessions + direct SQLite + documented pytest; the single failure is precisely root-caused (specificity/source-order) with a one-line fix.
