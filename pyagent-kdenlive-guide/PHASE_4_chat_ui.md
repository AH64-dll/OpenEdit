# Phase 4 — Chat UI

## Context (recap)

Phase 3 works from a terminal. This phase gives it a real interface. Per the
architecture decision (§5.2 of `01_FINDINGS_AND_ARCHITECTURE.md`), this is a
companion window that sits next to Kdenlive, not embedded inside it — that's
Phase 8, a much larger and separate investment, deliberately deferred.

## Goal

Something you'd actually want to keep open while editing: a chat transcript,
a way to see what PyAgent is about to do before it does it (if
`auto_approve` is off), and a glance at current project state without
tabbing over to Kdenlive.

## Recommended shape

Pick one — both are reasonable, and this is the swappable layer of the whole
guide.

**Option 1 — local web app (recommended).** FastAPI (or Flask) backend
wrapping Phase 3's interface, a small frontend (plain HTML/JS, or React
since you're already comfortable with it from GameHub) served on
`localhost`, opened in a normal browser window sized and positioned next to
Kdenlive. Lowest new-dependency cost, easiest to iterate on, and the same
shape Phase 8 would need anyway if you ever embed it in a `QWebEngineView`
dock — so building it as a clean local web app now isn't wasted work even if
you go that far later.

**Option 2 — a small PySide6/PyQt6 always-on-top panel.** Tighter OS
integration (can genuinely dock itself to a screen edge, doesn't need a
browser), costs you a heavier Python GUI dependency and more UI code to
maintain by hand instead of HTML/CSS.

**Default recommendation:** Option 1, specifically because of the Phase 8
reuse angle above. Switch to Option 2 only if you have a concrete reason
(e.g. you want it to feel like a native panel more than you value the later
reuse).

## UI surface needed

- Chat transcript (user + PyAgent messages).
- Pending-edit-plan card: when `auto_approve` is off, render Phase 3's
  plain-language + diff-style summary with explicit Approve/Reject/Edit
  actions — don't bury this in the chat transcript as just more text, it
  needs to be visually distinct since it's the main safety mechanism.
- Current project state panel (track list, clip count, duration) — pull this
  from `get_project_info()`/`get_timeline_summary()` on load and after every
  applied change, don't let it go stale.
- A handful of quick-action buttons for the most common single-step requests
  (e.g. "add crossfade between selected," "render preview") — optional
  polish, not blocking for a first working version.

## Explicit non-goals for this phase

- Not embedding inside Kdenlive's own window — Phase 8, if you get there.
- Not building real-time video preview inside this UI — per the findings
  doc's token-efficiency principle (reused from D-Ogi's design doc), PyAgent
  itself should never be dealing with full-resolution frames; if you want a
  human-facing preview, that's `render --dry-run`'s proxy output (Phase 6),
  played in any normal video player, not something this chat UI needs to
  stream itself.
- No user accounts/auth — this is a single-user local tool.

## Acceptance criteria

- [ ] Can hold a multi-turn conversation with PyAgent from this UI, with
      responses appearing without a full page reload.
- [ ] A pending edit plan is visually distinct from ordinary chat text and
      has working Approve/Reject actions wired to Phase 3.
- [ ] The project state panel reflects the actual current state after an
      approved edit, without needing a manual refresh.
- [ ] Runs alongside a real, open Kdenlive instance without interfering with
      it — it is not writing to the file Kdenlive currently has open unless
      going through Phase 5's sync step. Verify this explicitly, since a
      naive implementation could otherwise write underneath Kdenlive while
      it's mid-session.

## Handoff to Phase 5

Phase 5 needs to know exactly when this UI has caused a file write, so it
can trigger (or prompt the user toward) a reload in Kdenlive at the right
moment — not before the write completes, not so late that several edits
pile up unreflected.
