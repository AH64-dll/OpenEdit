# Findings & Architecture Decision

Everything below was verified against Kdenlive's own architecture docs, its
source repository, its manual, and existing prior art — not assumed. Where I
couldn't verify something directly, I've said so and turned it into a Phase 0
task instead of a claim.

---

## 1. What Kdenlive actually is, technically

- Kdenlive 25.x is a **C++ application built on Qt6 and KDE Frameworks 6**,
  fundamentally a GUI wrapper around the **MLT multimedia framework**. It is
  not a scripting-language host (no embedded Python, no Lua) — it's a
  compiled, monolithic desktop app.
- Architecture is a `Core` singleton (`pCore->window()`, `pCore->bin()`,
  `pCore->projectManager()`, `pCore->monitorManager()`, `pCore->currentDoc()`)
  that every subsystem hangs off of. The timeline is MVC: `TimelineItemModel`
  (data) + `timeline.qml` (view) + `TimelineController`/`TimelineFunctions`
  (the methods that actually do things). Every timeline maps 1:1 onto an
  `Mlt::Tractor`; every track is an `Mlt::Playlist`; every clip wraps an
  `Mlt::Producer`; every effect is an `Mlt::Filter`.
- Docking (Bin, Effects Stack, Monitor, etc.) uses **KDDockWidgets**, and as of
  Kdenlive 25.12 layouts are flexible and get embedded into the project file
  itself. This matters for Phase 2 — a hand-written project file that omits
  layout data won't corrupt anything, but won't look like a "real" saved
  project either.
- Rendering is genuinely client-server internally: the main app prepares a job
  (`RenderWidget`/`RenderRequest`) and hands it to a separate `kdenlive_render`
  process, which itself shells out to `melt`/`ffmpeg`. This is why your
  existing pipeline calling `melt` directly is the *correct* mental model —
  you're doing exactly what Kdenlive's own renderer does, just without the
  detour through `kdenlive_render`.

**Sources:** Kdenlive's own DeepWiki-indexed architecture overview
(deepwiki.com/KDE/kdenlive), the KDE/kdenlive GitHub repo description, and the
Kdenlive 25.12.0 release notes (new docking system, embedded layouts).

## 2. What Kdenlive does **not** have

This is the part that determines everything else, so it's worth being
explicit rather than optimistic:

| Thing you might hope exists | Reality |
|---|---|
| A plugin/extension API (like Blender's `bpy`, OBS plugins, DaVinci Resolve scripting) | **Does not exist upstream.** Kdenlive's own manual has a page called "Plugins," but it refers to optional AI feature modules (Vosk/Whisper speech-to-text), not a third-party extension system. |
| A D-Bus interface for scripting the timeline | **Does not exist upstream.** Standard KDE apps expose *some* D-Bus (single-instance activation, generic freedesktop interfaces) but nothing that touches the project/timeline. Confirmed both by absence of evidence and, more strongly, by the fact that the best prior art in this space (§4 below) explicitly describes itself as *adding* a D-Bus scripting API that wasn't there before. |
| Headless / CLI-scriptable batch editing | **Does not exist.** Kdenlive's own command-line reference is limited to opening a project file, `--version`, `--help`. An independent summary states plainly it's "not designed for headless operation or extensive scripting of editing tasks purely via the command line." |
| Python bindings exposed *by Kdenlive* | **Does not exist.** (MLT itself has separate, optional Python bindings — see §3.3 — but that's MLT, not Kdenlive, and it doesn't know about Kdenlive-specific project metadata.) |

None of this means the project is unreasonable — it means "chat UI that edits
inside Kdenlive" has to be built as *client + bridge*, not as a plugin you
drop into a folder. That's what §5 lays out.

## 3. The project file, and where the "docs to feed the AI" already exist

### 3.1 `.kdenlive` is MLT XML, not a separate format

A `.kdenlive` file is a valid MLT XML document (`<mlt>` → `<profile>` →
`<producer>`s → `<playlist>`s → `<tractor>`) with a layer of
`kdenlive:`-namespaced properties and elements on top: bin folder structure,
notes, guides/markers, document version, and — as of 25.12 — embedded UI
layouts. `melt` (the MLT command-line player/renderer your pipeline already
calls) can play the video track structure of a `.kdenlive` file directly
because the MLT part of it is standard.

Document version is tracked explicitly:
`<property name="kdenlive:docproperties.version">1.1</property>`. Kdenlive
auto-upgrades and backs up old-version files on open — useful to know because
it means Phase 2's writer doesn't have to chase every historical format
quirk, just the current one, and Kdenlive will tell you (via a backup file)
if something looks stale.

**This is also your fix for the "opens as Untitled" limitation** your own
project docs already flagged: your Go pipeline currently emits a bare `.mlt`
with no `kdenlive:` metadata at all, so Kdenlive treats it as an untitled
import rather than a project. Phase 2 emits the real thing.

### 3.2 The single best resource for "the AI should know all the tools": Kdenlive's own effect/transition definitions

Kdenlive ships **machine-readable XML definitions for every effect and
transition it exposes**, in its own source tree:
`data/effects/*.xml` (and the parallel `data/transitions/` /
`data/generators/` folders). Each one is small and structured:

```xml
<effect xmlns="https://www.kdenlive.org" tag="crop" id="crop">
    <name>Edge Crop</name>
    <description>Trim the edges of a clip</description>
    <author>Dan Dennedy</author>
    <parameter type="constant" name="top" max="%maxHeight" min="0" default="0" suffix="pixels">
        <name>Top</name>
    </parameter>
    ...
</effect>
```

`tag` is the underlying MLT service name (what actually goes into the project
XML's `<filter mlt_service="...">`); `id` is Kdenlive's internal id; each
`<parameter>` carries type, min/max, default, suffix, and sometimes a
`<comment>` with a plain-English explanation. The schema itself is documented
in `data/effects/README.md` in the same repo — point your agent straight at
that file rather than having it guess at the format.

This is a far better "tool catalog" than scraped prose documentation: it's
already structured, already versioned alongside Kdenlive itself, and it's
*exactly* the set of things a human editor sees in the effects panel — so
when PyAgent says "I applied a Crop effect," that name means the same thing
to the user looking at Kdenlive's UI.

### 3.3 The second-best resource: MLT's own service metadata

One level below Kdenlive's curated list, MLT ships **YAML metadata for every
filter, transition, producer, and consumer it implements**
(`src/modules/*/filter_*.yml`, `producer_*.yml`, `transition_*.yml` in the
`mltframework/mlt` repo, schema documented at mltframework.org). Example
fields: `schema_version`, `type`, `identifier`, `title`, `description`,
`parameters` (each with `identifier`, `title`, `type`, `description`,
sometimes value lists). This is useful for two things Kdenlive's own XML
sometimes doesn't cover: filters MLT supports that Kdenlive's UI doesn't
expose, and deeper parameter documentation when Kdenlive's wrapper is terse.

These YAML files may already be installed locally if `mlt` is installed
(check the MLT data directory), or they can be pulled straight from
`github.com/mltframework/mlt`. Phase 0 has a task to check which.

### 3.4 Known gap: some things genuinely aren't documented anywhere

Worth setting expectations: even KDE's own bug tracker has an open report
(#496494) that the Wipe/Luma/Dissolve transition parameters aren't properly
documented in either the XML comments or the manual. Phase 1's plan accounts
for this with a small hand-built "cookbook" step — make one change in the
Kdenlive GUI at a time, save, diff the XML — for the handful of assets where
the structured sources have gaps.

### 3.5 MLT Python bindings exist, but treat as "check first"

MLT has historically shipped optional Python bindings (`mlt-python-bindings`
on Arch/AUR, `python-mlt` under other naming). These would let Phase 2's
engine construct `Mlt::Producer`/`Mlt::Playlist`/`Mlt::Tractor` objects
programmatically instead of hand-templating XML strings — more robust for the
MLT-standard parts of the file. Availability and exact package name drift
over time and distros, so Phase 0 includes a concrete check on your actual
EndeavourOS machine rather than assuming. If it's not available or feels
heavier than needed, plain XML manipulation (via `lxml`, which preserves
unknown elements far better than the standard library's `ElementTree`) is a
perfectly good fallback — it's what your existing Go pipeline already does
successfully, just string-templated instead of tree-edited.

## 4. Prior art — someone has already built most of this

This is the single most important finding in this document, so don't skip it.
A developer going by **D-Ogi** has published three linked, actively-tagged
repositories that together are extremely close to what you're describing:

### `D-Ogi/kdenlive` — a Kdenlive fork with a real D-Bus scripting API

A fork of `KDE/kdenlive` (GPL-3.0, tracks upstream `master`) that adds:

- **108 new `Q_SCRIPTABLE` methods** exposed over D-Bus, covering project
  ops, media pool, timeline (insert/move/resize/cut/slip/delete, track
  management), effects, compositions, audio, subtitles, markers/guides,
  groups, selection, sequences, zones, titles, proxy, playback, rendering,
  and undo/redo.
- A QuickJS-based JavaScript expression engine for keyframe parameters
  (audio-reactive effects, `sin(time*2)`-style expressions) — a nice-to-have,
  not something you need for the core ask.
- Two libplacebo GPU effects.

Build instructions follow standard Kdenlive build docs, with `-DUSE_DBUS=ON`.

*Caveat worth being honest about: the interface name is stated inconsistently
across this developer's own repos* — the fork's own README says
`org.kde.kdenlive.MainWindow`, while the companion Python library's README
says it talks to `org.kde.kdenlive.scripting`. Don't take either on faith;
Phase 0 / Phase 7 has you introspect the actual built binary with
`qdbus`/`busctl` to get ground truth before writing code against it.

### `D-Ogi/kdenlive-api` — a Python client, deliberately shaped like DaVinci Resolve's API

MIT licensed. Talks to the patched Kdenlive over D-Bus via `pydbus` +
`PyGObject`. The API is intentionally modeled on DaVinci Resolve's
well-known scripting API (`Resolve → ProjectManager → Project → MediaPool /
Timeline → TimelineItem`), on the stated theory that scripts and know-how
written for Resolve should port with minimal changes. Ships 81 unit tests
against a mock D-Bus backend (so testable without a running Kdenlive).

### `D-Ogi/mcp-kdenlive` — an MCP server on top of the above

Python, uses the official MCP SDK, exposes both **composite** tools
(`build_timeline`, `replace_scene`, `get_timeline_summary`,
`add_transitions_batch`, `render_video`) and **atomic** tools (project,
media, timeline, transitions, markers, replace, checkpoints). Meant to be
dropped straight into a Claude Code / MCP-compatible agent's config.

The design document behind this project (in the `kdenlive-api` repo's
`docs/` folder) independently arrived at several conclusions worth stealing
for PyAgent regardless of whether you adopt this fork:

- **Token efficiency as a first-class design constraint.** Project state
  goes to the agent as text (markdown tables), never GUI screenshots. Frame
  previews are capped thumbnails (≤480px, JPEG q70), never full-resolution
  frames. QC uses small 1:1 crops of a region, never a full frame. Audio
  preview is numeric (RMS/peak/waveform-as-list), never a spectrogram image.
- A **MoSCoW-prioritized capability list** that maps almost exactly onto
  "what does an editor need to do a real edit": Must-have = orientation,
  import, timeline building, trim, transitions, save/load, text-only state
  preview. Should-have = thumbnails, 1:1 QC crops, markers, batch ops, clip
  replace, audio basics, undo/checkpoints. Could-have = effects, titles,
  color grading, multi-track compositing, media analysis, EDL/FCPXML/OTIO
  interchange. Explicitly Won't-have = real-time preview streaming, GUI
  screenshots, full-res frames sent to the agent, vision-based content
  recognition, node-based (Fusion/OFX-style) compositing, Selenium-style live
  GUI-event simulation, multi-agent collaborative editing.

Phase 1 and Phase 3 of this guide reuse that prioritization shape and that
token-efficiency principle directly, whether or not you end up depending on
D-Ogi's actual code.

### Risk assessment on adopting this fork

Be clear-eyed: as of this research, these are small, very new, single-maintainer
repositories (low star/fork counts, short commit histories on the two Python
repos). That's not a criticism — it's exactly the kind of focused personal
project this guide is describing you build too — but it means:

- It might not build cleanly against the exact upstream commit it's currently
  based on, on your machine, today.
- 108 methods is a lot of surface area for a young project; some are more
  likely to be solid (basic timeline ops) than others (audio analysis,
  subtitle editing).
- It's GPL-3.0 (inherited from Kdenlive) — completely fine for your own use
  and for building on top of, but relevant if you ever wanted to distribute a
  compiled binary.
- No guarantee of continued maintenance as Kdenlive's `master` moves.

None of that is a reason to ignore it — it's a reason to **spike it early and
cheaply** (Phase 0) rather than commit to it architecturally before knowing
whether it actually works for you.

### Complementary, non-Kdenlive-specific prior art: `kwin-mcp`

A separate project, `isac322/kwin-mcp`, provides generic MCP-exposed desktop
automation for KDE Plasma 6 (screenshots, AT-SPI2 accessibility tree, mouse/
keyboard/touch injection via KWin's D-Bus EIS interface) for both virtual and
live sessions. This isn't Kdenlive-aware at all, but it's a reasonable
fallback tool for the small set of things neither the file engine nor the
D-Bus fork covers (e.g., "click the Render button and wait") without you
writing your own `xdotool` wrapper from scratch. Treat as optional/Phase 8
territory, not core infrastructure.

## 5. Architecture decision

### 5.1 Two real backends, one PyAgent

| | **A — File-based** (Phases 0–6) | **C — D-Bus fork** (Phase 7) |
|---|---|---|
| Requires modifying/rebuilding Kdenlive | No | Yes (build the fork) |
| Live (see it happen without reopening) | No — edit, then reload | Yes |
| Undo/redo | Your own (Phase 2 tracks its own history) | Kdenlive's native undo stack, for free |
| Engineering risk | Low — plain XML I/O, fully in your control | Medium/high — depends on a small third-party C++ patch |
| Time to first working demo | Days | Unknown until Phase 0's spike — could be a weekend, could be a dead end |
| Works if the fork is ever abandoned | Yes, unaffected | No |

**Decision: build A first, unconditionally. Spike C early (Phase 0), adopt it
in Phase 7 only if the spike says it's solid.** The reason this works cleanly
is that PyAgent (Phase 3) is designed against a small abstract "editor
backend" interface — a handful of operations like `insert_clip`,
`add_transition`, `apply_effect`, `get_timeline_summary` — rather than
against file-writing code directly. Backend A implements that interface by
editing XML; Backend C, if adopted, implements the *same* interface by making
D-Bus calls instead. PyAgent's brain doesn't change either way. This is the
single most important design decision in this guide — don't let it get
skipped for expedience.

### 5.2 The chat UI sits alongside Kdenlive first, embeds later

"A PyAgent UI chat inside the video editor" — taken completely literally —
means a panel compiled into Kdenlive's own window. That's real and buildable
(Phase 8), but it's also the most expensive, highest-maintenance piece here
(every Kdenlive upstream release means rebasing a C++ patch), and it adds
nothing to what PyAgent can *do* — only to how it *feels*. So the UI plan is:
a companion window/webapp next to Kdenlive first (Phase 4) — which already
gets you "I chat, it edits my project" — and a true embedded dock widget
later if you decide the project is worth that ongoing cost.

### 5.3 What's explicitly out of scope for this guide

- **Headless/CLI scripting of Kdenlive itself** — doesn't exist, not worth
  chasing.
- **GUI automation (`xdotool`/AT-SPI) as the primary control mechanism** —
  fragile (breaks on any UI change, needs pixel/element coordinates), and
  explicitly what D-Ogi's own design doc rules out too ("not driving the GUI
  like Selenium"). It appears in this guide only as a minor Phase 5/8
  fallback for a couple of things like "trigger a reload," never as how
  PyAgent performs actual edits.
- **Windows/macOS support** — everything here assumes Linux; see the note at
  the end of `00_START_HERE.md`.
