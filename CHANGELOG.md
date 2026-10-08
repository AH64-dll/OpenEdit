# Changelog

All notable changes are tagged on GitHub. See
https://github.com/AH64-dll/OpenEdit/releases for downloads.

## Unreleased

- Remove the Pi extension, bridge and provider. MCP is included in the default
  package; built-in chat SDKs remain optional and the UI defaults to review mode.
- Remove generated graph indexes, task scratch files, UI backups and personal
  launchers/configuration. Clean imports and static-analysis failures.
- Load detailed guides on demand; page asset/transcript reads and return compact
  render polling results, with full diagnostics available explicitly.
- Validate tool enums, nested numbers and exclusive edit modes. Report MCP
  errors using the protocol error flag and keep synchronous tools off the loop.
- Commit generated edits, scripts, silence cuts and color grading atomically.
  Preserve current project paths and reject non-finite operation numbers.
- Fix invalid-media batch uploads, codec-family fallback, render settings
  coalescing, cross-process render ownership and cancellation during child spawn.
  Isolate legacy overlay workers; fix FFmpeg's missing composite output label
  and preserve optional background audio.
- Fix conversation path validation, concurrent history/cost persistence and CLI
  stream lifetime/output bounds. Disable render dependency telemetry.
- Expand CI to lint, the non-browser regression suite, Python 3.11-3.13,
  package builds and a default-install smoke check.
- Remove tests of an untracked private sample project; generate timeline-view
  media fixtures locally. Use the sandbox's actual interpreter/version in its
  test probe, and isolate direct proxy tests from ingest's background workers.
- Document Diffusion Studio's tested compiler/write-back reuse seam and a
  proposed optional JSX adapter in `docs/DIFFUSION_INTEGRATION.md`.

## v1.3.1 — 2026-08-11

**Installers provision the full render stack** — a fresh download can now
actually render, not just serve MCP.

- `install.sh` (Linux/macOS) + `install.ps1` (Windows): detect or auto-install
  Node.js >= 22 (user-local, no sudo), run `npm install`, and verify the
  pinned HyperFrames engine (`hyperframes@0.7.65`) executes.
- ffmpeg probe (Windows: winget `Gyan.FFmpeg`; Linux: package hints) and
  Chrome/Chromium probe for headless capture.
- melt probe with honest Windows handling (no packaged melt; overlay-only
  renders work without it; warning + WSL option otherwise).
- Every install ends with a **runtime readiness summary** (ffmpeg / melt /
  node / hyperframes / chrome → READY or manual steps).
- Docs now match the code: INSTALL.md runtime requirements + Windows/Linux
  parity, MCP.md render pipeline (HyperFrames-native), agent install prompt,
  and the guide on GitHub Pages.
- Contributing: `CONTRIBUTING.md`, pull-request and issue templates,
  `SECURITY.md`.
- Proof point: 60 s HyperFrames logo intro rendered end to end through the
  pipeline at 1080p30 with GPU (NVENC) encode.

## v1.3.0 — 2026-08-11

- One-command installers for Linux/macOS (`install.sh`) and Windows
  (`install.ps1`), released with installer assets.
- Real product screenshots (Review Studio + timeline) in the README.
- Agent install/configure prompts in `docs/`.
- Live guide on GitHub Pages (https://ah64-dll.github.io/OpenEdit/).
- MIT license and metadata cleanup.
