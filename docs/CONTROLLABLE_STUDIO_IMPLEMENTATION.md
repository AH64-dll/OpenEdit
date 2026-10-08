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

Still required: selective request revert and dependency UI, full timeline
interaction and track controls, effect-stack editing, keyframe/curve UI, audio
waveforms and controls, caption/style/font editing, full media-canvas marks,
built-in agent request grouping/context, custom export settings, immutable
snapshot publication to Desktop, fresh package/platform validation and the
complete S16 workflow. Keep all S01-S16 acceptance requirements open until their
current implementation and runtime evidence are complete.
