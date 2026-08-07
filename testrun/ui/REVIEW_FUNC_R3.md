# Stage 3 Functional Review — REVIEW_FUNC_R3 (DeepSeek V4 Flash)

Date: 2026-08-07 · Reviewer: review-func (round 3) · Scope: re-verify the two R2 residuals (D1-notes, D4-CSS), regression sweep (pytest, console, transport/timeline/theme), D2 render end-to-end
Method: live server http://127.0.0.1:8000 (review-only, pid 8262 `open_edit.cli serve --review-only --port 8000`, serves the current working tree — md5(served css/js) == md5(disk) verified) · headless Chrome 151 via raw CDP (two independent sessions, Network/Log/Runtime capture, real Input mouse events for hover/play/seek) · node unit-check of `formatTimecode` · SQLite direct read of render_jobs.db · pytest (documented command).

## Verdict summary

| Item | Verdict | One-line evidence |
|---|---|---|
| D1-notes (timecode fix) | **PASS** | Live notes modal shows `[00:05.00] · typed · pending`, `[00:10.00] · typed · pending`, `[00:05.00] · typed · pending` — timecodes, zero `1970` (two sessions) |
| D1 renders-list dates (regression) | **PASS (DOM) / caveat (visible)** | `.render-sub` textContent still holds real 2026 dates (`8/7/2026, 1:04:15 AM`), no 1970 anywhere; BUT the subline is `display:none !important` (pre-existing duplicated CSS block, lines 1824/2046) so dates are not painted — corroborated by vision R3 |
| D4-CSS (studio selectors) | **PASS** | `.render-card` computed: `display:grid`, `cursor:pointer`, width 210.3px (>200px); real-mouse hover changes background and `:hover` matches; **13 `.render-card`, 0 `.render-item`** in `#renders-list`; 4 studio selectors + legacy alias confirmed in source |
| Regression — pytest | **PASS** | exit 0 · 1504 run (1497 passed, 7 skipped), 0 failed, 0 errors (log `testrun/logs/pytest_r3_reviewfunc.log`) |
| Regression — console scan | **PASS** | 0 responses ≥400 (no non-favicon 404s; favicon not requested — inline data: SVG), 0 exceptions, 0 error logs; only 4 benign `ERR_ABORTED` cancellations (media/range probes) |
| Regression — transport/timeline/theme | **PASS** | real-click play ▶→❚❚ with timecode advancing; skip fwd/back ±5s syncs playhead+label+player; timeline click-to-seek 25%→00:05.37 / 75%→00:18.53 (player.currentTime 18.533 matches); theme dark↔light↔dark persisted to localStorage |
| D2 (render still succeeds) | **PASS** | Latest render_jobs.db row (rowid desc): job `ca409fa9…` e2e-demo/proxy **status=succeeded**, ok=true, elapsed 11.17s, QC 10/10 passed; mp4 exists 1,440,468 B, mtime 01:04:15 matches updated_at |

**Overall: PASS** (both R2 residuals fixed and verified live; all regressions green) — confidence 92/100.
Single pre-existing caveat (not introduced by the R3 fixes): the renders rail hides `.render-thumb`/`.render-sub` (`display:none !important` from a duplicated ~4.6 KB CSS section) → cards show name-only; the 2026 dates exist in DOM but are not visible. Vision R3 flags the same as FAIL(partial) for the rail presentation.

---

## D1 — Notes modal timecode fix → **PASS** (R2 residual fixed)

### Source (coordinator's fix, confirmed in app.js `openNotesModal`)
```js
el('div', { class: 'note-ts' }, [
  // Note timestamps are playhead anchors (seconds in the timeline), so
  // show them as timecodes — not as wall-clock dates.
  `[${formatTimecode(Number(n.timestamp) || 0)}] · ${n.source} · ${n.status}`,
]),
```
`formatTimecode` unit check (node, extracted from served app.js):
```
0      -> 00:00.00      5    -> 00:05.00     10   -> 00:10.00
28.59  -> 00:28.59      61.5 -> 01:01.50     125.25 -> 02:05.25   3600.75 -> 01:00:00.75
```

### Live (e2e-demo selected, two independent Chrome sessions)
`#btn-show-notes` → `#modal-notes` → `#notes-list .note-ts` innerText:
```
[00:05.00] · typed · pending
[00:10.00] · typed · pending
[00:05.00] · typed · pending
```
Modal innerText contains **no `1970`** in either session; note texts unchanged (`review-func test note at playhead` ×3). Server payload still `timestamp: 5.0 / 10.0 / 5.0` (playhead seconds) — the timecode rendering is the correct interpretation. **R2's residual D1-notes is fixed.**

## D1 — Renders list dates (regression check) → PASS at DOM level, caveat: not visible

`fmtTime` untouched by the R3 fixes (renders path unchanged). Live `#renders-list`:
- `.render-card .render-sub` textContent (all 13 cards): real 2026 dates, e.g. `Review artifact · 640×360 · Ready · 1.4 MB · 8/7/2026, 1:04:15 AM`, `… Failed: Overlap on track a1 … · 8/6/2026, 7:11:47 AM`.
- Zero `1970` strings in the whole renders list DOM (textContent); zero in body innerText.
- **Caveat:** `getComputedStyle(.render-sub) = display:none`, `getBoundingClientRect = 0×0`, `offsetParent === null` → the subline is **not painted**. The only visible card content is `.render-name`. Root cause: a pre-existing duplicated ~4.6 KB CSS section (`.compact-renders` … `.timeline-responsive-inner`, two copies at offsets 48871/53471) each containing
  ```css
  .render-card .render-thumb, .render-item .render-thumb,
  .render-card .render-sub, .render-item .render-sub { display: none !important; }
  ```
  (lines 1824 and 2046). This is **not** from the coordinator's D4 fix (that edit was 5 targeted `str.replace` ops on the studio selectors + legacy alias — verified in the coordinator session log; it never touched these blocks) — it pre-dates R3 in the redesign tree. Vision R3 (Luna, pixel-level) independently flags the same: renders rail shows name-only rows.

## D4 — Studio `.render-card` styling → **PASS** (R2 residual fixed)

### Source (coordinator's fix, verified in style.css + coordinator session log)
4 studio selectors renamed `.render-item` → `.render-card` (`.asset-card, .edit-card, .render-card, .note-item`, the `:hover` and `:active` variants, and `.render-card { grid-template-columns: 34px minmax(0,1fr); cursor: pointer; }`) + legacy block header aliased to `.render-item, .render-card { display: flex; … }`.

### Live computed styles (`#renders-list .render-card`, e2e-demo)
| Property | Value | Criterion |
|---|---|---|
| display | `grid` | ✓ |
| cursor | `pointer` | ✓ |
| width | `210.312px` (260px rail minus padding) | ✓ ~>200px |
| grid-template-columns | 34px minmax(0,1fr) layer | ✓ (thumb col 34px, meta col ~150px) |
| border-radius / background | 12px / oklab surface 40% | ✓ studio card |

Hover (real CDP mouse move, `:hover` matches):
- before: `background: oklab(0.290253 … / 0.4)`
- after: `background: oklab(0.999994 … / 0.07)` (white 7% overlay per `.render-card:hover` rule) → hover affordance works.

Class drift: `#renders-list` has **13 `.render-card`** and **0 `.render-item`**; page-wide `[class*="render-item"]` count = **0** (two sessions). **D4 fixed.** (Presentation caveat: thumb+sub hidden by the pre-existing `display:none` block above — separate from the selector fix.)

## Regression sweep

### pytest — PASS
`cd /home/amr/apps/mlt-pipeline && source .venv/bin/activate && python -m pytest tests/ -q --timeout=120 -p no:cacheprovider` → **EXIT=0** (63.5 s). Progress stream: 1497 dots + 7 `s`, **0 F / 0 E**; 7 SKIPPED entries (timeline-test fixture, strace fixtures — same as R2); 0 FAILED/ERROR lines. Log: `testrun/logs/pytest_r3_reviewfunc.log`.

### Console scan — PASS
Full-load CDP capture (fresh tab, Network/Log/Runtime enabled before navigation, e2e-demo selected, then exercised notes/settings/theme/transport):
- Responses ≥400: **0** (favicon not requested — inline data: SVG icons; no non-favicon 404s).
- `Runtime.exceptionThrown`: **0** · `Log.entryAdded` error/warning: **0**.
- 4 `Network.loadingFailed` all `net::ERR_ABORTED`, `canceled: true` — benign: video element switching sources + the 1-byte `Range` reachability probe (`_renderEndpointIsReachable` cancels its body). Not errors.

### Transport / timeline / theme — PASS
- Play/pause (real mouse click): `▶`→`❚❚`, `player.paused=false`, `currentTime` advancing, `#tc-current` live-updates (00:01.26 at 1.45 s). (Programmatic `.click()` is blocked by headless autoplay policy; real input events work — environmental, not a product defect.)
- Skip fwd/back: `#tc-current` 00:00.00 → 00:05.00 → 00:00.00; `#timeline-playhead` left 300px → 0; `#timeline-timecode-label` matches.
- Timeline click-to-seek (real mouse): 25% → 00:05.37, 75% → 00:18.53; `player.currentTime` = 18.533333 (exact sync).
- Theme: `#btn-toggle-theme` dark→light→dark; `data-theme` on `<html>`; `localStorage['open-edit-theme']` persisted.
- D3 re-check (regression): settings modal still shows review-mode notice and fires **zero** network requests after open (no `/api/runtimes`, no `/api/settings/keys`, no 404s).

## D2 — Render still succeeds end-to-end → **PASS**

`/home/amr/Videos/e2e-demo/.open_edit/render_jobs.db` (direct SQLite):
- Latest row by rowid: `ca409fa99300495b979308d9b805c9e1` · project e2e-demo · mode proxy · **status=`succeeded`** · created 1786053829.75 (2026-08-07 01:03:49) · updated 1786053855.67 (01:04:15)
- result_json: `ok: true`, `elapsed_sec: 11.17`; qc_report: `passed: true`, 10/10 checks (render_completed, proxy_render, streams, duration 28.77 vs 28.59 Δ0.18 s, audio_sync Δ0.001 s, black_frames, frozen_frames, silence, overlays_burned, thumbnail)
- Output `renders/project_0c4bbbb617bc.mp4` exists, 1,440,468 B, mtime 01:04:15.347 — matches updated_at (fresh)
- Preceding failed row (`f325c6b1…`, 00:49) is the historical template_not_found failure, superseded; no new failures since
- Live UI: preview auto-loaded `/api/projects/bd2dd83f126d/renders/ca409fa99300495b979308d9b805c9e1/file`, readyState 4

## Verdict
- D1-notes: **PASS** — the exact R2 residual (1970 dates in notes modal) is fixed; timecodes `[00:05.00]`/`[00:10.00]` verified live in two sessions, `formatTimecode` unit-verified.
- D4-CSS: **PASS** — all computed-style criteria met (grid, pointer, 210 px, hover), 0 `.render-item` page-wide.
- Regression: **PASS** — pytest exit 0 (1497/7/0), console clean (0 ≥400, 0 exceptions, benign aborts only), transport/timeline/theme all functional, D3 settings gating intact.
- D2: **PASS** — latest render_jobs.db row succeeded with ok=true and QC 10/10; artifact on disk.
- **Caveat (pre-existing, follow-up):** duplicated ~4.6 KB CSS section hides `.render-thumb`/`.render-sub` (`display:none !important`, lines 1824/2046) → renders rail is name-only; 2026 dates are in the DOM but not painted. Introduced by the earlier redesign, not by the R3 fixes; vision R3 agrees (FAIL-partial on rail presentation).
- Confidence: **92/100** — every claim reproduced live via CDP computed styles/real input events in two independent sessions, direct SQLite read, and the documented pytest command; the single caveat is precisely located and corroborated by the vision reviewer.
