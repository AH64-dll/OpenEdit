# Diffusion execution follow-up — 2026-10-08

This follow-up builds on `b32c0ab918c62ce8ac7ee179441a984d57630be4`
from `feat/diffusion-authoring`. The implementation plan is retained unchanged.

## Delivered

- Accepted JSX, including formatting and comments, is persisted with its graph
  revision in the same SQLite transaction as the IR batch. Formatting-only
  saves remain graph no-ops. The last eight accepted revision views are kept.
- Other editors' graph changes cause a fresh source export. Stale, invalid,
  crashed and timed-out writes preserve the last-good source and operations.
- Review Studio provides a source editor and clip property controls using the
  same adapter as MCP, with HTTP 409 conflicts, retained drafts and `author=user`.
- Compiler output reads are bounded in memory. Windows timeout cleanup also
  requests descendant termination. Optional setup and six MCP tools remain.
- Dedicated CI covers the real compiler on Linux, Windows and macOS, plus a
  real Chromium/HTTP/compiler/SQLite browser flow with screenshots.

## Local evidence

Fedora Linux, Python 3.12.13, Node 22.23.3, pinned compiler dependencies. The
repository archive's Git tree and original commit were verified against GitHub
before restoring the local shallow checkout.

- Full Python regression: **1,468 passed, 18 skipped, 1 deselected**, 105.74 s.
  The 18 skips require `melt`; the deselection is the existing browser render.
- After adding crash/output-limit/history coverage, the focused authoring,
  HTTP and migration suite passed **43 tests** in 18.99 s, with no skips.
  This includes a real stdio MCP initialization, six tools, source export,
  atomic mutation and stale rejection.
- Ruff, JavaScript syntax and Git whitespace checks pass.
- Built wheel and source distribution; verified compiler source, lockfile,
  MPL license, UI module and migration inclusion, and absence of node_modules
  and bytecode. A fresh default wheel install outside the checkout loads its
  MCP entry point and packaged skills and installs the optional worker offline
  from integrity-verified locked dependency tarballs.

The execution sandbox denies socket creation and wakeup sends. Local async
tests used a temporary external test-host helper that bounds selector polling
and forwards that helper to stdio test children. This helper is not shipped or
used in CI. Tests used the machine's full FFmpeg from `~/.local/bin`, since the
system FFmpeg lacks the `libx264` encoder required by the fixtures.

Chromium fails at startup in this sandbox with `setsockopt: Operation not
permitted`. Browser screenshots and native Windows/macOS results therefore
require the dedicated CI acceptance workflow; local source edits alone are
not visual approval.

## Release boundary

This delivers source synchronization and initial UI writeback on top of the
plan's initial media-authoring release. It does **not** enable a Diffusion
browser graphics renderer, materialized graphics CAS assets, spatial canvas
editing or expanded speed/audio/compositing mappings. Milestones 3 and the
remaining parity checks in milestone 4 remain gated by their frame, encode,
audio, cancellation and compatibility acceptance tests. Existing media,
HyperFrames and legacy Remotion rendering paths retain their own requirements.
