# Phase 4 Design — Audit Log & Fixes

**Date:** 2026-07-20
**Source:** `phase4-design-revised.md` (Claude + Super Z merged v2)
**Reviewer:** Phase 4 audit
**Outcome:** 3 critical, 4 high, 8 medium, 3 low issues found. All fixed inline in this audit. New sections added. Sequencing re-ordered. 1 new task added (T8 IR extension, promoted from inline §3.8). 1 new housekeeping task added (T9 notes archive).

---

## Critical Issues (3)

### C1 — Task sequencing: T1 has unresolved dependencies

**Original (§11 step 6):** "T1 tool repointing + 5 new tools + `creativity_level`"

**Problem:** T1 includes 5 new tools:
- `pyagent_run_python` — depends on `sandbox_bridge.run_free_form()` (Phase 3 ✓)
- `pyagent_get_style_profile` — depends on `style/retrieve.py` (T2 — NOT YET BUILT)
- `pyagent_set_pinned_value` — depends on `style/aggregate.py` (T2 — NOT YET BUILT)
- `pyagent_get_pending_notes` — depends on `NotesStore.list_pending()` (T6 — NOT YET BUILT)
- `pyagent_add_marker` — depends on `NotesStore.append()` (T6 — NOT YET BUILT)

T1 also edits `system_prompt.md` to add `prior_state` block (built by `style_inject.py` from T2) and `pending_notes_summary` (from T6).

**Fix:** T1 is now the LAST Phase 4 task, after T6 and T2. Updated §11 sequencing.

---

### C2 — §3.8 IR extension is treated as inline; should be a real task

**Original (§3.8):** "IR op metadata extension (small)" — presented as a paragraph noting the change to `Operation.originating_note_id`.

**Problem:** This is a foundational change that T7 (commit_feedback) cannot function without. The `commit_feedback` handler must stamp `originating_note_id` on every op produced during the run; otherwise the audit trail breaks. Treating it as a small inline change hides the work.

**Fix:** Promoted to its own task **T8 — IR op metadata extension**. Includes:
- Add `originating_note_id: str | None = None` to `Operation` (`open_edit/open_edit/ir/types.py`).
- Stored in `payload` JSON (the `edits.payload TEXT NOT NULL` column already exists — no SQL migration needed).
- `IR` API methods (`open_edit/open_edit/ir/api.py:24-180`) accept optional `originating_note_id` parameter.
- `sandbox_bridge.run_free_form()` accepts optional `originating_note_id` parameter; if set, stamped on every op produced.
- Existing fixtures continue to work (default `None`).
- New tests: `test_originating_note_id.py` — verify stamping, default None, propagation through `apply.py` and `EditGraphStore`.

**Note on schema:** The current schema.sql comment says "Schema is additive-only; no migrations needed because the file is a snapshot, not a long-lived schema-bearing database." This is misleading — if the `edits` table already exists in a user's project, the comment is true for that table (no schema change), but for new fields we use the `payload` JSON column, not a new SQL column. Updated wording in the design.

---

### C3 — Region mark rejection logic is wrong

**Original (§8 row 8):** "Click-and-drag region mark on a frame without time | Client-side validation: reject region marks before `t_start=0` or after video duration."

**Problem:** `t_start=0` is valid (the very first frame of a video). The wording "before `t_start=0`" would reject valid marks.

**Fix:** Changed to "reject region marks where `t_start < 0` or `t_end > video_duration`."

---

## High Issues (4)

### H1 — Race condition in `commit_feedback`

**Original (§3.7):** Backend queries `NotesStore` for `status=pending` notes on receipt of `commit_feedback`, then assembles `pending_feedback` block and triggers agent run.

**Problem:** Between the user clicking "Send to Claude" and the backend's query, a new note could be added. That note would not be in the `pending_feedback` block, so the agent would not act on it. The user would expect "I added a note just before clicking, the agent should see it." Or, conversely, a note could be added during the agent run; the agent would not see it but it would still be `status=pending` afterwards.

**Fix:**
- Add a `commit_token` (UUID) field to the `commit_feedback` message. Backend begins a transaction: mark all `status=pending` notes with `commit_token=<token>`, then queries those notes, then triggers agent run.
- Any new note added after the transaction begins is not in the block — the user must click "Send to Claude" again to include it. (UI shows a "your last note arrived after you clicked Send — would you like to commit it too?" toast.)
- After agent run completes: all notes with `commit_token=<token>` transition to `status=processed`. Notes added during the run with `commit_token=NULL` remain `status=pending`.
- New test: `test_commit_feedback_race.py` — simulates a note added mid-run, verifies it's not marked processed.

---

### H2 — Version switcher during active render

**Original (§3.4 + §3.5):** Version switcher dropdown in the preview player UI; user selects v1/v2/v3.

**Problem:** If the user switches to v1 while v2 is rendering, what happens? The render of v2 still completes (it has to), and the user might switch back. The list of versions is in flux.

**Fix:**
- Each `RenderSnapshot` has a `status: Literal["rendering", "ready", "failed"]` field.
- During render, the entry is `status=rendering`; the switcher entry is disabled (greyed out with a spinner).
- After render completes, the entry transitions to `status=ready`; the switcher enables.
- If the user is currently viewing the rendering version and switches to a different ready version, the rendering continues in the background; the UI shows the new selection immediately.
- If the render fails, the entry is `status=failed`; the switcher shows a "render failed" badge and disables the entry.
- `RenderSnapshotStore` enforces a max-versions cap (default 20, evict oldest `status=ready` entry by `created_at`); entries with `status=rendering` or `status=failed` are not evicted.
- New test: `test_version_switcher_during_render.py` — verifies state transitions, UI behavior, eviction policy.

---

### H3 — `pyagent_get_pending_notes` token budget

**Original (§3.1):** "Full-detail pull of pending review notes for the current project; agent calls this on demand for detail."

**Problem:** With 50 pending notes, each `ReviewNote` object is ~100 tokens. Total: 5000 tokens for one tool call. That's a lot.

**Fix:**
- Add `summary_only: bool = False` parameter to `pyagent_get_pending_notes`. Default: full detail.
- When `summary_only=True`: returns just `(note_id, anchor_summary, text_preview[:80])` per note. ~30 tokens per note. 50 notes = 1500 tokens.
- When `summary_only=False` (default): returns the first 10 in full detail plus a count of the rest. 10 notes × 100 tokens = 1000 tokens.
- New test: `test_get_pending_notes_summary.py` — verifies token budgets.

---

### H4 — WS broadcast scope for `note_list`

**Original (§3.6):** "`note_list` (server→client, broadcast on any change): full list of notes for the current project."

**Problem:** What if multiple sessions/projects are open simultaneously (multi-project v1.1, but the WS layer should be forward-compatible)? A broadcast to all sessions is too wide. Project-scoped broadcast requires `project_id` in the message.

**Fix:**
- All note-related WS messages include `project_id` field.
- Backend maintains a `project_id → set[websocket_conn]` map; broadcasts go only to the project's connections.
- Current chat UI has a single project per session, so the backend can fall back to session-scoped broadcast when `project_id` matches the active session's project.
- New test: `test_note_ws_broadcast_scope.py` — verifies project-scoped delivery.

---

## Medium Issues (8)

### M1 — `RenderSnapshotStore` needs a max-versions cap

**Original (§3.4):** New `RenderSnapshotStore`, but no eviction policy.

**Problem:** Each render = ~50MB MP4. Without a cap, an active project accumulates GBs of stale MP4s.

**Fix:** Default max 20 versions. Evict oldest `status=ready` entry by `created_at` on each new render. `status=rendering` and `status=failed` are not evicted. Configurable via `~/.open-edit/config.json`:
```json
{ "render_snapshot_max_versions": 20 }
```
- New test: `test_render_snapshot_cap.py` — verifies eviction, ordering, status protection.

---

### M2 — `creativity_level` storage location not specified

**Original (§3.1):** "Set on the agent run config, surfaced in the system prompt as a directive."

**Problem:** Where is it persisted? Per-message? Per-session? Per-project? The design doesn't say.

**Fix:**
- **Per-project default:** stored in `~/.open-edit/projects/<id>/project_meta.json` as `{"creativity_level": "balanced"}`. Read on agent run start.
- **Per-message override:** a dropdown in the chat composer (left of the "Send" button) labeled "Creativity: conservative / balanced / full". Set in the WS `prompt` message: `{type: "prompt", text: "...", creativity_level: "full"}`. Overrides the per-project default for that turn.
- **Default:** `balanced` if neither is set.
- New test: `test_creativity_level.py` — verifies per-project default, per-message override, fallback.

---

### M3 — Notes DB archive trigger not specified

**Original (§8 row 14):** "Notes DB grows large (>1000 notes) | Archive processed notes older than 30 days to `notes.db.archive`. Pending notes never archived."

**Problem:** When does the archive run? On every note add (cheap in SQL, but noise)? Periodic (cron-style, needs a scheduler)? On commit_feedback (cleanest, ties to a known event)?

**Fix:** Archive runs on `commit_feedback` completion, after marking notes processed. The `commit_feedback` handler: (1) marks all `commit_token=<token>` notes as `status=processed`, (2) checks if `count(*) where status=processed and created_at < now - 30d > 0`, (3) if so, moves them to `notes_archive` table (same schema). The check is O(1) with an index.
- New task **T9 — Notes DB archival housekeeping.** Small (~0.5 day), runs on commit_feedback completion.

---

### M4 — `prior_state` token budget not explicit

**Original (§3.2):** "≤250 token injection" — refers to the style slice only.

**Problem:** `prior_state` now has multiple components: style slice, pending notes summary, creativity directive, latest 3 ops. Total budget not specified.

**Fix:** Total `prior_state` budget: **≤600 tokens**, broken down as:
- Style slice: ≤250 tokens (per spec §8.8)
- Pending notes summary: ≤150 tokens (count + 3 most recent)
- Creativity directive: ≤50 tokens (1-2 sentences)
- Latest 3 ops: ≤150 tokens (50 tokens each, summarized)
- **Hard cap: 600 tokens.** If exceeded, trim in order: notes summary → style slice examples → latest ops. Never trim creativity directive or core numeric defaults.
- New test: `test_prior_state_budget.py` — verifies all four components fit, trim order is correct.

---

### M5 — `RenderSnapshotStore` vs `RenderCache` confusion

**Original (§3.4):** `RenderSnapshotStore` is a new storage layer for version snapshots.

**Problem:** Phase 2 already has a `RenderCache` (`open_edit/open_edit/render/cache.py`). What's the difference?

**Fix (added to design):**
- `RenderCache` (Phase 2): keyed by `edit_graph_hash` (SHA-256 of canonical JSON of edit graph), used for cache hits (don't re-render if nothing changed). Auto-pruned by age (`DEFAULT_MAX_AGE_SEC = 3600`). User never sees it.
- `RenderSnapshotStore` (Phase 4): keyed by `version_id` (UUID), used for user-facing version switcher. Auto-pruned by max-versions cap (default 20, evict oldest `status=ready`). User sees it in the preview player.
- They coexist. After Phase 2's `RenderCache` returns a cached MP4, Phase 4's `RenderSnapshotStore` records a new snapshot with the current `version_id` (only if the user has "save version" enabled, default on).

---

### M6 — Note placement in chat UI not specified

**Original (§3.5):** "Notes sidebar (below) shows all notes chronologically."

**Problem:** "Below" what? The current 3-column layout is sessions / chat+composer / project state. A 4th column is a major UI change. A modal is a different UX.

**Fix:** Notes live in the project state column (right sidebar). The project state panel currently shows: project name, total duration, clip count. New addition: notes section with count badge + last 3 notes (truncated). Click "View all" → opens a modal overlay with the full notes list. This integrates without a 4th column.
- New task: Add notes section to `pyagent-kdenlive-guide/phase4_chat_ui/static/app.js` and `index.html`.
- New test: `test_notes_sidebar_render.py` — verifies project state panel includes notes section.

---

### M7 — STT requires HTTPS in most browsers

**Original (§3.5):** "Speech-to-text input via Web Speech API."

**Problem:** Web Speech API requires a secure context (HTTPS or localhost) in Chrome, Edge, Safari. The chat UI is served from `localhost` in dev — works. In production behind a reverse proxy, HTTPS is required.

**Fix:** Document the requirement in `phase4_chat_ui/README.md` (new file or add to existing). Production deployment must use HTTPS or a localhost-only reverse proxy. The STT button is hidden if the page is not in a secure context (using `window.isSecureContext`).
- New test: `test_stt_secure_context.py` — verifies button visibility based on `isSecureContext`.

---

### M8 — Edit history list performance at >500 ops

**Original (§8 row 13):** "Long-form op count > 500 | Edit history list shows pagination (50 ops/page)."

**Problem:** The pagination is mentioned in error handling but not in T4's design. T4 is the task that builds the edit history list.

**Fix:** T4's edit history list includes pagination from the start:
- Default 50 ops per page.
- Page controls: prev / next / page number.
- For v1.1: virtual scrolling (only render visible rows).
- For v1: simple pagination is fine.
- New test: `test_edit_history_pagination.py` — verifies page size, controls, edge cases (0 ops, 50 ops exactly).

---

## Low Issues (3)

### L1 — `§3.8` schema wording is misleading

**Original:** "This is a small additive change. Existing fixtures continue to work (`originating_note_id` defaults to `None`)."

**Problem:** Reads as if it's purely additive. The Pydantic model change is additive (default `None` works). The actual data goes into the `payload` JSON column (already exists). No SQL column change. But the wording doesn't make that clear.

**Fix:** Updated to: "Add `originating_note_id: str | None = None` to `Operation` Pydantic model. The new field is serialized into the existing `edits.payload TEXT NOT NULL` JSON column (no SQL schema change). `EditGraphStore` reads/writes the same column. `IR` API methods and `sandbox_bridge.run_free_form()` accept an optional `originating_note_id` parameter; if set, it's stamped on every op produced by that call."

---

### L2 — `§4.3` templated motion graphics — where do templates live?

**Original (§4.3):** "Templated per beat type. A library of parameterized templates, one per narrative beat type."

**Problem:** Where do the templates live? A new dir? What's their format? Who maintains them?

**Fix (added to design):**
- New dir: `open_edit/agent/skills/motion_graphics/templates/`
- One Python file per beat type: `hook.py`, `turn.py`, `scope.py`, `mechanism.py`, `cost.py`, `tease.py`, `button.py`
- Each template exports a `TEMPLATE = MotionTemplate(...)` object with: name, beat_type, parameters (Pydantic model), generate_code(params) -> Python source (manim/moviepy/headless canvas), default_params.
- Template library seeded with 2-3 example templates per beat type (the "US map with dots merging into a computer" is one of them). v1.1 adds more.

---

### L3 — `§3.6` anchor discriminated union Pydantic syntax

**Original (§3.6):** "Discriminated union: timestamp / region / op anchors all serialize and deserialize correctly."

**Problem:** Pydantic v2 discriminated union syntax is non-obvious. Test should verify it works.

**Fix (added to design with code snippet):**
```python
from pydantic import BaseModel, Field
from typing import Literal, Annotated, Union

class TimestampAnchor(BaseModel):
    anchor_type: Literal["timestamp"] = "timestamp"
    t_start: float
    t_end: float

class RegionAnchor(BaseModel):
    anchor_type: Literal["region"] = "region"
    x: float; y: float; w: float; h: float
    t_start: float; t_end: float

class OpAnchor(BaseModel):
    anchor_type: Literal["op"] = "op"
    op_id: str

NoteAnchor = Annotated[
    Union[TimestampAnchor, RegionAnchor, OpAnchor],
    Field(discriminator="anchor_type")
]

class ReviewNote(BaseModel):
    note_id: str
    project_id: str
    anchor: NoteAnchor
    text: str = ""
    source: NoteSource  # "typed" | "voice" | "region" | "agent" | "form_correction"
    status: NoteStatus  # "pending" | "processed" | "dismissed"
    created_at: str
    processed_at: Optional[str] = None
    resulting_op_ids: list[str] = []
    commit_token: Optional[str] = None
```

---

## Missing Things I Want to Add (5)

### Add 1 — T8 IR extension (promoted from inline §3.8)

See C2 above. ~0.5 day.

### Add 2 — T9 notes DB archival housekeeping

See M3 above. ~0.5 day. Trivial SQL, important for long-running projects.

### Add 3 — Phase 4.5 task breakdown

The revised design has §4 but no concrete task breakdown. I added 8 Phase 4.5 tasks to the plan:
- W1: Whisper integration (~2 days)
- W2: Render sandbox Rust binary (~1 week)
- W3: Silence cutter skill (~2 days)
- W4: Narrative analyzer skill (~2 days)
- W5: Music selector skill + IR op (~2 days)
- W6: SFX placer skill + IR op (~1.5 days)
- W7: Motion graphics skill (templated) + template library (~1 week)
- W8: Long-form stress test (~0.5 day)

Total: ~20 days = 4 weeks.

### Add 4 — T8 sequencing rationale

The original §11 order had T1 before T6, T2, T8. Fixed: T8 → T6 → T2 → T5 → T4 → T7 → T1 → T9.

### Add 5 — Risk register

Added a §16 risk register covering:
- Whisper model download size (~150MB for `base`, ~1.5GB for `large-v3`)
- Faster-whisper is CTranslate2-backed; native deps may not be portable
- Render sandbox trust posture (no seccomp) is intentional but explicit
- Motion graphics templated vs. bespoke tradeoff may need revisit
- 11-minute video end-to-end budget may not hold for "go full creativity" run (bespoke or many LLM calls)

---

## Sequencing (Final)

| # | Task | Effort | Depends on | Notes |
|---|---|---|---|---|
| 1 | T8 IR extension (`originating_note_id` on Operation) | 0.5d | — | Foundation for T7 |
| 2 | T6 unified notes store + sidebar | 2d | T8 (commit_token field) | Foundation for T5, T7 |
| 3 | T2 style memory (aggregate + retrieve + style_inject) | 1.5d | — | Foundation for T1 |
| 4 | T5 HTML5 preview player + region mark + per-frame notes + STT | 1.5d | T6 | Depends on NotesStore |
| 5 | T4 RenderSnapshotStore + version switcher | 1d | — (Phase 2 orchestrator exists) | Independent |
| 6 | T7 commit_feedback + version_ready notification | 1d | T6, T8 | Stamps originating_note_id |
| 7 | T1 tool repointing + 5 new tools + creativity_level | 2d | T6, T2 | Last Phase 4 task |
| 8 | T9 notes DB archival housekeeping | 0.5d | T6 | Small, runs on commit |
| 9 | (parallel) W1 Whisper integration in AssetStore | 2d | — | Phase 4.5 start |
| 10 | (parallel) W2 Render sandbox Rust binary | 5d | — | Phase 4.5 critical path |
| 11 | W3 Silence cutter skill + new tool | 2d | W1 | Phase 4.5 |
| 12 | W4 Narrative analyzer skill + new tool | 2d | W1 | Phase 4.5 |
| 13 | W5 Music selector skill + AddMusicTrackOp (or AddEffectOp extension) | 2d | W4 | Phase 4.5 |
| 14 | W6 SFX placer skill + AddSfxOp (or AddEffectOp extension) | 1.5d | W4, W5 | Phase 4.5 |
| 15 | W7 Motion graphics skill (templated) + template library | 5d | W2, W4 | Phase 4.5 longest pole |
| 16 | Long-form stress test (§9.8) | 0.5d | All of above | Validates 11-min claim |

**Phase 4 total:** ~9 days (1.8 weeks)
**Phase 4.5 total:** ~20 days (4 weeks)
**Total:** ~29 days (~5.8 weeks)

---

## Open Questions (now answered)

| Q | Original | Answer |
|---|---|---|
| §12.1 | §2 verification — who runs it, by when? | I just ran it. Memo at `.superpowers/sdd/phase4-section-2-verification-memo.md`. Result: Phase 4.5 in scope. |
| §12.2 | §4.3 templated vs. bespoke? | **Templated** (per design recommendation). |
| §12.3 | §4.3 sandbox fix — two sandboxes or expand Phase 3? | **Two sandboxes (A)**. New `open-edit-render-sandbox` Rust binary. |
| §12.4 | §7 brand profile — wizard in v1, defer to v1.1? | **Minimal brand profile in Phase 4.5, full wizard v1.1.** |
| §12.5 | §7 export/upload — scoped to later phase? | **Defer to v1.1.** Local MP4 export only for v1. |
| §12.6 | §9.8 long-form stress test budget? | **15 min wall clock for 5-min video is acceptable.** Document the budget. |
| §12.7 | T3 de-scope — confirm slider/form UI moves to v1.1? | **Confirmed.** Free-text `correction_note` is the v1 primary input. |

---

## §10 "Done When" Additions (3 new items)

Added to the existing 17:
- 18. T8 IR extension: `originating_note_id` field on `Operation` Pydantic model, default `None`; existing fixtures continue to work; new tests pass.
- 19. T9 notes archive: on `commit_feedback` completion, processed notes older than 30 days move to `notes_archive` table; pending notes never archived.
- 20. `RenderSnapshotStore` max-versions cap: default 20; evict oldest `status=ready`; never evict `status=rendering` or `status=failed`.

---

## Summary of Changes Applied

- §2: Verification memo filled in (all 3 questions = NO, Phase 4.5 in scope)
- §3.1: T1 dependencies on T6 and T2 made explicit
- §3.4: `RenderSnapshotStore` cap, version switcher states, max-versions cap
- §3.5: `t_start=0` → `t_start < 0` fix; STT HTTPS requirement; note placement in project state column
- §3.6: Pydantic discriminated union syntax; WS broadcast scope; `summary_only` param on `pyagent_get_pending_notes`
- §3.7: `commit_token` race fix
- §3.8: Promoted to T8 with proper task scope; clarified payload-JSON storage (no SQL change)
- §6: RenderSnapshotStore cap documented
- §7: T9 housekeeping added; brand profile minimal in 4.5, wizard v1.1
- §8: Race conditions, version switcher states, max-versions cap, t_start < 0
- §9: Tests for T8, T9, races, version switcher, RenderSnapshotStore cap
- §10: Items 18-20 added
- §11: Reordered (T8 → T6 → T2 → T5 → T4 → T7 → T1 → T9)
- §12: All questions answered
- §13: Updated bottom line to note audit completion
- §14 (NEW): §2 verification memo
- §15 (NEW): This audit log
- §16 (NEW): Risk register

All changes integrated into the implementation plan (separate file).
