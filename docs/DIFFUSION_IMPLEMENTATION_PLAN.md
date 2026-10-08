# Diffusion integration implementation plan

OpenEdit's SQLite operation graph remains authoritative. Diffusion supplies an
optional editable JSX view and, in a later phase, a graphics renderer. Existing
Python scripts and media rendering continue to work without Node dependencies.

## Execution checkpoint — 2026-10-08

| Work | Status | Next dependency |
|---|---|---|
| Revision-safe literal media JSX and MCP commands | Implemented | Regression and distribution checks recorded in validation report |
| Pinned compiler/source writer, optional setup and packaging | Implemented | Cross-platform lifecycle coverage before broad rollout |
| Persistent source formatting and visual writeback | Planned | Browser/visual host and revision-aware source ownership |
| Browser graphics, CAS materialization and preview lifecycle | Planned | Pinned browser worker plus actual frame/encode tests |
| Speed/audio/compositing parity and UI integration | Planned | Golden fixtures before enabling each expanded feature |

Execute in this order. The initial release can edit supported media through
MCP; the browser renderer and visual UI each require their own acceptance gate.
See [usage](DIFFUSION_AUTHORING.md) and
[validation](DIFFUSION_AUTHORING_VALIDATION.md) for the delivered boundary.

## Milestone 1: revision-safe authoring through MCP

- Export a flat JSX document with stable IDs for tracks and clips; resolve
  media through the project CAS. Return a compact summary unless source is
  explicitly requested.
- Accept literal JSX or source-property edits, parse and compile in a bounded
  Node worker, translate changes into IR, and append the entire batch once.
- Support video, audio and still images; add/remove, move, trim, source
  replacement and constant audio volume. Preserve existing graph features that
  have no representation in this initial view.
- Use Diffusion's actual `volume` prop (decibels). Apply volume changes as the
  difference from existing cumulative clip gain, because OpenEdit's gain ops
  accumulate.
- Reject non-unity playback rates and dynamic/keyframed gain changes until
  timing/audio parity is established. OpenEdit currently stores speed as an
  effect without retiming clip endpoints; Diffusion retimes source duration.
- Reject stale revisions, unsupported JSX, unknown assets, duplicate IDs,
  track reordering and mismatched media/track kinds without changing the graph.
- An unchanged document is a no-op, including no revision increment, while a
  stale unchanged document still fails.

Acceptance: real Node parsing/compiler/source-writeback tests; atomic rollback;
concurrent export consistency; stale edits; unchanged source; effect and
legacy-overlay preservation; actual stdio MCP round trip with six tools.

## Milestone 2: compiler packaging and source synchronization

- Vendor only pinned compiler/source-writer dependencies, retaining MPL files,
  license and provenance; keep the Python integration MIT.
- Pin Node dependencies in their own lockfile. Run only when authoring is
  requested; impose input/output and time limits; clean temporary writes.
- Route visual changes through the same revision-checked adapter. Persist
  source views keyed by revision only after successful graph commit; refresh
  from the graph after other editors mutate it.
- Include worker code in the wheel and source distribution without installed
  node_modules. Provide explicit optional setup and actionable missing-worker
  errors. CI installs the worker and exercises it independently of Chromium.

Acceptance: clean install, compiler diagnostics, worker timeout/crash/restart,
last-good source preservation and deterministic source identities.

## Milestone 3: graphics worker and preview lifecycle

- Pin and package the reconciler/runtime/encoder in a separate browser worker.
  Start with text, shapes and basic animations; define unsupported features.
- Resolve asset URLs through the pinned project; materialize graphics into CAS
  with content-addressed keys and provenance. Keep existing render backends.
- Connect managed cancellation/restart and cached last-good previews to the
  durable render service. Add visuals to IR only after successful output/QC.

Acceptance: actual browser frame stepping and encode; representative text and
shape clips; audio/alpha behavior; cache invalidation; no partial graph mutation
on compile/render failure; cancellation reaps browser/encoder children.

## Milestone 4: parity and rollout

- Establish frame/source-time/audio parity for trims and playback rates,
  including source-in offsets, still images, speed ramps and mixed frame rates.
- Verify compositing order, masks, transitions and replay of legacy HyperFrames
  and Remotion projects. Expand feature mappings only after passing examples.
- Add UI code/canvas synchronization through the same MCP/IR adapter; surface
  stale edit conflicts without replacing another editor's work.
- Benchmark tool payload sizes, startup, compilation and render memory; enable
  integrations only on demand and document upgrade/migration behavior.

Acceptance: golden frame/audio checks against pinned fixtures, cross-platform
worker lifecycle, review UI edits, reproducible package installation and bounded
MCP instructions/results.

The initial implementation targets milestones 1 and the compiler portion of 2.
Browser graphics and visual UI integration require their own tested release;
they must not be represented as available before those acceptance checks pass.
