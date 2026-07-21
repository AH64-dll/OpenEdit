# Phase 8 — Native Dock (stretch)

## Context (recap)

This is the literal reading of "a PyAgent UI chat inside the video editor
Kdenlive" — a panel compiled into Kdenlive's own window, not a companion app
next to it. It's the most expensive, highest-maintenance phase in this
guide, and per the architecture decision (§5.2 of the findings doc), it
should be earned by actually using Phases 0–6 (and optionally 7) in real
editing sessions first, not built because it's the "purest" version of the
original ask. Depends on Phase 4's chat UI already existing as a working
local web app — that choice was made specifically so this phase could reuse
it rather than rebuild the frontend.

## Goal

Embed Phase 4's chat interface as a real dock inside Kdenlive's own window,
sitting alongside the Bin, Effects Stack, and Monitor docks, toggleable and
positionable the same way those are.

## Where this patch lives

Decide this before writing any C++:

- **Patch vanilla `KDE/kdenlive`** if you're staying on the file-based
  backend (Phase 2) or haven't adopted Phase 7.
- **Patch on top of `D-Ogi/kdenlive`** if Phase 7's D-Bus backend is in
  active use — the two pair naturally (live editing, live panel), and
  you're already maintaining a build of the fork, so this is one dock
  widget added to an already-forked tree rather than a second independent
  fork to track.

Either way, this is now genuinely a personal Kdenlive fork you build from
source, not a plugin you drop in — Kdenlive has no plugin loading mechanism
for arbitrary third-party dock widgets (confirmed in the findings doc §2),
so "embedded" here means "compiled in."

## Implementation shape

- Add a new dock widget (using **KDDockWidgets**, the same docking system
  Kdenlive's own Bin/Effects Stack/Monitor panels use as of the
  architecture described in the findings doc §1) that embeds a
  `QWebEngineView` pointed at Phase 4's `localhost` server.
- Register it through the same mechanism Kdenlive's existing docks use so it
  shows up in the View menu / dock-visibility list like a first-class
  panel, not a floating window that happens to be borderless.
- On Kdenlive 25.12+, dock layouts get embedded into the project file
  itself (per the findings doc §1) — check whether an out-of-tree custom
  dock participates in that saved-layout system automatically, or whether
  it needs to be special-cased; don't assume without checking against your
  actual build.
- Keep Phase 4's frontend and backend exactly as they are — the reuse
  payoff from choosing "local web app" back in Phase 4 is that this phase
  touches only the C++ shell around a `QWebEngineView`, not the chat UI
  itself. The backend can stay out-of-process over HTTP even though the
  frontend is now embedded; only rewrite this into fully in-process calls
  if `localhost` latency inside the same machine turns out to actually
  matter, which is unlikely.

## The real cost of this phase: ongoing maintenance, not the initial build

The dock widget itself is a bounded, buildable piece of work. The recurring
cost is that every future upstream Kdenlive release (or, if on the Phase 7
track, every time the fork rebases against a new upstream commit) means
re-applying this patch by hand. Budget for this as an ongoing tax, not a
one-time cost, and keep the patch as a clean, minimal diff — not scattered
inline changes — specifically so re-applying it stays cheap. If re-basing
starts costing more time than the embedded panel saves you over the
companion window from Phase 4, that's a legitimate reason to drop back to
Phase 4 permanently; this phase doesn't have to be a one-way door.

## Explicit non-goals for this phase

- Not proposing this dock for inclusion in upstream Kdenlive as part of this
  guide — that's a real option if it proves solid, but it's a different
  kind of project (KDE Review process, C++ code-quality bar, ongoing
  community maintenance commitment) and out of scope here.
- Not rewriting the chat frontend in native Qt/QML — reuse the
  `QWebEngineView` + Phase 4 web app; a native rewrite is extra work for a
  UI that already works.
- Don't attempt this phase before Phases 0–6 are stable and actually being
  used — this is the guide's own version of "earned, not defaulted to," the
  same principle Phase 5 applies to its window-automation fallback.

## Acceptance criteria

- [ ] The dock is visible and toggleable from Kdenlive's View/Docks menu,
      positioned and resized the same way any built-in dock can be.
- [ ] Chat, pending-edit-plan cards, and the project-state panel all
      function identically to the standalone Phase 4 window when embedded —
      no feature regression from being inside the dock.
- [ ] Dock visibility/position survives a Kdenlive restart, and the behavior
      of Kdenlive 25.12+'s project-embedded layout system with respect to
      this custom dock is explicitly documented (participates / doesn't /
      partially — whichever it actually is).
- [ ] The patch is kept as a single, reviewable diff against a documented,
      pinned Kdenlive (or fork) commit hash — not inline changes scattered
      across the tree — so it can actually be re-applied when upstream
      moves.
- [ ] This phase's output states plainly whether the maintenance cost, in
      practice, was worth it over keeping Phase 4's companion window — this
      is the honest closing note the guide asks for, not a formality.

## Handoff

None — this is the last phase in the guide. If you get here and it's
holding up, `01_FINDINGS_AND_ARCHITECTURE.md`'s architecture decision
(build the file-based backend first, keep the D-Bus/native-dock tracks
strictly additive and optional) did its job: nothing in Phases 0–6 depended
on this phase succeeding, and nothing here required redoing earlier work to
get here.
