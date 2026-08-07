# REVIEW FUNC R5 — DeepSeek V4 Flash (review-func)

**Target:** live http://127.0.0.1:8000 (e2e-demo) · review-only server pid 8262 (`open_edit.cli serve --review-only --port 8000`)
**Date:** 2026-08-07 · **Method:** headless Chrome 151 via raw CDP (two independent browser sessions): real `Input.dispatchMouseEvent` mouse moves/press/release, live computed-style sampling at 50/200/450 ms, `elementFromPoint` occlusion checks, full Network/Log/Runtime capture; served css/js md5 == disk verified; documented pytest command (exit code captured directly)
**Scope:** R4 residual (renders-rail card hover dead after equal-specificity override) + full regression sweep

---

## 1. Renders-rail card hover — **PASS** (R4 residual fixed)

Coordinator's appended fix verified live in served `/style.css?v=20260728-crt-restyle` (md5 == disk) at lines 3028–3033:

```css
.renders-list .render-card:hover {
  background: color-mix(in oklab, white 7%, transparent);
  border-color: var(--oe-line-strong);
}
.renders-list .render-card:active { transform: scale(.99); }
```

| Criterion | Result | Evidence (real mouse, computed styles, session 1 @ 1600×1000) |
|---|---|---|
| Hover → backgroundColor CHANGES | **PASS** | Card 0 center (1470,118), real `Input.dispatchMouseEvent` moves: neutral `oklab(0.290253 0.00150616 -0.00518039 / 0.4)` → **t=50 ms mid-transition `oklab(0.412472 …/0.220774)`** → **t=200/450 ms settled `oklab(0.999994 0.0000455678 0.0000200868 / 0.07)`** = exactly `white 7%` overlay (alpha 0.07). `:hover` matches throughout. |
| Hover → border-color CHANGES | **PASS** | `rgba(255,255,255,0.14)` (`--oe-line`) → **`rgba(255,255,255,0.22)`** = `--oe-line-strong` (tokens resolved live from `:root`). |
| `:active` scale on mousedown | **PASS** | `mousePressed` → `active:true`, computed `transform: matrix(0.99, 0, 0, 0.99, 0, 0)`; `mouseReleased` → `transform:none`. |
| Revert on leave | **PASS** | Move to (5,5): `:hover=false`, bg back to base oklab(0.29…/0.4), border back to 0.14. |
| Applies to all cards | **PASS** | Real-mouse hover verified on cards 0, 5, 10, 11, 12 → all `oklab(0.999994…/0.07)` + border 0.22 (after scrolling rail so cards 11–12 clear the timeline occlusion, see caveat). |
| Independent session | **PASS** | Fresh tab (session 2, full page load + app exercise): hover chain `…#renders-list → .render-card` with `:hover=true`, same bg/border values; `:active` scale re-verified. |

**Root cause of R4's fail is gone:** the hover rule now has the *same* specificity as the appended base rule but appears *after* it in source order, so it wins while `:hover` is active; the base rule still wins when not hovering (verified: rest state unchanged).

---

## 2. Quick regression sweep — **PASS (all items)**

### pytest — PASS
`cd /home/amr/apps/mlt-pipeline && source .venv/bin/activate && python -m pytest tests/ -q --timeout=120 -p no:cacheprovider`
→ **EXIT=0** (captured directly, isolated re-run 68 s) · **1504 tests executed, 7 skipped, 0 FAILED, 0 ERROR** (1504 progress dots counted; skip set identical to R2/R3/R4: 3 × timeline-test fixture + 4 × strace fixtures). Note: pyproject `addopts = "-ra -q"` + command `-q` = quietest mode, which suppresses the final `N passed` line (verified on a subset run with `-q -q` vs `-v`); exit code + dot count are authoritative and match R4's 1504/7/0 exactly. Log: `testrun/logs/pytest_r5_reviewfunc.log`.

### Console / network — PASS
Fresh session, full load + exercise (play/skip/pause, theme ×2, notes modal, render-card click):
- Responses ≥400: **0** · `Runtime.exceptionThrown`: **0** · console error/warning entries: **0** · `Log.entryAdded` error/warning: **0**
- 8 `Network.loadingFailed`, all `net::ERR_ABORTED` + `canceled:true` — benign (video source switches + render-endpoint probe; same signature as R3/R4).

### Rail presentation unchanged — PASS
13 `.render-card`, 0 `.render-item`; card width **239px** (100% of rail), base bg `oklab(0.290253…/0.4)`, `.render-thumb` `display:flex`, `.render-sub` `display:flex` — identical to R4. Status colors unchanged: running `rgb(234,179,8)` (`--oe-warn`), failed `rgb(220,38,38)` (`--oe-danger`), succeeded `rgb(22,163,74)` (`--oe-success`).

### Notes timecodes + renders dates — PASS
Notes modal: 3 items with `[00:05.00]`, `[00:10.00]`, `[00:05.00]` — format intact, zero `1970` anywhere. All 13 `.render-sub` dates in **2026** (`8/7/2026, 1:04:15 AM` … `8/6/2026…`); **0** `1970` matches.

### Theme / transport — PASS
- Theme: `#btn-toggle-theme` dark→light→dark; `<html data-theme>` + `localStorage['open-edit-theme']` toggle in lockstep.
- Transport (real clicks): play `▶`→`❚❚`, `paused=false`, `currentTime` 1.12 s, `#tc-current` live `00:00.97`; skip fwd → `currentTime` 6.69 s, tc `00:06.55`, `#timeline-playhead` left `392.9px` (syncs).

### Served tree integrity — PASS
md5(served `/style.css?v=20260728-crt-restyle`) == md5(disk), md5(served `/app.js?v=20260729-preview-rev`) == md5(disk) — server serves the current working tree.

---

## Caveat (pre-existing, NOT introduced by the fix — carried from R3/R4)
`.timeline-panel` (z-index 2, y 733–913 at this viewport) overlaps the bottom ~180 px of the right panel, occluding the last two `.render-card`s at default scroll: `elementFromPoint(1470,756)` returns `#btn-add-note-playhead` (a timeline button), not the card. This is a layout-region overlap from the legacy `.layout { height: calc(100vh - var(--topbar-h)) }`, present since R3, untouched by the R5 CSS block. The rail scrolls (`aside.panel-right` scrollH 1040 > clientH 865); with the panel scrolled, cards 10–12 hover correctly (verified). Out of scope for the hover fix.

---

## Verdict

- **Item 1 (hover fix): PASS** — real-mouse hover changes computed background to the white-7% overlay (`oklab(0.999994 … / 0.07)`), border-color to `--oe-line-strong` (0.22), `:active` applies `scale(.99)` on mousedown; full revert on leave; reproduced in 2 independent browser sessions on multiple cards.
- **Item 2 (regression): PASS** — pytest EXIT=0 (1504 run / 7 skip / 0 fail / 0 error), console clean (0 ≥400, 0 exceptions, 0 errors), rail width/thumb/sub/status unchanged, notes `[00:05.00]`-style timecodes + 2026 render dates intact, theme + transport OK.
- **Overall: PASS 100%** · Confidence: **95/100** — every claim verified live with real CDP input events and computed styles across two independent sessions; only residual item is the pre-existing timeline-overlap caveat, which is unrelated to and unaffected by the fix under review.
