# Controllable studio implementation

This implements the user-approved source-preserving editor plan. The original
Diffusion implementation plan remains unchanged. Imported footage remains local
media; editable instructions, graphics and animation retain their source.

## Acceptance requirements

- S01: Versioned editable documents, stable object IDs, source preservation and
  atomic, revision-checked changes shared by manual and AI callers.
- S02: Durable Undo/Redo, request grouping and selective AI revert with explicit
  conflicts/dependencies; no loss of unrelated later work.
- S03: Desktop-first resizable studio with canvas, library/layers, contextual
  inspector, timeline, AI panel and advanced Code view; responsive drawers.
- S04: Shared selection, nested/animated hit testing and direct manipulation;
  numeric properties, align/distribute, grouping, ordering, visibility and locks.
- S05: Rectangle selection and separate AI marks: arrows, rectangles, freehand,
  notes and pins. Marks carry object IDs, composition coordinates and timing;
  remain editable/undoable and are excluded from exports.
- S06: AI targeting/context and request summaries for built-in and external MCP
  agents, preserving the six public tools. Manual editing needs no provider.
- S07: Timeline dragging, trimming, splitting, duplication, normal/ripple delete,
  compatible tracks, ordering, thumbnails and mute/solo.
- S08: Stable-ID effect stacks, parameter controls, bypass/reorder/reset/duplicate/
  delete and transitions, driven by shared capabilities.
- S09: Keyframe tracks, easing and Bezier editing; auto-key off; base-placement
  changes preserve animation. Preview/export use one curve evaluator.
- S10: Cached waveforms, gain/fades/pan/EQ and track controls.
- S11: Editable captions, text/style/timing, split/merge, SRT import/export and
  existing optional transcription; reusable editable styles and project fonts.
- S12: Interactive graphics, checked asynchronous media previews, explicit
  quality/status, selected-range full-quality check and obsolete-result guards.
- S13: Export always opens settings: presets/custom, filename/folder, full/range,
  geometry/aspect/FPS, supported codec/container, quality/bitrate/speed/encoder,
  audio and caption options. Defaults follow the project, MP4/H264/Auto/SDR709.
- S14: Export an immutable snapshot, verify the result, publish atomically to
  the OS Desktop by default; unique names, visible path, Play/Open folder.
- S15: Preserve legacy projects/backends and source comments, package all new
  resources, and test fresh installations and Linux/macOS/Windows behavior.
- S16: Real browser interaction, reviewed captures and complete import -> AI edit
  -> manual edit -> marked refinement -> selective revert -> reopen -> export.

## Delivery sequence

1. Persistent documents, history and source round-tripping (S01, S02 foundation).
2. Studio shell, direct editing, selection and annotations (S03-S05).
3. Timeline, effects, animation and preview integration (S07-S09, S12).
4. Audio, captions and AI/history integration (S02, S06, S10-S11).
5. Configurable local export and complete acceptance (S13-S16).

## Implementation evidence

Work is in progress. A successful build or earlier branch CI is not acceptance
of these requirements. Record completed contracts and their verification here;
leave requirements open until current implementation/runtime evidence proves
them. No video-understanding, tracking or footage-reconstruction model is in scope.

Foundation checkpoint (not full-plan acceptance): migration 8 stores versioned
documents and annotations in the same atomic actions as render operations.
Manual/AI writes share revision checks, locks and durable Undo/Redo. Graphics
remain source-backed through clip moves, trims, effects and materialization.
The literal source writer supports text, properties, hierarchy, duplication and
whole-motion-path translation without erasing position keyframes.

The studio adds a live graphics runtime, nested transformed selection, property
editing, layer hierarchy/visibility/locks, selection boxes and object-relative
AI marks. Panel sizes persist with pointer and keyboard controls. External MCP
agents can read the current workspace selection and its structured context.
An optional full-quality graphics check keeps its last good result and rejects
obsolete results. Browser acceptance now checks exact live/export frame parity,
manual/AI writes, marks, locks, Undo/Redo and reopen, plus real MLT rendering of
source-backed clips. These new browser checks are pending CI execution.

Local evidence: 288 focused storage/IR/history/graphics checks passed, followed
by a complete run of 1562 passed, 18 MLT-dependent skips and 6 browser tests
deselected. Compatibility updates cover migration expectations, additive
timeline fixture fields and script-bootstrap operation definitions. Another
23 API/source checks passed, including live compiler, font/runtime resources
and shared workspace selection. Ruff passed. The current wheel builds and
contains the migration, browser runtime and studio UI resources.
Local Chromium is blocked by the process sandbox and MLT is not installed, so
local unit tests do not establish browser/export acceptance.

Request-history implementation now adds migration 9, contiguous AI-tool grouping,
semantic three-way source/property inversion, audited operation-status deltas,
and reversible selective request actions. Later unrelated properties and source
comments survive; conflicting properties, source ownership, locked layers,
dependent clips and linked marks produce an explicit report. Built-in AI turns
receive the same structured selection/source/marks as external MCP agents, and
History offers request revert with a dependency report. Focused regression checks
are passing; complete regression and actual browser acceptance are in progress.

Timeline/effect checkpoint in progress: stable IR operations now name, reorder,
mute/solo/hide/lock tracks and clips; duplicate clips with independent effect IDs;
and update, bypass, reorder, reset, copy or remove effects by stable ID. The UI
adds pointer dragging and trim handles, multi-selection, splitting, duplication,
normal/ripple deletion, track buttons and catalog-driven effect forms. The script
bootstrap exposes these controls too. Source-duration and compatible-track
validation share the revision-checked commit path, preserving atomic history.

Rendering now preserves upper-layer source-in offsets and stacking, keeps upper
video audio in the mix, and caches checked alpha layer passes for upper effects.
Solo state survives preview-range slicing; disabled effects are excluded from
emission. Linear volume converts to the MLT decibel level property. A canvas
selection bug was fixed by reading stable Source metadata instead of removed
runtime id props. New browser tests exercise actual drag/trim/effect controls;
actual render acceptance checks trimmed upper media, effect bypass, hidden
pictures and audio. These checks await the next CI run. Local compatibility
regressions passed (234 tests, one MLT skip); the full rerun passed with 1592
tests, 18 MLT skips and 7 browser tests deselected. Linux/macOS/Windows compiler
jobs and Python 3.11/3.12 regression, wheel and installation jobs passed at
8848db0. Actual source-backed MLT export passed; upper-layer pixel checks passed
before an invalid test time argument stopped audio acceptance. That argument is
corrected in the next checkpoint. Canvas interaction acceptance exposed direct
matrix slots being read as attached traits; the interactive adapter now reads
the same derived matrix store used by the renderer.

Animation and media-visual checkpoint: source-backed keyframe tracks have
add/update/delete/time movement, named easing and draggable/numeric Bezier
handles, editable animation presets, and explicit auto-key off by default.
Auto-key uses evaluated local time/coordinates, retains an initial base value,
and ordinary translation preserves the complete motion path. Preview/export
share the pinned runtime curve evaluator. Ambiguous tracks, duplicate times and
invalid values/curves are rejected. Real browser acceptance now exercises these
controls and checks eased pixel/geometry parity. Source assets get six cached
filmstrip images and bounded waveform envelopes, reused without another decode;
visible timeline clips request them lazily. Focused compiler/source/cache checks
passed (55 tests); complete regression and browser acceptance are in progress.

Export checkpoint: Export opens a configurable settings dialog with project
presets/custom dimensions and rational FPS, filename/folder, full/range,
container/codec, quality/CRF/bitrate, speed/encoder and audio settings. Export jobs
capture the database and immutable media before rendering; later edits cannot
alter that revision. Destination files undergo metadata and complete decode
checks before atomic publication under a unique name, with a visible path and
Play/Open folder actions. Desktop defaults respect Windows redirection and XDG.
Actual FFmpeg publication and snapshot/API tests passed locally (39 focused
checks). Real MLT range export and complete browser export acceptance are added
to CI and remain pending. Caption inclusion becomes effective with S11.

At 0966551, current Python regression/package CI and Linux/macOS compiler jobs
passed. Actual upper-layer MLT rendering, effect bypass, trim offsets and audio
controls passed. Browser acceptance identified string-root asset validation and
seek-dependent nested bounds; this checkpoint normalizes paths and settles
geometry before both interactive and checked rendering. Browser proof is still
pending. Queue and encoder advisory locks are separate, preserving immediate
coalescing while a proxy encoder is running; 61 focused preview/job checks passed.

Caption/audio checkpoint in progress: caption objects now compile to durable
render operations, share manual/AI history and semantic request revert, and
retain text, timing, visibility, locks and editable style properties. SRT
interchange, clip-trim-aware transcript conversion, optional local transcription,
project font import and reusable style editing are available. Cached transparent
caption rasters are shared by preview chunks and final rendering; export can
exclude captions. The caption editor includes timing/style changes and split/
merge. Shared effect controls add parameter keyframes (including track effects)
and clip audio fades. Stereo pan is translated to MLT's 0..1 balance range and
EQ uses avfilter.equalizer's actual property names. Actual MLT audio tests are
added to CI. Focused caption/history/preview regressions passed (78 checks),
including real FFmpeg caption timing and imported font rasterization.

At 4a4928d, interactive/export nested animation pixel parity and backwards seek
determinism passed, as did actual immutable selected-range MLT export. Linux and
macOS compiler/export tests passed. Windows identified unclosed SQLite backup
handles and read-only fsync; both are corrected. Browser interaction advanced to
an ambiguous test selector and subpixel rounding mismatch, also corrected. Full
local regression at that checkpoint passed: 1632 tests, 18 MLT skips, 8 browser
tests deselected. Full new browser interaction and reviewed UI acceptance remain
pending; the library is now visible by default when using external MCP too.

Media/transition/range-check checkpoint: video preview annotations support
arrows, boxes, freehand, pins and notes with editable points, timing, color,
visibility and locks. Region selection remains separate. Manual and AI marks
share durable history and context. Explicit conversion creates an independent
editable JSX graphics document; keeping/deleting the mark does not affect the
graphic. Real compiler round-trips passed for every mark type.

New visual transitions retain the original trims and cut; their boundary
frames freeze where no extra trimmed footage is available. Type, duration,
bypass and removal are editable. Existing transition operations retain legacy
replay semantics. Cached alpha transitions respect effects, layering and
selected-range offsets. Actual FFmpeg crossfade/wipe pixel checks pass;
actual MLT transition acceptance is added to CI. Audio uses its own fades.

Full-quality range checks now use original media and immutable source snapshots,
at project geometry/FPS, and remain in the project cache. The UI presents the
verified check and explicitly marks it outdated after later edits. Local export
API checks pass (21 checks). The clip inspector now exposes timing alongside
its effects; advanced source controls stay in Code. Library tabs fit the panel.

At 3ead7c3, all three compiler/platform jobs passed, including Windows cleanup,
caption/font rasterization and audio parameter validation. Full local regression
passed with 1640 tests, 18 MLT-dependent skips and 9 browser tests deselected.
Actual immutable MLT range export and interactive/export graphics parity passed.
Browser CI exposed a timeline repaint race in the test and an ignored EQ in
MLT; the repaint wait is corrected and detailed EQ renderer diagnostics are
added. These remain pending current runtime acceptance.

Stabilization checkpoint (after df20cea): the three remaining CI failures are
addressed. media-marks.js was loaded twice (a versioned script tag plus module
imports), duplicating the annotation toolbar, overlay and inspector; it now loads
once. Windows graphics scratch directories tolerate a briefly locked Chromium
profile and stale ones are swept. MLT before 7.28 silently drops audio avfilter
filters (upstream mlt 615aac5), so EQ is now reported by readiness, warned about
in render and export results, and its actual-MLT assertion is version-gated.

Running the complete studio workflow exposed further editor defects, now fixed:
inspector panels (marks, captions, animation, clip/track, graphics layers)
discarded typed values on background refreshes; Undo/Redo used a stale history
revision immediately after an edit; a stale compile failure in the graphics
editor dropped the queued Undo snapshot; Enter in animation forms reloaded the
page. Exports remain untagged: tagging BT.709 fixed MLT 7.41 output but shifted
MLT 7.22 output, so melt's raw-pipe matrix differs by version; pure-color pixel
checks on MLT 7.41 stay below thresholds tuned on 7.22 (open item). UI polish: friendly mark labels, styled
inspector forms and selects, one labelled preview toolbar, a sticky export
footer with a settings summary and warnings, graphics and captions empty states.

Local evidence with MLT 7.41 and Playwright Chromium: tests/browser/studio.cjs
passes end to end for the first time (manual/AI edits, locks, video and graphics
marks, conversion, transitions, captions, history, request revert, reopen and
exact interactive/export pixels), as does authoring.cjs. Full regression: 1672
passed. Browser/MLT pytest suites pass. CI on Linux/macOS/Windows and MLT 7.22
remains to confirm these results.

Still required: CI confirmation of the local browser results above (request
revert now passes locally), complete timeline
interaction and track controls, effect-stack editing, keyframe/curve UI, audio
waveforms and controls, caption/style/font editing, full media-canvas marks,
custom export settings, immutable
snapshot publication to Desktop, fresh package/platform validation and the
complete S16 workflow. Keep all S01-S16 acceptance requirements open until their
current implementation and runtime evidence are complete.
