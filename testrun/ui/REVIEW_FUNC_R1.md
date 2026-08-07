# Stage 3 Functional Review — REVIEW_FUNC_R1 (DeepSeek V4 Flash)

Date: 2026-08-06 · Reviewer: review-func · Scope: rubric categories **C** (functionality, live server) and **E** (quality gates)
Method: live server http://127.0.0.1:8000 (review-only) + http://127.0.0.1:8001 (agent mode) · headless Chrome 151 via CDP (Runtime.evaluate, real mouse gestures, Network/Log capture) · curl for API/Range checks · pytest.

Project under test: **e2e-demo** (id `bd2dd83f126d`, 9 assets, 57 ops, 28.59s). Scratch project `rf-func-test-656771` created for destructive tests (upload). A second clean Chrome profile was used to re-verify preview streaming after one test profile got corrupted by a JS-dialog deadlock (artifact, not app bug).

---

## C — Functionality (evidence per feature)

| # | Feature | Verdict | Evidence |
|---|---|---|---|
| C1 | Project select | **PASS** | `#project-select` lists 4 projects; e2e-demo auto-selected from localStorage; switching re-renders assets(9)/edits(50)/renders(12)/timeline; conn stays Connected. |
| C2 | Project create | **PASS** | `#btn-new-project` → `#modal-new-project` opens, name entry, `#btn-create-project` → modal closes, toast `Created project "rf-func-test-656771"`, new project appears in select and is auto-selected. |
| C3 | Project refresh | **PASS** | `#btn-refresh-project` → lists reload (9/50/12), selection preserved, toast/conn OK. |
| C4 | Assets list | **PASS** | 9 asset cards with filename, duration, 1920×1080, codec, audio; per-card "Add" (add-to-timeline) buttons. |
| C5 | Upload dropzone | **PASS** | `#dropzone` visible in assets tab; real upload via `#file-input` (DOM.setFileInputFiles) of `rf_upload_test.mp4` → toast `Ingested 1 file`, `#upload-progress` shown, asset card with `0:02 · 320×180 · h264 · audio`. |
| C6 | Asset preview modal | **PASS** | Click asset card → `#modal-asset-preview` opens, title=`take1_intro.mp4`, video src = asset file URL, readyState 4, duration 9.72s (played). |
| C7 | Range streaming (206) | **PASS** | curl: asset `GET .../assets/<hash>/file` Range 0-1023 → **206** `bytes 0-1023/7869701`; render file Range 0-1023 → **206** `bytes 0-1023/1440468`; full GET → 200 video/mp4. Browser video elements reached HAVE_ENOUGH_DATA and played both. |
| C8 | Edit graph list | **PASS** | 50 `.edit-card` entries, kind + status badges (`applied`/`reverted`), newest-first. |
| C9 | Edit undo | **PASS** | Select card → `#btn-edit-undo` → toast `Undid replace_clip_source`; card + detail status flip to `reverted`; button disables for reverted; API confirms (`PATCH /ops/{id}/status` → status reverted, graph_revision bump). Restored to applied afterwards. |
| C10 | Edit delete | **PASS** | `#btn-edit-delete` (confirm stubbed) → toast `Reverted replace_clip_source`; edit stays in history as `reverted` (still 50 cards), detail hides. Restored via API. |
| C11 | Edit detail | **PASS** | `#edit-detail-kind/status/author/id/payload` populated from selected edit; visible when edits tab active; timeline marker click also opens it. |
| C12 | Renders list | **PASS** | 12 `.render-item`s with mode (`Review artifact · 640×360` / `Final export · 1080p`), status (Ready/Rendering…/Failed: …), size, timestamp; click succeeded render → preview loads that file (src + badge update). |
| C13 | Render proxy/final + polling | **PASS** (mechanics) — see D2 | `#btn-render-proxy` → busy label `Rendering…`, disabled; POST /render 202; new entry appears `running`; **auto-polls** (no manual refresh) → `failed`; buttons re-enable; full error surfaced in toast + list. `#btn-render-final` same wiring. **But the actual render job on e2e-demo fails (D2).** |
| C14 | Notes add-at-playhead | **PASS** (flow) — see D1 | Skip to 5s → `#btn-add-note-playhead` → toast `Note added at playhead`; pending count 1→3; `.timeline-note-marker` count 3; API notes `timestamp: 5.0/10.0/5.0`. |
| C15 | Notes list | **PASS** (flow) — see D1 | `#btn-show-notes` → `#modal-notes` lists `.note-item`s with text/source/status. **Timestamp displays as `1/1/1970, 2:00:00 AM` (bug D1).** |
| C16 | Chat widgets review-gated | **PASS** | `#chat-log/#chat-status/#verify-chip/#cost-badge/#chat-input/#btn-send/#btn-stop/#btn-topbar-stop` present in DOM; in review mode all `display:none` (agent-only), input + send disabled, conn title `Review mode (no chat WebSocket)`; in agent mode (8001) chat enabled (input enabled). |
| C17 | Prompt chips | **PASS** | 4 `.prompt-chip`s with `data-prompt` attrs (✂️ Cut silences / 🏷️ Add lower-third / 🔊 Normalize audio / 🎬 Render final video). Static (no click handler — not required by contract). |
| C18 | WS reconnect | **PASS** (agent mode, live) | 8001: `ws://127.0.0.1:8001/api/chat/<pid>` handshake 101 + `ready` frame; forced socket close → `#conn-status` flips `connected` → `disconnected` → auto-reconnect → `connected` with new OPEN socket (~2.5 s). Backoff code in ws.js (max 8 attempts, 10 s cap; online/focus handlers). Review mode: no WS by design; conn shows Connected (review indicator). |
| C19 | Preview streams render + asset | **PASS** | Render: readyState 4, duration 28.77, real playback (currentTime 1.90 s, tc ticking); asset: readyState 4, 9.72 s. 206 verified (C7). Verified in a fresh Chrome profile after one profile was corrupted by a dialog deadlock during testing. |
| C20 | NEW transport (skip-back/play/skip-fwd + tc) | **PASS** | `#btn-skip-fwd` → tc `00:00.00`→`00:05.00`, playhead 300 px, video seeks to 5 s; `#btn-play` (real gesture; synthetic clicks are blocked by autoplay policy — expected browser behavior) → video plays, button `▶`→`❚❚`, tc ticks in real time; `#btn-skip-back` → tc 00:00.00, video 0 s. `#tc-current` + `.transport-total` (`/ 00:28.59`) correct. |
| C21 | Timeline ruler/scrub | **PASS** | `#timeline-ruler-col[data-scrub-bound="1"]`; 6 ticks (0s–25s); click ruler at 30% → playhead 300→514 px, tc `00:08.57`, video seeks to 8.57 s. |
| C22 | Timeline zoom/fit | **PASS** | zoom-in → ticks 0/2/4/…/14, playhead scales (300→1156 px); zoom-out ×4 → ticks 0/10/20; fit → ticks 0/5/…/25 across full 1486 px ruler. |
| C23 | Timeline markers | **PASS** | 27 `.timeline-edit-marker`s with titles (`add_clip @ 00:00.00 …`); click marker → switches to edits tab + opens matching edit detail (kind `add_clip`, id `19c203c1…`). |
| C24 | Timecode copy | **PASS** | `#btn-copy-timecode` → toast shows timecode (`[00:07.50]`). |
| C25 | cmd-K | **PASS** | Ctrl+K and `#btn-cmd-k` open palette; Esc closes; typing filters (`proj` → Create New Project / Refresh Projects List); clicking item executes (opened new-project modal). |
| C26 | Theme toggle | **PASS** | `data-theme` dark→light→dark; icon swaps moon SVG → sun SVG (circle+rays). |
| C27 | Panel toggles | **PASS** | `#btn-toggle-left-panel`/`#btn-toggle-right-panel` flip `panel-left-collapsed`/`panel-right-collapsed`, panels display flex 240 px when open. Review-mode default: left collapsed (body class on boot). |
| C28 | Settings modal | **PASS** (agent mode) — see D3 | Opens, Esc closes, 4 key inputs + `#btn-save-settings-keys`; agent mode (8001) populates runtimes (Anthropic ✓ Installed, OpenAI ✓ Installed, Pi Agent Engine …) and key placeholders. Review mode: gated endpoints 404 by design → perpetual `Scanning PATH & GUI directories…` (D3). |
| C29 | Toast | **PASS** | Appears with content and hides after timeout (created project, undid, note added, timecode, render error). |
| C30 | Conn status | **PASS** | Review: `Connected` (title: review mode, no WS). Agent: connected/disconnected/reconnecting states live. |
| C31 | LLM selects | **PASS** | `#llm-provider-select`/`#llm-model-select` present; disabled in review mode. |

## E — Quality gates

| Item | Verdict | Evidence |
|---|---|---|
| pytest | **PASS** | `python -m pytest tests/ -q --timeout=120 -p no:cacheprovider` → **exit 0**, 1504 collected, **0 failures**, 7 skipped (env: timeline-test fixture ×3, strace fixtures ×4). |
| Browser console | **FAIL (minor)** — see D3 | 0 JS exceptions on both tabs (`Runtime.exceptionThrown` none). Only favicon 404s on the clean flow. Opening settings in review mode adds 2×404 (`/api/runtimes`, `/api/settings/keys`) — by-design gating, but rubric allows only favicon 404. |
| Contract IDs | **PASS** | All 80 contract IDs present in index.html (incl. `timeline-empty-msg` in static HTML, removed on render), plus NEW ids `btn-skip-back/btn-play/btn-skip-fwd/tc-current`; 30 `data-od-id` attrs. |
| JS-emitted classes | **FAIL (minor)** — see D4 | Contract lists `.render-card`; app emits `.render-item render-status-*` (no test depends on it; verified `grep tests/` empty). `--green`/`--text-dim`/`--border` all defined in style.css. |

## Defects found (direct evidence)

- **D1 — Epoch timestamps in notes & renders lists.** `fmtTime(n.timestamp)` in `js/dom.js` calls `new Date(iso)` with a *seconds* value (note `timestamp: 5.0`, render `timestamp: 1785989611`): notes show `[1/1/1970, 2:00:00 AM]`, renders show `1/21/1970, 6:07:02 PM`. Fix: `new Date(sec*1000)` (or pass ISO). Re-verify: open notes modal + renders list → 2026 dates.
- **D2 — Live render on e2e-demo fails (backend/fixture).** Proxy render → `OverlayRenderError: template_not_found: overlays/caption_sequence.html` (raised inside `render/hyperframes.py` fingerprint via `html_overlay.generate_composition_html`). Template absent from project workdir and builtins (only `lower_third.html`, `caption_card.html` exist). Two pre-existing failed jobs in list (audio-track overlap on a1; hyperframes exit 1) confirm fixture drift predates this session. UI mechanics (buttons/polling/error surfacing) all PASS. Fix: provide the overlay template (project or builtin) or repair the demo timeline; re-verify: render proxy on e2e-demo → `succeeded`, preview auto-loads new render.
- **D3 — Review-mode settings modal: perpetual "Scanning…" + 2 console 404s.** `/api/runtimes` + `/api/settings/keys` return 404 `not available in review-only mode` (by design), but `openSettingsModal()` fetches them anyway; `rRes.runtimes` undefined → placeholder never resolves. Fix: skip the fetches in review mode (or have server return 200 gated payload) and show a review-mode notice. Re-verify: open settings in review mode → no 404s, modal shows notice.
- **D4 — Contract class drift.** `.render-card` (CONTRACT.md) vs emitted `.render-item` (renderRendersList). Fix: rename emitted class to `render-card` (or amend contract in lockstep). Re-verify: renders list DOM contains `render-card`.

## Residue from testing (needs cleanup)
- Scratch project `rf-func-test-656771` (id `cfce07ecf208`, 1 uploaded asset `rf_upload_test.mp4`) — no delete-project API found.
- e2e-demo: 3 pending notes ("review-func test note at playhead") + 1 failed render job entry (id `24dd5f64008e4dd9bbf982d538400704`).
- All e2e-demo edit ops restored to `applied` (0 non-applied ops).

## Verdict
Category C: **PASS with defects** (all 31 inventory features exercised against the live server; 2 defects: D1 visible timestamp bug, D2 render pipeline failure on the demo fixture — UI mechanics unaffected).
Category E: **PASS for pytest** (exit 0, 1504 collected, 7 env skips, 0 failures); **FAIL (minor) for console** (D3 adds 2 non-favicon 404s); **FAIL (minor) for class contract** (D4).

**Overall: NOT PASS** — confidence **90/100**. All functionality is present and working, but D1 (epoch timestamps visible in notes/renders lists) and D3 (console 404s) block a 100% verdict. D2 is a fixture/backend issue that must be fixed before a render can complete end-to-end on e2e-demo. Fix list: D1 → D2 → D3 → D4, then re-verify per item and re-run pytest + console scan.
