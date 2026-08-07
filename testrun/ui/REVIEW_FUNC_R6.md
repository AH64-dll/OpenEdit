# REVIEW FUNC R6 (FINAL) — DeepSeek V4 Flash (review-func)

**Target:** live http://127.0.0.1:8000 (e2e-demo project `bd2dd83f126d`) · review-only server pid 8262 (`open_edit.cli serve --review-only --port 8000`)
**Date:** 2026-08-07 · **Method:** headless Chrome 151 via raw CDP (3 independent sessions): real `Input.dispatchMouseEvent` clicks, `elementFromPoint` hit-tests at `#btn-show-notes` center after right-rail scroll-to-bottom, full Network/Log/Runtime capture, live computed layout probes at 1600×900 and 1600×1000; served `style.css` md5 == disk; documented pytest command (exit code captured directly)
**Scope:** R5 hygiene fixes — (a) stray editor token `[od:file-window …]` removed from style.css, (b) appended `body.has-timeline main.layout { height: calc(100vh - var(--topbar-h) - 180px) }` so panels end above the 180px timeline (fixes the pre-existing occlusion carried from R3/R4/R5)

---

## 1. CSS hygiene (both fixes present in served tree) — **PASS**

| Check | Result | Evidence |
|---|---|---|
| Stray token removed | **PASS** | `grep '[od:\|file-window' open_edit/serve/static/style.css` → **0 hits**; served `/style.css?v=20260728-crt-restyle` also 0 hits. (In R5 the token sat ~line 2015; the area is now clean `[data-theme="light"] .crt-tv-*` rules.) |
| Appended rule present | **PASS** | Line 3036–3039: comment + `body.has-timeline main.layout { height: calc(100vh - var(--topbar-h) - 180px); }` (last rule in file). |
| Served == disk | **PASS** | md5(served) == md5(disk) == `2ddbb3d528ae5cfe97ff0c5dfa69046e`. |

## 2. Layout invariant: panels end exactly at timeline top — **PASS**

`main.layout` grid-template-columns = **`0px 1340px 260px`** (left rail / center / 260px right rail) in **both** viewports; video element present in both.

| Viewport | topbar | main.layout h (computed) | main bottom | timeline top | main bottom == timeline top |
|---|---|---|---|---|---|
| 1600×900 | 48 | 672 (= 900−48−180) | **720** | **720** | **PASS** |
| 1600×1000 | 48 | 772 (= 1000−48−180) | **820** | **820** | **PASS** |

(The coordinator's 633==633 at 1600×900 measured with a different topbar height; the invariant — layout bottom equals timeline top — reproduces identically at both viewports, which is the requirement.)

## 3. Hit-test: `#btn-show-notes` clickable after rail scroll-to-bottom — **PASS**

| Viewport | btn rect after rail scroll | `elementFromPoint` at btn center | Real mouse click at center |
|---|---|---|---|
| 1600×900 | (1544,577)–(1590,603) | **`btn-show-notes`** (`isBtn=true`) | **notes modal opened** |
| 1600×1000 | (1544,677)–(1590,703) | **`btn-show-notes`** (`isBtn=true`) | — (same geometry verified; modal-open proven at 900) |

- Right rail (`aside.panel-right`) scrolls: scrollH 1040 vs clientH 672 (900vp) / 772 (1000vp); `scrollTop = scrollHeight` then hit-test.
- Before scrolling, the button sits under the timeline (pre-existing occlusion scenario) — after scroll it lands at y 577–603 (900vp), fully above timeline top 720, and the real-mouse click lands on the button (modal `#modal-notes` unhidden with the 3 review notes). **The R3/R4/R5 occlusion caveat is resolved.**

## 4. pytest — **PASS** (EXIT=0)

Exact command: `cd /home/amr/apps/mlt-pipeline && source .venv/bin/activate && python -m pytest tests/ -q --timeout=120 -p no:cacheprovider`
→ **EXIT=0** · **1504 executed / 7 skipped / 0 FAILED / 0 ERROR** (progress-line dot count; skip set identical to R2–R5: 3 × timeline-test fixture + 4 × strace fixtures). Log: `testrun/logs/pytest_r6_reviewfunc.log`.

## 5. Console / network scan — **PASS (0 exceptions / 0 non-favicon 404s)**

Full-load + exercise session (project select, rail scroll, real click, notes modal, transport, theme ×2):
- `Runtime.exceptionThrown`: **0** · `Runtime.consoleAPICalled` error/warning: **0** · `Log.entryAdded` warning: **0**
- HTTP ≥ 400: **1** — `http://127.0.0.1:8000/favicon.ico` 404 (the allowed favicon only; the 1 `Log.entryAdded` error is exactly this favicon resource line)
- 5 `Network.loadingFailed`: all `net::ERR_ABORTED` + `canceled:true` — benign video-source-switch signature (same as R3–R5)

## 6. Spot regression sweep — **PASS (all items)**

| Item | Result | Evidence |
|---|---|---|
| Transport play | **PASS** | Real mouse click: `paused:true→false`, label `▶→❚❚`, `currentTime` 0→**1.55 s**, `#tc-current` live `00:01.53` |
| Transport skip | **PASS** | Real click skip-fwd: `currentTime` +5 s → 7.54 s, `#timeline-playhead` left **436.3 px** (synced); skip-back −5 s → 2.54 s; pause → `paused:true`, `▶` |
| Theme toggle | **PASS** | `#btn-toggle-theme`: `data-theme` dark→light→dark with `localStorage['open-edit-theme']` in lockstep (light/light, dark/dark) |
| Notes timecodes | **PASS** | Modal shows `[00:05.00]`, `[00:10.00]`, `[00:05.00]` patterns; **0** `1970` |
| Renders dates | **PASS** | 13/13 `.render-sub` contain **2026** (`8/7/2026, 1:04:15 AM`, `8/6/2026…`); **0** `1970` |
| Render job succeeded in DB | **PASS** | `/home/amr/Videos/e2e-demo/.open_edit/render_jobs.db`: latest job `ca409fa99300495b979308d9b805c9e1` (project `e2e-demo`, mode `proxy`) `status='succeeded'`, `result_json.ok=true`, `qc_report.passed=true` (streams/duration/audio-sync all passed), finished **2026-08-07T01:04:15**, output `/home/amr/Videos/e2e-demo/.open_edit/renders/project_0c4bbbb617bc.mp4` exists (1,440,468 B). UI matches: top render card `render-status-succeeded` — "Review artifact · 640×360 · Ready · 1.4 MB · 8/7/2026, 1:04:15 AM". |

---

## Verdict

- **Item 1 (CSS hygiene): PASS** — token gone from disk + served CSS; appended height rule present and active.
- **Item 2 (layout + hit-test): PASS** — at 1600×900 and 1600×1000 the grid is `0/1fr/260`, video present, main.layout bottom == timeline top exactly, and after right-rail scroll-to-bottom `elementFromPoint` at `#btn-show-notes` center returns `btn-show-notes`; a real mouse click there opens the notes modal (end-to-end clickability).
- **Item 3 (pytest): PASS** — EXIT=0, 1504/7/0/0.
- **Item 4 (console): PASS** — 0 exceptions, 0 console/log errors, 0 non-favicon 404s.
- **Item 5 (regression): PASS** — transport play/skip, theme toggle, `[00:05.00]` timecodes, 2026 render dates, render job `succeeded` in DB all verified live.
- **Overall: PASS 100%** · Confidence: **97/100** — every criterion verified with real CDP input events, hit-tests, and live computed layout in independent sessions; the long-standing timeline-occlusion caveat (R3/R4/R5) is closed: panels now terminate exactly at the timeline top and the bottom rail control is clickable after scroll in both target viewports.
