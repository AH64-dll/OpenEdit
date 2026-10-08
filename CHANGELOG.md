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

### Optional Diffusion authoring and graphics

**Diffusion authoring and graphics** — optional literal-JSX editing of media
clips and graphics scenes through MCP, backed by a pinned Chromium render
worker and versioned CAS previews.

- Authoring/graphics operations on the existing six tools:
  `get_authoring_view`, `apply_authoring_edit`, `get_graphics_view`,
  `rewrite_graphics_source`, `trigger_render` with `mode=graphics`, and
  `commit_graphics`. All write paths are revision-checked and commit
  atomically into the SQLite graph. Source rewrites and preview jobs prepare
  drafts and outputs; only explicit authoring saves or graphics commits edit IR.
- Graphics studio in the review UI: source/editor, canvas selection of
  direct scene children, parent-relative nested edits and live preview.
- Pinned browser worker renders literal JSX graphics through the vendored
  Diffusion runtime; a pinned compiler worker translates authored JSX back
  into graph operations.
- Graphics renders materialize into versioned CAS media with poster and
  preview paths; durable jobs recover after restarts and retain checked previews.
- Media JSX supports constant `playbackRate` (0.125-8), baked into the
  committed CAS asset with provenance for the original hash/range/rate.
- Cumulative graphics materialization budgets: 64 MiB, 32 megapixels and
  64 images per commit.
- Graphics `<group>` matches upstream Diffusion semantics: it takes
  transform/opacity/timing props only and derives its box from children.
  `fill`, `width`, `height` and paint props on a group are now rejected at
  compile instead of silently doing nothing; clip a painted child rect to
  get the same effect.
- Packaging: license is now `MIT AND MPL-2.0 AND OFL-1.1`; vendored MPL-2.0
  sources, lockfiles, `PROVENANCE.json` and the OFL font license ship in
  wheels and source distributions. Node_modules and browser downloads do
  not; `python -m open_edit.integrations.diffusion.setup [--graphics
  --chromium]` installs them explicitly.
- Docs: `docs/DIFFUSION_AUTHORING.md`, `docs/DIFFUSION_GRAPHICS.md`, updated
  README license and tooling sections.

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
