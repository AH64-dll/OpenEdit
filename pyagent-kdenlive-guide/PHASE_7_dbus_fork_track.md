# Phase 7 — D-Bus Fork Track (stretch)

## Context (recap)

This phase only exists because of what Phase 0's half-day spike found. If
`spike-results/dbus_fork_spike.md` says the `D-Ogi/kdenlive` fork didn't
build, or you never got past a couple of hand-tested D-Bus calls, don't
start this phase — Phases 0–6 already give you a complete, working PyAgent
on the file-based backend alone, and this phase is explicitly the "invest
further only if it's worth it" branch the findings doc flags in §4's risk
assessment.

## Goal

Implement a second `EditorBackend` (the interface Phase 2 defined) that
talks to the patched Kdenlive over D-Bus instead of reading/writing files,
so PyAgent can edit live — visible immediately, no reload dance — with
Kdenlive's own undo stack backing every AI edit for free.

## Prerequisite: nail down the real interface before writing a line of backend code

Phase 0's spike flagged a genuine discrepancy across D-Ogi's own repos — the
fork's README says `org.kde.kdenlive.MainWindow`, the Python client's
README says `org.kde.kdenlive.scripting`. Don't guess or split the
difference. Re-run the introspection from Phase 0 against your actual built
binary:

```
qdbus | grep -i kdenlive
qdbus org.kde.kdenlive.<candidate> /
```

or the `busctl --user` equivalent, and record the real interface name and
method signatures in this phase's own `spike-results/` follow-up before
touching Phase 2's interface. If the fork has moved since Phase 0 (new
commits on `master`), re-clone at a pinned commit and note the exact hash
you're building against — "which commit" is a Phase-0-and-7-both concern,
since reload behavior and method availability can drift.

## Building the backend

- Prefer `D-Ogi/kdenlive-api` (the Python client) over hand-rolled `pydbus`
  calls where it covers what you need — it's already shaped like DaVinci
  Resolve's API and has 81 unit tests against a mock backend, which is a
  meaningfully better starting point than raw D-Bus. Drop to raw
  `pydbus`/`PyGObject` only for the handful of the fork's 108 methods the
  client doesn't wrap yet.
- Implement `DBusEditorBackend` against the exact same method signatures as
  Phase 2's file-based `EditorBackend` (`get_project_info`,
  `get_timeline_summary`, `insert_clip`, `add_transition`, `apply_effect`,
  and so on) — Phase 3 should not need a single line changed to run against
  this backend instead of the file-based one. If a Phase 2 operation has no
  clean D-Bus equivalent, say so explicitly in this phase's output rather
  than silently degrading it.
- Reuse Phase 1's catalog for effect/transition validation on this backend
  too — the catalog describes what Kdenlive can do, not which backend is
  talking to it, so there's no reason for it to differ.
- Make the backend a config value in Phase 3 (`editor_backend: "file" |
  "dbus"`), matching the model-provider-as-config-value decision already
  made there. This should be a restart-time choice, not something that
  silently switches mid-session.

## Failure handling — don't fall back to the file backend mid-session

If a D-Bus call fails or times out while this backend is active, PyAgent
must not silently fall back to writing the project file directly — that's
exactly the race Phase 5 exists to prevent, and it's worse here because
Kdenlive is definitely open and definitely has the file loaded. On a D-Bus
failure: surface the error to the user plainly, and let them choose to
retry the call, abandon it, or restart PyAgent against the file-based
backend (which then follows Phase 5's normal reload flow, since Kdenlive
would need to be closed and reopened cleanly first anyway).

## What this backend gets you that Phase 5 couldn't

- No reload step at all — edits are visible in Kdenlive immediately.
- A real "undo the AI's last edit" affordance: call the fork's
  `Undo`-equivalent `Q_SCRIPTABLE` method (confirm its exact name via the
  same introspection step above) instead of PyAgent tracking its own undo
  stack. This can replace or supplement Phase 3's propose-then-apply
  confirmation for low-stakes edits, if you decide you trust "do it, then
  undo if wrong" more than "confirm, then do it" once this backend is
  solid — that's a judgment call to make after using it, not something to
  decide up front.
- Phase 5 becomes almost entirely unnecessary when this backend is active;
  keep it as the fallback path for whenever you're running the file-based
  backend instead, since both backends need to coexist, not replace each
  other.

## Explicit non-goals for this phase

- Don't patch the fork further — if a method you need is missing or broken,
  that's an upstream issue/PR on `D-Ogi/kdenlive`, not a personal
  patch-on-a-patch to maintain. Fall back to the file-based backend for that
  specific operation if needed.
- Don't remove or deprecate the file-based backend — it remains the default
  and the only one guaranteed to keep working if this fork stops being
  maintained.
- Don't chase all 108 exposed methods — implement what Phase 2's operation
  list actually needs, matching Phase 2's own "start narrow and correct,
  widen later" principle.

## Acceptance criteria

- [ ] The exact D-Bus interface name and method signatures actually used
      are documented against a specific, pinned fork commit hash — not
      "whatever `master` was on some day."
- [ ] An edit made through PyAgent via this backend appears in Kdenlive's
      own timeline without any reload, restart, or manual action.
- [ ] Calling the fork's `Undo`-equivalent method from PyAgent correctly
      reverts the most recent AI-made edit, verified against Kdenlive's own
      undo history (not just "the file looks reverted").
- [ ] Switching `editor_backend` from `file` to `dbus` in config, with no
      other code changes, produces a working PyAgent session — this is the
      actual proof the interface boundary from Phase 2 held up.
- [ ] A deliberately induced D-Bus failure (e.g. call Kdenlive while it's
      not running) is reported clearly to the user rather than silently
      falling back to a file write.

## Handoff to Phase 8

If this backend is adopted, Phase 8's native dock becomes noticeably more
attractive to build, since a live-editing backend pairs naturally with a
live-embedded panel — but Phase 8 does not require this phase; it can be
built against either backend.
