# Phase 2 — Project Engine

## Context (recap)

This is the deterministic "hands" layer — the only part of PyAgent that
actually touches a project file. Same design philosophy your own
`mlt-pipeline` design spec states outright: *"Everything deterministic is
testable [code]. The AI's only job is..."* — here, the AI's only job is to
decide *what* edit to make; this phase's code is what actually makes it,
validates it, and can't be talked out of its own rules by a persuasive prompt.

Depends on Phase 0 (`manual_baseline.kdenlive` fixture, the reload-behavior
finding, the MLT-bindings-availability finding) and Phase 1 (the catalog, for
validating effect/transition names).

## Goal

A Python library — think of it as the spiritual successor to `internal/edl` +
`internal/mlt` from `mlt-pipeline`, but bidirectional (reads existing
projects, not just generates new ones) and Kdenlive-aware (emits real
`.kdenlive`, not bare `.mlt`) — that:

1. Parses an existing `.kdenlive` file into an in-memory model.
2. Exposes a small set of typed operations to modify that model.
3. Serializes back out to `.kdenlive`, preserving everything it doesn't
   understand (bin folders, notes, embedded layouts, anything Kdenlive added
   that this phase's code has no opinion about).

This is also the **backend-A implementation of the abstract operation
interface** described in `01_FINDINGS_AND_ARCHITECTURE.md` §5.1 — design it
as a class implementing a documented interface (`EditorBackend` or similar),
not as a pile of free functions, because Phase 7 will potentially write a
second implementation of the exact same interface against D-Bus, and Phase 3
should not need to change when that happens.

## Design decisions to make (informed by Phase 0's spike results)

- **XML library:** if Phase 0 found working MLT Python bindings, use them for
  constructing the MLT-standard parts (`Mlt::Producer`, `Mlt::Playlist`,
  `Mlt::Tractor`) — they're more robust than string templating. Either way,
  you'll still need direct XML handling (`lxml`, not stdlib `ElementTree` —
  it round-trips unknown elements/namespaces far more faithfully) for the
  `kdenlive:`-namespaced parts the bindings don't know exist. Don't let the
  bindings' ignorance of Kdenlive-specific data silently drop it on save —
  this is exactly the kind of bug a round-trip test (see below) is meant to
  catch.
- **Round-trip safety is the top priority.** A project a human spent an hour
  on must survive PyAgent opening and re-saving it with zero data loss on
  anything PyAgent didn't touch. This is more important than supporting every
  possible edit type — start narrow and correct, widen later.

## The operation API (minimum for v1 — matches Phase 1's Must-Have catalog shape)

- `get_project_info()` — fps, resolution, name, track list, as plain data
- `get_timeline_summary()` — every clip: track, start, end, source, transition
  at each edge (design this to render as a clean markdown table for Phase 3 —
  text, not a screenshot, matching the token-efficiency principle in the
  findings doc)
- `import_media(paths)` / `import_media_glob(pattern)`
- `insert_clip(track, position, source, in_point, out_point)`
- `append_clip(track, source, in_point, out_point)`
- `move_clip(clip_id, new_track, new_position)`
- `trim_clip(clip_id, new_in, new_out)`
- `delete_clip(clip_id)`
- `add_transition(clip_a_id, clip_b_id, type, duration)`
- `apply_effect(clip_id, effect_id, params)` — validate `effect_id`/`params`
  against Phase 1's catalog
- `add_marker(position, name, color)`
- `save(path)` / `load(path)`

## Validation pattern — reuse, don't reinvent

Port the `Validate` → `Clamp` two-step pattern from `internal/edl` directly:
a strict validation pass that rejects genuinely broken requests with a
`fix:`-prefixed hint (e.g. `fix: out_point must be <= clip duration (10.0s), got 12.0s`),
then a separate clamping pass for the boundary cases that are safe to just
correct and warn about. This is what let your existing pipeline's agent
self-correct without a human in the loop — same mechanism, same reason, now
serving PyAgent's tool-calling loop instead of a single batch prompt.

## Testing

- Golden-file tests: build a small project with the operation API, assert the
  output matches an expected `.kdenlive` (same spirit as
  `internal/mlt/generate_test.go`'s byte-match test).
- **Round-trip test using Phase 0's `manual_baseline.kdenlive`:** load it,
  make one small change via the operation API, save it, and assert every
  *other* piece of data (bin folders, the title clip, the marker, embedded
  layout if present) is byte-identical or semantically unchanged. This is the
  test that actually matters most — it's the difference between "PyAgent can
  write projects" and "PyAgent can safely edit a project you already care
  about."
- Reuse `testdata/clip_short.mp4` from `mlt-pipeline` as a fixture clip.

## Explicit non-goals for this phase

- No LLM calls anywhere in this phase — this is plain, deterministic,
  independently-testable code, same as your Go `internal/` packages.
- No chat UI, no D-Bus — this phase only knows how to read and write files.
- Don't try to support every effect/transition type on day one — implement
  the operation list above against a handful of common effects/transitions
  from Phase 1's catalog, prove round-trip safety, then widen coverage.

## Acceptance criteria

- [ ] Loads `manual_baseline.kdenlive`, re-saves with zero changes, output is
      semantically identical to input (whitespace/attribute-order
      differences are fine; missing data is not).
- [ ] Each operation in the list above has a passing unit test and a
      `fix:`-hinted rejection test for at least one invalid input.
- [ ] A project built entirely through this API, containing at least one
      clip, one transition, and one title, opens in the real Kdenlive GUI
      with its correct project name (not "Untitled") — this is the concrete
      check that the `kdenlive:` metadata gap from Phase 0's diff task has
      actually been closed.
- [ ] `effect_id`/transition-type arguments are rejected with a clear error
      if they're not present in Phase 1's catalog.

## Handoff to Phase 3

Phase 3's tool-calling loop calls this phase's operation API directly (as
`EditorBackend` — the file-based implementation). Nothing about Phase 3
should reference file paths or XML directly; that's this phase's job to hide.
