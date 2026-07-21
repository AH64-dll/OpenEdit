# Phase 5 — Sync & Reload

## Context (recap)

This phase exists entirely because of what Phase 0 found (or didn't find)
about whether Kdenlive notices when its open project file changes on disk.
Do not start this phase until Phase 0's `reload_behavior.md` has an actual
observed answer written in it — everything below branches on that finding.

## Goal

Close the loop between "PyAgent wrote changes to the file" and "the change
is visible in Kdenlive," as automatically as is reasonably possible given
what Kdenlive actually supports.

## Branch on Phase 0's finding

**If Kdenlive auto-reloads or prompts to reload on external changes:** this
phase is nearly free — just make sure Phase 2 always writes through a safe
atomic save (write to a temp file, then rename over the original) so
Kdenlive never reads a half-written file mid-save, and confirm the
prompt/reload behavior is still consistent when several rapid edits land
close together.

**If Kdenlive does nothing** (most likely, based on how most desktop apps
handle this absent an explicit "reload footage"-style feature): rank the
options below and implement the cheapest one that's still genuinely useful,
rather than jumping straight to automation.

1. **Manual reopen, with a clear signal.** PyAgent's chat UI (Phase 4) shows
   a plain "project updated — reopen in Kdenlive to see it" notice after
   each applied change. Zero engineering risk, costs the user one click.
   This is the correct default and may be all you need.
2. **A desktop notification** (via whatever notify mechanism your desktop
   environment supports) at the same moment, for when the chat UI window
   isn't in focus.
3. **Automated reload via window automation**, only if 1–2 feel genuinely
   too manual in practice: use `wmctrl`/`xdotool` (X11) to find the Kdenlive
   window and simulate whatever keyboard shortcut corresponds to closing and
   reopening the current project (check `kdenliveui.rc` from Phase 1 for the
   real shortcut rather than guessing), or the equivalent KWin/D-Bus
   approach if on Wayland. Mark this clearly as fragile — it breaks silently
   if Kdenlive's UI changes — and keep option 1 as the fallback path if it
   fails rather than failing silently.
4. **If Phase 7's D-Bus fork gets adopted**, its `Open`-equivalent
   `Q_SCRIPTABLE` method (verify its exact name against Phase 0's `qdbus`
   introspection results) replaces all of the above with a real,
   non-fragile reload call. This is one of the concrete, checkable reasons
   Phase 7 might be worth the investment even after Phases 0–6 are solid on
   their own.

## Explicit non-goals for this phase

- Don't build option 3 (window automation) unless options 1–2 have actually
  been tried and found lacking in real use — this is the most fragile piece
  in the whole guide and should be earned, not defaulted to.
- Don't attempt to detect what specifically changed and reload only that — a
  full reload/reopen is fine; diffing Kdenlive's in-memory state isn't
  something you have access to without Phase 7 anyway.

## Acceptance criteria

- [ ] After PyAgent applies an edit through the chat UI, there's a clear,
      correctly-timed signal (in whichever form was implemented) telling
      the user the project file changed.
- [ ] Rapid successive edits (two or three in under a minute) don't produce
      duplicate/conflicting reload signals.
- [ ] Whatever mechanism was implemented is documented in this phase's
      output with the actual observed Kdenlive version it was tested
      against — reload behavior is exactly the kind of thing that can
      change between Kdenlive releases.

## Handoff to Phase 6

None directly — Phase 6 (render/QC) is independent of this phase and can be
built in parallel if useful.
