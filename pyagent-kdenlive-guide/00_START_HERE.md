# START HERE — PyAgent for Kdenlive

This is a build spec for handing to your coding agent (OpenCode, Antigravity, or
whoever's driving). It answers the question you actually asked — "can an AI chat
UI live inside Kdenlive and edit for me" — with real findings, not guesses, and
then breaks the build into phases the same shape as your `mlt-pipeline` docs.

Read this file first. Then read `01_FINDINGS_AND_ARCHITECTURE.md` once, fully,
before writing any code — it's the "why" behind every phase and will save you
from your agent reinventing things that don't exist or missing things that
already do. After that, hand `PHASE_0` through `PHASE_8` to your agent one at a
time, in order. Each phase file is self-contained (context recap + task +
acceptance criteria) so it survives a fresh session, same as `edl_writer.md`
does for your existing pipeline.

## The one-paragraph answer

Kdenlive has **no official plugin API, no scripting console, and no headless
CLI automation** — confirmed from Kdenlive's own architecture docs and from the
Linux Command Library's own note that it's "not designed for headless operation
or extensive scripting." So "chat UI inside Kdenlive" can't be built the way
you'd build a Blender addon. But there are two real, working paths, and you
don't have to pick just one:

1. **File-based control** — PyAgent reads and writes the `.kdenlive` project
   file directly (it's just MLT XML plus Kdenlive-specific tags). Zero
   modification to Kdenlive itself, 100% in your control, buildable this week.
   Costs you: no live "watch it happen," you reload the project to see changes.
2. **A patched Kdenlive with a real D-Bus scripting API** — someone has already
   built almost exactly what you're describing (`D-Ogi/kdenlive`, a fork with
   108 scriptable methods, plus a Python client and an MCP server on top of
   it). If it builds cleanly for you, it gives PyAgent *live* control with
   Kdenlive's own undo/redo working on AI edits. Costs you: depending on a
   small, unreviewed third-party fork for something load-bearing.

The recommended order below builds path 1 first (it can't fail you), and
spikes path 2 early so you know by Phase 0 whether it's worth adopting instead
of, or alongside, path 1.

## What "PyAgent" means in this guide

You used this name for "a Python-based AI agent, because Python is easy to
modify." Nobody in this space has already claimed that name for a specific
product — the closest prior art (`D-Ogi/kdenlive-api`) calls itself something
else. So in this guide, **PyAgent = the Python process you're going to build**:
the LLM tool-calling loop that turns your chat messages into edits. It's yours,
it's small, and it's the one piece of this whole system you'll be modifying
constantly — everything else (the file engine, the D-Bus bridge if you adopt
it) is infrastructure PyAgent calls into.

## How this relates to `mlt-pipeline`

You're not throwing that project away. `mlt-pipeline` is a good **batch**
tool: point it at a folder of footage, get a rough cut back, done in one shot.
PyAgent is a **conversational, iterative** tool: you keep talking, it keeps
adjusting the same project. They can share code (the Go project's `internal/edl`
validate-then-clamp pattern, the `internal/mlt` XML generation ideas, the
`render --dry-run` melt wrapper) — Phase 2 and Phase 6 of this guide port those
ideas into Python rather than discarding them. And Phase 2 directly fixes the
"opens as Untitled" limitation your own docs already flagged, by emitting a
real `.kdenlive` file instead of a bare `.mlt`.

## Reading order

| Order | File | What it's for |
|---|---|---|
| 1 | `00_START_HERE.md` | this file |
| 2 | `01_FINDINGS_AND_ARCHITECTURE.md` | everything researched, the architecture decision, the risk register. Read fully once. |
| 3 | `PHASE_0_spike_and_validate.md` | cheap experiments that de-risk everything else — do this before committing to anything |
| 4 | `PHASE_1_knowledge_base.md` | builds the "what tools exist" corpus PyAgent will read from |
| 5 | `PHASE_2_project_engine.md` | the Python library that actually reads/writes `.kdenlive` files |
| 6 | `PHASE_3_pyagent_core.md` | the chat/tool-calling agent loop itself |
| 7 | `PHASE_4_chat_ui.md` | the interface you actually type into |
| 8 | `PHASE_5_sync_and_reload.md` | closing the loop so Kdenlive shows what PyAgent did |
| 9 | `PHASE_6_render_and_qc.md` | rendering previews/finals and sanity-checking them, conversationally |
| 10 | `PHASE_7_dbus_fork_track.md` *(stretch)* | evaluating/adopting the D-Bus fork for live, undoable control |
| 11 | `PHASE_8_native_dock_stretch.md` *(stretch)* | truly embedding the chat panel inside Kdenlive's own window |

Phases 0–6 get you a complete, working, useful PyAgent. Phases 7–8 are where
you go if you want it to feel more native and you're willing to invest more.
Nothing in 0–6 depends on 7–8 succeeding.

## One assumption worth stating up front

Everything in this guide assumes Linux (you're on EndeavourOS), since D-Bus,
the fork, and the file layout conventions referenced are all Linux-specific.
If you ever need this on Windows/macOS too, the file-based path (Phase 2) is
the only one that ports without major rework.
