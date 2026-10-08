# Diffusion execution and acceptance — 2026-10-08

The integration builds on `b32c0ab918c62ce8ac7ee179441a984d57630be4` on
`feat/diffusion-authoring`. The implementation plan remains unchanged. All four
milestones are implemented for the supported literal-JSX vocabulary, with
cross-platform browser acceptance complete. Code acceptance below is for
`40bbfb5d1052eab499d6052cf6c5dbeedb789c5e`; this report is a documentation follow-up.

| Milestone | Delivered and verified |
|---|---|
| 1: revision-safe authoring | CAS media JSX, atomic batches, stale/no-op checks, six-tool MCP round trips |
| 2: packaging and synchronization | Pinned compiler, revision-owned formatting, source/property writeback, optional clean installation |
| 3: graphics and preview lifecycle | Actual Chromium frames, alpha CAS encode/QC, cache, cancellation/restart, explicit graph commit |
| 4: parity and rollout | Frame/audio fixtures, source-time retiming, legacy replay checks, HTTP/UI/canvas editing, platform CI and benchmarks |

## Delivered behavior

- Literal media JSX supports stable CAS references, media add/remove, move,
  trim, replacement, cumulative-gain-aware absolute dB volume and constant
  playback rates. SQLite operations remain authoritative; accepted source and
  its entire operation batch commit together at the expected graph revision.
  Formatting-only changes save without incrementing the revision. The last
  eight accepted source revisions are retained.
- Optional, separately locked Node compiler and browser workers use pinned
  upstream sources. Ordinary Python editing starts neither worker. Input,
  output, time, scene, asset and frame budgets bound authoring/rendering work.
  Wheels include source, locks, provenance and licenses, excluding node_modules
  and downloaded browsers.
- The graphics worker captures text, shapes, keyframes, preset animations,
  project CAS images, masks, compositing order and sequence transitions in
  Chromium. It creates silent RGBA CAS video, browser preview and poster only
  after successful render/decode/duration/alpha checks. Durable jobs support
  cancellation, restart, checked cache reuse and last-good preview preservation.
  Adding or updating a timeline clip requires an explicit revision-checked
  commit of a succeeded job.
- Review Studio provides media JSX/property editing and graphics source,
  preview, layer properties and canvas dragging. Both use the same kernel
  adapters as MCP. A stale revision retains drafts and requires reload; another
  editor's operations are never silently overwritten.
- Constant-rate and piecewise-rate CAS baking preserves source-in offsets,
  still-image timing and audio pitch. Fixtures cover 24 and 30000/1001 fps,
  video with audio, audio-only and transparent stills. Existing speed/speed-ramp
  operations keep their prior replay semantics; arbitrary interpolated legacy
  ramps are not converted automatically to the piecewise source-time format.

## Review and acceptance

OMP contributed the camera reset, required upstream koota patch, corrected
group/sequence fixtures, asset-budget contracts, Windows provisioning retries
and mirrored tool instructions. Review checked those changes against pinned
upstream behavior and corrected installer equivalence, CRLF handling, process
publication and UI property assumptions. The installer reproduces the upstream
dependency patch byte for byte; repeat installation and cross-trait-generation
queries have direct coverage. Groups derive their bounds from children;
group box/fill props are rejected. Sequence children have explicit timing.

The complete local regression passed **1,504 tests**, with **18 skipped** because
`melt` is unavailable and **4 browser tests deselected**, in 117.09 seconds.
Ruff passes. [Main CI](https://github.com/AH64-dll/OpenEdit/actions/runs/37753489646)
passes on Python **3.11, 3.12 and 3.13**, including lint, regression tests,
distribution builds, a fresh default-wheel MCP/skills check and explicit
optional setup with both actual compilers. The Python 3.12 CI regression is
**1,497 passed, 25 skipped, 4 deselected**; browser and render dependencies are
exercised separately in the acceptance jobs below.

[Diffusion acceptance](https://github.com/AH64-dll/OpenEdit/actions/runs/37753489551)
is green on **Linux, Windows and macOS**:

- Each platform passes the real compiler/graphics contracts and authoring/API/
  migration tests (21 plus 43 tests). Windows and macOS each additionally pass
  three real browser lifecycle/golden tests and eight timing/audio tests.
- Linux passes three real browser tests, the HTTP/UI source/property/canvas
  flow, eight timing tests, eight existing render/legacy replay tests, and an
  actual HyperFrames browser plus FFmpeg composition test. The UI flow checks
  loaded source video, source writeback, a canvas drag, preview/QC, explicit
  timeline commit, stale draft retention and responsive layout.
- Golden frames check text/font rendering, animation positions, image CAS,
  compositing order, rectangular masks and sequence transitions. Graphics
  clips are committed and rendered through actual MLT. Screenshot review
  exposed MLT's inherited PAL pixel aspect; explicit square-pixel consumer
  settings now preserve the source geometry, checked by frame position.
- Actual HyperFrames replay checks a red HTML overlay over blue footage with
  preserved audio. Remotion compatibility uses a deterministic CLI fixture
  feeding real media through materialization/proxy/MLT replay; it does not
  establish fresh TSX execution by the Remotion renderer.

Desktop/mobile captures and exported MLT/HyperFrames frames from that run were
visually reviewed. Mobile rails no longer cover the editor. Group-derived sizes
and animated properties cannot be replaced accidentally through numeric UI
controls; animated source remains editable as JSX. Direct scene children can
be dragged; nested layers use parent-relative property/source editing.

The wheel and source distribution include graphics/font/patch/provenance
resources and exclude node_modules and bytecode. Every packaged Python/resource
file in the final local wheel matches the checkout. The **1.4.0** wheel SHA-256
is `1597f91c80b1b7bd00823b08e98048fdd9bae1bc1e1bad83015563ac4ed2eaad`.
An independently installed wheel outside the checkout exposes six tools and
packaged skills without optional workers; explicit offline optional setup
installs locked dependencies, applies the patch and runs the compilers.

Local tests use Python 3.12.13, Node 24.18.0 and the full FFmpeg in
`~/.local/bin` (the system FFmpeg lacks libx264). This execution sandbox blocks
socket wakeups and Chromium startup. An external, unshipped test helper bounds
selector polling for async tests; CI uses neither that helper nor local stubs.
Actual browser verification therefore runs in GitHub Actions.

Browser cancellation/restart passes on all three platforms. Separate tests
exercise a real FFmpeg encoder timeout/reap/restart and simultaneous successful/
failed compiler requests. These checks cover worker cleanup, cache invalidation,
last-good previews and failures without partial graph mutation. FFmpeg is
provisioned explicitly on every platform. Frames and UI captures are available
in the acceptance run's artifacts.

## Performance and upgrade boundaries

The accepted Linux run used Python 3.12.14, Node 24.21.0 and Chromium
148.0.7778.96. Its reproducible `benchmark.json` records:

| Measurement | Result |
|---|---:|
| Fresh-project media summary / source | 663 / 902 bytes |
| Graphics summary / six-tool schema | 125 / 3,802 bytes |
| Compiler cold / five-run median | 0.366 / 0.365 seconds |
| Graphics compilation | 0.667 seconds |
| 15-frame graphics render / checked cache hit | 3.557 / 0.822 seconds |
| Largest completed child RSS | 256,640 KiB |
| Sampled host plus descendants RSS sum | 1,780,368 KiB |

The process-tree figure samples every 100 ms and counts shared pages once per
process; it is not unique physical memory. The child figure is not aggregate
memory. These are fixture measurements on a CI runner, not performance limits.

See [graphics usage and limits](DIFFUSION_GRAPHICS.md) and
[media authoring](DIFFUSION_AUTHORING.md). Runtime/browser/FFmpeg versions,
source and referenced CAS hashes enter cache identity. Existing graph databases
migrate source-view storage transactionally, projects can move without retaining
old preview paths, and unchanged source is a no-op. Dynamic JS/imports, remote
assets, arbitrary fonts and dynamic audio gain are rejected. Timing ramps use
explicit piecewise-constant segments; arbitrary interpolated legacy ramps
retain their original operations. Graphics exports are silent, with sound on
ordinary media tracks. Existing HyperFrames and Remotion backends retain their
own setup and replay behavior.
