# Diffusion authoring milestone validation

Verified on 2026-10-08 with Python 3.12, Node 24 and the pinned upstream
`fefcde9df7198466bd7cc9f3a9d7eae1575b5b12` source. This report covers the first
media-authoring milestone and compiler packaging, not a browser renderer.

## Real compiler and graph checks

The 32 tests in `tests/test_diffusion_authoring.py` exercise the real Node
compiler and upstream AST source writer. They cover video/audio/still-image
export, unchanged round trips, add/remove/move/trim/source replacement,
absolute gain without compounding, escaped Unicode identities, stale revisions
before and during compilation, concurrent WAL export consistency, rollback
after late invalid or skipped edits, unsupported JSX, duplicate identities,
track order, overlaps, scene changes, existing effect/overlay preservation,
compiler timeouts and restart. A JavaScript side-effect fixture is rejected
without execution. An actual stdio MCP session verifies edit results and
protocol error flags while retaining six tools.

Registry invocation coverage includes the two new subcommands. Ruff and
installer shell syntax pass. All Python package source also parses using the
Python 3.11 grammar. GitHub CI runs Python 3.11/3.12/3.13 and installs the
optional worker explicitly, so authoring tests run there without Chromium.

Full local regression result: **1,464 passed, 18 skipped, 1 deselected** in
95.62 seconds. All 18 skips require the absent `melt` executable. The deselected
test requires a real HyperFrames/Chrome render. No authoring tests were skipped.

## Distribution checks

- Built wheel and source distribution successfully using Hatchling 1.32.4.
- Confirmed both ship worker code, lockfile and MPL source/license, without
  node_modules or Python bytecode. Wheel size: 658,523 bytes in this build.
- Confirmed vendored TypeScript files match the pinned upstream files byte for
  byte, and package metadata declares `MIT AND MPL-2.0` with both license files.
- Installed the wheel in a fresh environment with default Python dependencies.
  JSX export and packaged guide loading work before installing Node packages.
- Installed the worker using the installed wheel's setup module. An actual
  installed-wheel MCP session exported source, moved/trimmed/set volume with
  three atomic operations and rejected a stale write. Startup instructions
  remained 1,219 bytes and the MCP tool count remained six.
- CI repeats default-wheel readiness/license checks, optional worker setup and
  compilation from the installed wheel outside the repository.

## Remaining validation

No Diffusion browser/runtime/encoder is enabled. Browser graphics, playback
rates, speed ramps, dynamic gain, compositing parity and persistent visual
source editing need the later milestones' tests. Existing media renderers
receive ordinary IR operations; this milestone does not establish new frame
or audio parity against Diffusion. Native Windows worker lifecycle and setup
have not been executed in this environment.
