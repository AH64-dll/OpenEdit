# Diffusion Studio integration assessment

## Decision

Diffusion Studio's compiler and source writer are reusable. The best fit for
OpenEdit is an **optional JSX authoring adapter**, followed by an optional
browser render worker for graphics that cannot be represented by existing IR.
OpenEdit's SQLite operation graph should remain the authoritative edit record.
The first media-authoring milestone is implemented through MCP, with a pinned
compiler/source-writer worker and revision-checked IR commits. It does not
replace OpenEdit's renderer or add a Diffusion graphics backend. See the
[authoring guide](DIFFUSION_AUTHORING.md) and
[remaining implementation plan](DIFFUSION_IMPLEMENTATION_PLAN.md).

Reviewed upstream commit: [`fefcde9df7198466bd7cc9f3a9d7eae1575b5b12`](https://github.com/diffusionstudio/editor/tree/fefcde9df7198466bd7cc9f3a9d7eae1575b5b12).
The root package reports version `0.209.1`; its JSX package reports `0.207.0`.
These are the inspected source versions, not a promise of npm availability.

## What the compiler actually does

The project source is a SolidJS/JSX component. It declares a `<stage>` and
`<scene>` containing video, audio, text, shapes and other elements. The editor
can update that source after a person changes the canvas or timeline.

The implementation has four distinct stages:

1. `apps/desktop/src/edit.ts` stamps durable element IDs. Its `applyEdits`
   uses TypeScript ASTs through `ts-morph` to change props, insert/remove/move
   elements, and write changes atomically.
2. `apps/desktop/src/source.ts` adds source locations and normalizes composition
   tags. `projects.ts` applies these Babel plugins, the Solid universal JSX
   preset and the TypeScript preset, then bundles browser-targeted CommonJS
   with esbuild. TypeScript types are stripped; compilation is not typechecking.
3. `packages/reconciler` evaluates the bundle and reconciles its element tree
   into runtime entities through a Solid universal renderer. Source stamps
   connect each entity to the JSX that created it.
4. `packages/runtime` maintains scenes and media state; `packages/encoder`
   exports through Mediabunny using a browser-grade canvas/audio context.

The special capability is bidirectional source editing. The compiler does not
turn arbitrary rendered video into source, and it does not compile JSX into
OpenEdit's operation graph or into an MLT timeline.

## Reuse opportunities

| Upstream component | Useful role in OpenEdit | Work required |
|---|---|---|
| `source.ts`, `edit.ts`, `atomic.ts` | Trace an editable scene node back to code; update source precisely | Isolate these unchanged modules behind a small Node worker; preserve MPL notices |
| `packages/jsx` | Declarative, typed agent authoring API | Map supported media props and IDs to OpenEdit clips/assets |
| `packages/reconciler` | Mount compiled JSX into a scene model | Implement a host boundary and validate supported scene changes before committing IR |
| `packages/runtime`, `packages/encoder` | Rich text, shapes, masks, animation and browser exports | Separate browser worker; media/effect parity, codecs, cancellation and caching |
| `packages/dapi` | One validated tool catalog for CLI and MCP | Borrow the design; OpenEdit already has a common registry and six MCP tools |

The authoring and write-back modules offer the highest value with the smallest
change to the current engine. Vendoring the whole Electron editor would add a
second project store, renderer, UI and dependency tree to maintain.

## Executed proof of reuse

The evaluation used upstream `edit.ts` and `source.ts` without altering their
source. They were bundled for an isolated Node test with these versions from
upstream's lockfile:

- Babel core / TypeScript preset `7.29.7`
- Solid preset `1.9.12`
- esbuild `0.28.1`
- ts-morph `28.0.0`

A fixture declared one scene, a video `id="clip1"` and a title `id="title1"`.
`stampProject` ran, then `applyEdits` changed the video start to 3 seconds,
source in/out to 2/7 seconds, and the title's text. Both writes succeeded with
no skipped edits. Recompilation retained `index.tsx:clip1` in the source map and
produced CommonJS without JSX. This verifies the compiler/write-back seam.

No footage was rendered in this experiment. It does not establish browser,
audio, export, effect or OpenEdit IR round-trip parity.

The reproducible harness is in `research/diffusion-compiler/`. It bundles the
reviewed upstream modules without modifying the checkout, edits a temporary
fixture, checks compilation and removes its generated files. It is independent
of OpenEdit's installed dependencies and MCP startup. To repeat it:

```bash
git clone https://github.com/diffusionstudio/editor.git /tmp/diffusion-editor
git -C /tmp/diffusion-editor checkout fefcde9df7198466bd7cc9f3a9d7eae1575b5b12
cd research/diffusion-compiler
npm ci --ignore-scripts --no-audit --no-fund
node check.cjs /tmp/diffusion-editor
```

## Implemented media adapter contract

The adapter retains the existing six MCP tools:

- `query_project/get_authoring_view` returns compact metadata, a graph revision
  and a feature list. JSX is returned only with `include_source=true`. Clips
  are flat media elements with stable URL-escaped IDs inside track groups.
- `edit_project/apply_authoring_edit` accepts full literal source or native
  source edits plus `expected_revision`. It translates the result into existing
  IR operations and commits once with `append_many(expected_revision=...)`.
- The compiler and AST writer run in a separate bounded Node process. The
  initial adapter rejects executable project statements and expressions,
  disables project Babel configuration and never evaluates project JavaScript.
  Reconciler evaluation belongs to a later graphics worker.
- Source is regenerated from the committed graph on read, including after
  other editors mutate it. Concurrent edits are rejected, including edits that
  become stale during compilation. Persistent source formatting and visual UI
  synchronization remain later work.

| JSX property | OpenEdit representation | Initial boundary |
|---|---|---|
| Stable element `id` | `clip_id` / operation identity | Preserve through move, trim and reload |
| `src` | CAS asset hash plus explicit source mapping | Resolve through the pinned project's asset store |
| `start` | `position_sec` / `MoveClipOp` | Preserve seconds and track assignment |
| `sourceIn`, `sourceOut` | Clip in/out points / `TrimClipOp` | Validate ranges before appending |
| `playbackRate` | Future `ChangeClipSpeedOp` mapping | Currently require 1; OpenEdit's speed effect and Diffusion's duration semantics differ |
| Audio `volume` | Delta `SetAudioGainOp` | JSX is absolute dB; OpenEdit appends cumulative gain effects, so apply the difference |
| Text, shapes, shaders, masks | Optional materialized graphics asset | Require a browser worker; do not silently drop unsupported content |

OpenEdit can already accept Python-generated IR through `run_script` and
structured edits through `edit_project`. The adapter's additional value is an
editable code view with atomic, revision-checked updates. Visual editing through
that contract is future work.

## Remaining checks before expanding it

1. Media assets, fixed track order, trims, still images and constant gain now
   have real compiler/IR/MCP round-trip tests. Extend these to playback rates,
   dynamic gain and richer JSX only after establishing their semantics.
2. Confirm frame/audio parity for representative OpenEdit projects, including
   overlays and transitions. Existing HyperFrames and Remotion operations must
   remain replayable.
3. Stale revisions, concurrent snapshot reads, multi-element edits, rollback,
   malformed source and worker timeout/restart are tested. Extend lifecycle
   checks to last-good browser previews and rendering cancellation.
4. Verify project path boundaries and graphics materialization before adding
   executable components or browser workers.
5. The compiler worker is pinned and packaged reproducibly. The inspected
   runtime/reconciler packages expose TypeScript source from their workspaces;
   do not assume they are independently supported production npm libraries.
6. Keep source and render details on demand so the integration does not add
   large JSX documents or duplicate graphs to every MCP call.

## License and distribution

The inspected editor, compiler, source writer and JSX/runtime packages are
MPL-2.0, while OpenEdit is MIT. Mozilla describes MPL's boundary as file-level
copyleft: distributed files containing MPL code, including modifications,
retain MPL obligations. Independent OpenEdit adapter files can remain under
OpenEdit's license. Do not copy the compiler into MIT files and remove notices.

For a vendored worker, preserve upstream headers and license, identify the
pinned source, publish the covered source/modifications and include the
required distribution notices. Upstream desktop brand assets are expressly
excluded from its open-source license; the adapter needs none of them.
The optional worker vendors unchanged compiler/source-writer and JSX helper
files, retaining their original headers, full MPL license and pinned provenance
in `open_edit/integrations/diffusion/worker/NOTICE.md`. Python adapter and worker
host files are independently written MIT code. No brand assets are included.

Primary references:

- [Repository and README](https://github.com/diffusionstudio/editor)
- [Compiler and project host](https://github.com/diffusionstudio/editor/blob/fefcde9df7198466bd7cc9f3a9d7eae1575b5b12/apps/desktop/src/projects.ts)
- [AST source writer](https://github.com/diffusionstudio/editor/blob/fefcde9df7198466bd7cc9f3a9d7eae1575b5b12/apps/desktop/src/edit.ts)
- [Source mapping plugins](https://github.com/diffusionstudio/editor/blob/fefcde9df7198466bd7cc9f3a9d7eae1575b5b12/apps/desktop/src/source.ts)
- [Reconciler](https://github.com/diffusionstudio/editor/tree/fefcde9df7198466bd7cc9f3a9d7eae1575b5b12/packages/reconciler)
- [Encoder runtime requirements](https://github.com/diffusionstudio/editor/blob/fefcde9df7198466bd7cc9f3a9d7eae1575b5b12/packages/encoder/package.json)
- [MPL-2.0 license](https://github.com/diffusionstudio/editor/blob/fefcde9df7198466bd7cc9f3a9d7eae1575b5b12/LICENSE)
- [Mozilla MPL FAQ](https://www.mozilla.org/en-US/MPL/2.0/FAQ/)
