# Changelog

All notable changes are tagged on GitHub. See
https://github.com/AH64-dll/OpenEdit/releases for downloads.

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
