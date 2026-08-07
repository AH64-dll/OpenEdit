# Stage 3 Functional Review — REVIEW_FUNC_R2 (DeepSeek V4 Flash)

Date: 2026-08-07 · Reviewer: review-func (round 2) · Scope: re-verify D1–D4 fixes from Round 1 against live server
Method: live server http://127.0.0.1:8000 (review-only, pid 8262 `open_edit.cli serve --review-only --port 8000`) · headless Chrome 151 via raw CDP (Network/Log/Runtime capture, real DOM queries) · node unit-check of `fmtTime` · SQLite direct read of render_jobs.db · pytest (documented command).

## Verdict summary

| Defect | Verdict | One-line evidence |
|---|---|---|
| D1 (epoch timestamps) | **FAIL — partial fix** | Renders list fixed (2026 dates live), **notes modal still shows 1/1/1970** (note `timestamp` is playhead seconds, not epoch; server payload unchanged) |
| D2 (render fails on e2e-demo) | **PASS** | Latest render_jobs.db proxy job `ca409fa9…` status=succeeded, ok:true, QC passed:true; fresh mp4 1.4 MB mtime 2026-08-07 01:04:15; overlays/ templates present; preview auto-loaded the new render |
| D3 (review-mode settings 404s) | **PASS** | Settings modal shows review-mode notice; zero `/api/runtimes` or `/api/settings/keys` requests in isolated CDP network capture; zero 404s |
| D4 (class drift) | **PASS** | app.js emits `render-card`; live DOM has 13 `.render-card`, 0 `.render-item` |
| pytest | **PASS** | exit 0, 1504 collected, 0 failed/error, 7 skipped (1497 passed) |
| Console scan | **PASS** | Full-load CDP capture: zero responses ≥400, zero JS exceptions (only 4 benign verbose `[DOM] Password field is not contained in a form` info logs) |

**Overall: NOT PASS** (D1 notes-modal half still broken) — confidence 93/100.

---

## D1 — Epoch timestamps in notes & renders lists → **FAIL (partial)**

### What was fixed
`open_edit/serve/static/js/dom.js` `fmtTime` (git diff confirmed):
```js
if (typeof value === 'number' || /^\d{9,10}(\.\d+)?$/.test(String(value).trim())) {
  value = Number(value) * 1000;
}
```

### Unit check (node, extracted function)
```
1786053855.6655638 -> 8/7/2026, 1:04:15 AM   (render job updated_at — epoch seconds)  OK
1785989611        -> 8/6/2026, 7:13:31 AM   (epoch seconds)                          OK
"1786053855"      -> 8/7/2026, 1:04:15 AM   (string epoch)                           OK
"5.0"             -> 5.0                    (passthrough, not 9-10 digits)          OK
5                 -> 1/1/1970, 2:00:05 AM   (playhead seconds treated as epoch)      WRONG
10                -> 1/1/1970, 2:00:10 AM                                            WRONG
```

### Live renders list (e2e-demo selected, two independent Chrome sessions)
Top card: `project_0c4bbbb617bc.mp4 · Review artifact · 640×360 · Ready · 1.4 MB · **8/7/2026, 1:04:15 AM**` — real 2026 date. Older jobs also 2026 (`8/6/2026, 7:11:47 AM`, etc.). **Renders list: FIXED.**

### Live notes modal (`#btn-show-notes` → `#modal-notes`), both sessions
```
[1/1/1970, 2:00:05 AM] · typed · pending — review-func test note at playhead
[1/1/1970, 2:00:10 AM] · typed · pending — review-func test note at playhead
[1/1/1970, 2:00:05 AM] · typed · pending — review-func test note at playhead
```
**Still 1970. NOT fixed.**

### Root cause of the residual failure
The notes API (`GET /api/projects/{id}` → `notes[]`) sends `timestamp` = the note's **timeline anchor in seconds** (5.0 / 10.0 — playhead position), not an epoch:
```
$ curl /api/projects/bd2dd83f126d  →  notes: [{timestamp: 5.0, ...}, {timestamp: 10.0, ...}, {timestamp: 5.0, ...}]
```
- `open_edit/serve/projects.py::_note_to_info` maps `ReviewNoteInfo.timestamp = anchor t_start` (seconds).
- `open_edit/serve/projects.py::ReviewNoteInfo` has **no created_at field** (server payload unchanged by the fix).
- `static/js/state.js::normalizeNotes` maps `timestamp: n.timestamp || 0` unchanged.
- New `fmtTime` multiplies any number by 1000 → `new Date(5000)` → 1970-01-01.

So the fix only addresses the renders path (epoch `job.updated_at`). To fix notes, either the server must expose a real creation timestamp (epoch/ISO) in the notes payload and the UI must use it, or the UI must render playhead anchors as timecodes (e.g. `[00:05.0]`), not dates. The R2 verification criterion ("notes modal timestamps must show real 2026 dates, not 1970") is **not met**.

---

## D2 — Render fails on e2e-demo → **PASS**

### render_jobs.db (direct SQLite read, `/home/amr/Videos/e2e-demo/.open_edit/render_jobs.db`, ORDER BY rowid DESC)
Latest row (project `e2e-demo`, mode `proxy`):
- job_id `ca409fa99300495b979308d9b805c9e1`
- status **`succeeded`**
- created_at 1786053829.747 (2026-08-07 01:03:49) · updated_at 1786053855.666 (2026-08-07 01:04:15)
- output_path `/home/amr/Videos/e2e-demo/.open_edit/renders/project_0c4bbbb617bc.mp4`
- result_json: `"ok": true`, `"elapsed_sec": 11.17`, qc_report `"passed": true` (render_completed ✓, proxy_render ✓, streams ✓, duration 28.77 vs 28.59 diff 0.18s ✓, audio_sync diff 0.001s ✓)
- The immediately preceding e2e-demo row (job `f325c6b1…`, 2026-08-07 00:49) is the **old failure**: `OverlayRenderError: template_not_found: overlays/caption_sequence.html` — superseded by the success.

### Renders dir
`/home/amr/Videos/e2e-demo/.open_edit/renders/project_0c4bbbb617bc.mp4` — exists, **1,440,468 bytes**, mtime **2026-08-07 01:04:15** (matches job updated_at → fresh).

### Overlay templates
`/home/amr/Videos/e2e-demo/overlays/` contains `caption_sequence.html` + `brand_lower_third.html` (the previously missing template is present).

### Live UI
`GET /api/projects/bd2dd83f126d/renders` → first entry `ca409fa9…` status=succeeded, timestamp 1786053855.7. Browser: renders list shows the job as `Ready · 1.4 MB · 8/7/2026, 1:04:15 AM`, and `#preview-player` **auto-loaded** `…/renders/ca409fa99300495b979308d9b805c9e1/file` (readyState 4 = HAVE_ENOUGH_DATA; network log shows the file requests).

---

## D3 — Review-mode settings 404s → **PASS**

### Source
`app.js::openSettingsModal` (git diff confirmed): after `showModal('modal-settings')`, review-only early-return BEFORE any fetch:
```js
if (document.body.classList.contains('review-only-mode')) {
  if (rList) { rList.innerHTML = '';
    rList.appendChild(el('div', { class: 'note-item muted small' }, [
      'Review mode: agent runtimes & API keys are managed by the agent harness. ' +
      'Start the server without --review-only to configure them here.',
    ])); }
  return;
}
```

### Live (review-only server on :8000; body class `review-only-mode`; two sessions)
1. Click `#btn-settings` → `#modal-settings` opens.
2. `#settings-runtimes-list` innerHTML = `<div class="note-item muted small">Review mode: agent runtimes & API keys are managed by the agent harness. Start the server without --review-only to configure them here.</div>`
3. Isolated CDP network capture around the click (events cleared immediately before): **zero requests fired** — no `/api/runtimes`, no `/api/settings/keys`. No response ≥400. No console errors/exceptions.

---

## D4 — Contract class drift → **PASS**

### Source
`app.js::renderRendersList` (git diff confirmed): `class: \`render-card render-status-${status}\`` (was `render-item`).

### Live
`#renders-list` DOM (e2e-demo): **13 `.render-card`** elements, **0 `.render-item`**; first child class = `render-card render-status-succeeded`.

---

## Quality gates

### pytest — PASS
Command (documented): `cd /home/amr/apps/mlt-pipeline && source .venv/bin/activate && python -m pytest tests/ -q --timeout=120 -p no:cacheprovider`
Result: **EXIT=0**, 1504 collected, progress stream has 0 F / 0 E / 7 s, 7 SKIPPED summary lines, 0 FAILED lines → **1497 passed, 7 skipped, 0 failed**. Log: `testrun/logs/pytest_r2_reviewfunc.log`.

### Console scan — PASS
Full page-load CDP capture (fresh tab, Network.enable before navigation): **zero responses ≥400** (headless Chrome did not request favicon at all; in any case no non-favicon 404s), zero `Runtime.exceptionThrown`, zero error-level logs. Only 4 benign verbose `[DOM] Password field is not contained in a form` info messages (key inputs outside a `<form>`). Settings segment: zero 404s. Condition "only favicon 404 allowed" satisfied.

---

## Verdict
- D2, D3, D4: **PASS** (all fixes verified live with direct evidence).
- D1: **FAIL (partial)** — renders-list timestamps now show 2026 dates and `fmtTime` correctly converts epoch seconds (unit-verified), but the notes modal still renders `1/1/1970` because note `timestamp` is a playhead anchor (5.0/10.0 s) and the server payload still has no real creation timestamp. The D1 re-verify criterion for the notes modal is not met.
- pytest: PASS (exit 0). Console: PASS (no non-favicon 404s).
- Confidence: **93/100** (all evidence direct and reproduced in two independent browser sessions; single residual D1-notes issue is precisely characterized with root cause).
