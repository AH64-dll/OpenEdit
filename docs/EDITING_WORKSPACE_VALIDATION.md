# Editing workspace validation — 2026-10-08

All approved product recommendations are implemented on `feat/diffusion-authoring`.
The original Diffusion implementation plan is unchanged. The guide is
[EDITING_WORKSPACE.md](EDITING_WORKSPACE.md).

## Verified behavior

The real Chromium acceptance exercises Review/Graphics/Code navigation, shared
inspectors, setup guidance, source/property writeback, atomic Undo/Redo, preserved
comments, stale-draft protection, canvas placement, graphics QC/commit, responsive
layouts, automatic checked previews, chunk seeking, last-good playback, obsolete
job cancellation, empty-timeline clearing and mobile project switching. Review
mode does not load chat/WebSocket modules or request provider configuration.

The Linux render acceptance also executes fresh Remotion TSX with the independent
pinned compatibility package, pulls a real PNG frame, and replays existing MLT,
graphics, legacy and HyperFrames paths. Windows/macOS acceptance covers graphics
frames, cancellation/restart, source-time/audio and schema/history migration.
Main CI covers Python 3.11–3.13, lint, package builds and fresh wheel installation.

## Evidence and artifact locations

- Full local regression: **1,517 passed**, 18 skipped because local MLT/melt is
  absent, 5 browser tests deselected, in 115.93 seconds. An external sandbox
  socket-polling helper was used for local async tests; it is not shipped.
- Worker lifecycle/compiler checks after the completed-process cleanup guard:
  **19 passed**. Readiness and advanced HTML regression: **63 passed**.
- Main CI for the workspace implementation and shell correction:
  [37762161847](https://github.com/AH64-dll/OpenEdit/actions/runs/37762161847).
- Real browser, fresh Remotion TSX, frame pull, MLT, timing and HyperFrames
  acceptance for the shell correction:
  [37762161807](https://github.com/AH64-dll/OpenEdit/actions/runs/37762161807).
  The browser job passed. This push run exposed intermittent macOS EPERM when
  cleanup signalled an already-reaped worker group; the follow-up guard avoids
  signalling reaped PIDs and has a focused regression. The duplicate PR run
  passed macOS at the same earlier code revision.
- Current branch checks, including the cleanup and final SVG/mobile controls:
  [GitHub Actions](https://github.com/AH64-dll/OpenEdit/actions?query=branch%3Afeat%2Fdiffusion-authoring).
  Review the current-head checks when assessing these final follow-ups.
- Captures and benchmark are uploaded as `authoring-browser-captures`. Baseline
  inspected captures are also copied locally to
  `../validation-captures/product-workspace/`. Final control assertions verify
  real SVG bounds, mobile Setup visibility and compact transport rows.

A new wheel was installed from outside the source checkout and verified for
startup, optional-agent isolation, packaged UI/lockfiles/migrations, MCP skills
and durable history. No node_modules are bundled. Explicit media-worker setup
and actual JSX compilation passed from the installed wheel. Source and wheel
builds both succeed.

`dist/open_edit-1.4.0-py3-none-any.whl` SHA-256:
`51a13da31b82ccfe8681541799c0761528ec33f0785c149b5d445551d365be8d`

## Limits

Optional workers still require explicit setup and a working host/browser runtime.
Canvas dragging remains limited to direct, non-keyframed scene children;
nested/animated properties remain source-editable. Clip properties show the
first 50 clips and disable an unavailable selection; Code/MCP handles the full
supported document. Historical projects have no recoverable batch boundaries,
so pre-migration applied operations become individual actions. Legacy direct
status/reorder/delete APIs form a safe history barrier.
