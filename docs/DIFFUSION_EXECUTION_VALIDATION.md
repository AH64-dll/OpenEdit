# Diffusion execution and acceptance — 2026-10-08

The integration builds on `b32c0ab918c62ce8ac7ee179441a984d57630be4` on
`feat/diffusion-authoring`. The implementation plan remains unchanged. All four
milestones are implemented; final cross-platform browser acceptance is in progress.

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

OMP contributed camera-reset and required upstream koota patch handling,
corrected group/sequence fixtures, asset-budget contracts and mirrored tool
instructions. Independent review checked those changes against pinned upstream
behavior. The installer now reproduces the upstream dependency patch exactly;
repeat installation and cross-trait-generation queries have direct coverage.
Groups derive their bounds from children; group box/fill props are rejected.
Sequence children have explicit timing instead of implicit stacking.

The complete local regression after review passed **1,501 tests**, with **18
skipped** because `melt` is unavailable and **4 browser tests deselected**, in
114.90 seconds. Subsequent encoder timeout/restart and concurrent compiler
checks passed in the **67-test** focused graphics/authoring/timing suite.
Ruff passes. A built wheel and source distribution contain all graphics/font/
patch/provenance resources and exclude node_modules and bytecode. A fresh wheel
installed outside the checkout exposes six tools and packaged skills with no
optional worker installed. Its explicit offline optional setup installs locked
dependencies, applies the exact upstream patch and runs both actual compilers.

[Acceptance run 37750205677](https://github.com/AH64-dll/OpenEdit/actions/runs/37750205677)
passed Linux browser/UI/timing/MLT replay and macOS compiler/browser/timing
checks. Windows identified CRLF conversion of pinned patch bytes; Git attributes
now preserve those sources as LF. Captured desktop graphics were reviewed;
mobile review exposed legacy rail overlap, now covered by layout/visibility
checks. Final acceptance is rerunning these fixes on all platforms.

Local tests use Python 3.12.13, Node 24.18.0 and the full FFmpeg in
`~/.local/bin` (the system FFmpeg lacks libx264). This execution sandbox blocks
socket wakeups and Chromium startup. An external, unshipped test helper bounds
selector polling for async tests; CI uses neither that helper nor local stubs.
Actual browser verification therefore runs in GitHub Actions.

The dedicated acceptance workflow exercises real compiler/source writeback on
Linux, Windows and macOS, browser render/cache/cancel/restart on all three,
Linux HTTP/UI/canvas flows and existing MLT/overlay/legacy replay fixtures.
FFmpeg is provisioned explicitly on each platform. Frame and UI captures are
uploaded as workflow artifacts even when an assertion fails.

## Performance and upgrade boundaries

The initial local benchmark measured a **663-byte** fresh-project authoring
summary, **902-byte** source response and **3,802-byte** six-tool schema;
compiler startup was **0.265 seconds** and graphics compilation **0.415 seconds**.
Peak child RSS was **163,412 KiB**: this is the largest completed child, not total
concurrent browser/process memory. The acceptance workflow also benchmarks
actual graphics render and cache reuse.

See [graphics usage and limits](DIFFUSION_GRAPHICS.md) and
[media authoring](DIFFUSION_AUTHORING.md). Runtime/browser/FFmpeg versions,
source and referenced CAS hashes enter cache identity. Existing graph databases
migrate source-view storage transactionally, projects can move without retaining
old preview paths, and unchanged source is a no-op. Dynamic JS/imports, remote
assets, arbitrary fonts and dynamic audio gain are rejected. Existing
HyperFrames and Remotion backends retain their own setup and replay behavior.
