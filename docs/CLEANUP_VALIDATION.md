# Cleanup and validation record

Baseline: OpenEdit commit `0558bd1`. Work branch: `fix/repository-cleanup`.

## Changes

- Removed the Pi extension, bridge, provider and provider-specific tests.
  MCP is installed by default. Review UI remains available; built-in chat is
  opt-in and its provider SDKs are optional.
- Removed 1,553 generated indexes, completed task scratch files, backup UI
  copies, personal scripts/configuration and local launchers: 44,583,336 bytes
  of tracked artifacts. Added ignores to keep generated state out of Git.
- Resolved the existing Ruff findings, including missing runtime imports and
  unused private code. Kept public compatibility exports and legacy IR types
  needed to replay existing projects.
- Reduced MCP initialization instructions from 27,292 to 1,219 UTF-8 bytes
  (95.5%). Guides remain available as resources/prompts. Bounded asset and
  transcript pages, removed duplicated transcript output, and made detailed
  render diagnostics an explicit request.
- Fixed nested schema validation, invalid numeric coercion, mutually exclusive
  edit modes and MCP protocol error flags. Synchronous MCP tools run off the
  event loop.
- Made generated edits, script edits, silence cuts and color changes atomic.
  Fixed concurrent project-ID creation, status-event integrity and ordering
  transactions. Free-form CLI edits use the current project layout.
- Fixed render coalescing across settings, cross-process worker ownership,
  cancellation during child spawn and QC, and shutdown cleanup. Legacy overlay
  jobs now run in a managed child process. Fixed FFmpeg's missing composite
  output label, optional background audio, codec-family fallback and executable
  paths containing spaces. Removed the unpinned automatic HyperFrames download
  fallback and disabled dependency telemetry in render processes.
- Fixed history path traversal, concurrent history/cost persistence, context
  truncation that split tool exchanges, and unbounded CLI stream lifetime,
  stderr and line buffers.
- Removed the Rust/Bubblewrap execution layer, backend selection, binary
  resolvers and obsolete syscall/protocol tests. MCP scripts and MoviePy
  graphics now use trusted Python subprocesses. Timeouts, bounded output,
  project-path checks, operation validation and atomic commits remain active.
  Scripts inherit the host account permissions; MCP does not provide isolation.
  Memory/CPU arguments remain only for legacy operation compatibility and do
  not impose OS resource limits.
- Updated installers, architecture documentation and CI checks. The declared
  MCP SDK minimum is the tested `1.30`; earlier inspected SDKs did not support
  the `CallToolResult` handler used to preserve error flags.

## Executed checks

| Check | Result |
|---|---|
| Full non-browser suite | **1,430 passed, 18 skipped, 1 deselected**; Python 3.12 |
| Ruff | All package and test files pass |
| Diff whitespace / Bash installer syntax | Pass |
| Python 3.11 syntax parsing | All 193 package Python files pass |
| Wheel and source distribution | Both build successfully |
| Wheel contents | 245 files; guides present; no Pi/generated-index/cache code |
| Fresh installed-wheel stdio MCP | Initialization, six tools, script execution and protocol error flags pass |
| Default-install dependency isolation | Anthropic and OpenAI SDKs absent; MCP still works |
| Real local FFmpeg compositing | Backgrounds with and without audio pass; expected streams verified with ffprobe |
| Diffusion compiler/write-back harness | Stable IDs, timing/title writes, source stamping and JSX compilation pass |

The full-suite command is:

```bash
pytest -m 'not browser' --timeout=30 --timeout-method=thread --tb=short
```

New regression coverage exercises actual local subprocess termination, stdio
MCP, concurrent persistence, atomic rollback, bounded paging and FFmpeg output.
CI now checks Python 3.11, 3.12 and 3.13; those additional runtime versions were
not executed locally.

## Verification boundaries

The remaining 18 skips require MLT `melt`. The single browser rendering test is excluded: automatic approval
review blocked HyperFrames telemetry and then a required browser download.
Telemetry is now disabled; the browser-dependent render was not completed.
Windows installer execution and full MLT rendering were not verified here.

The original 31 skips broke down as follows:

| Count | Coverage | Missing requirement |
|---|---|---|
| 18 | MLT render integration, including proxy/final, graphics and timeout checks | `melt`; FFmpeg is available |
| 5 | Generated Python edits through the real OS sandbox | Trusted `open-edit-sandbox` Rust executable |
| 4 | Recorded syscall-observation fixtures | `sandbox/observations/` trace files, not included in the repository |
| 3 | A developer's private FocusPopup sample project | Hardcoded files outside the repository |
| 1 | Real FFmpeg timeline-view image | Hardcoded sample video outside the repository |

Follow-up inspection removed the three sample-project checks because their
subject is not part of OpenEdit's tracked code. The timeline-view test now
generates its own video/audio fixture and passes. The four useful script integration
cases now execute with real Python instead of skipping for missing Rust
binaries. The read-only bind-mount case, Rust protocol mocks and four trace
fixture checks were removed with the sandbox. New tests exercise bounded
streams, timeout lock release, child termination, graphics output, stale-output
rejection and graphics failure cleanup. Direct encoder tests disable automatic ingest jobs to
prevent concurrent background status updates from making their assertions
flaky; automatic-enqueue and job-service tests continue to cover those flows.

Diffusion Studio is feasible as an optional authoring adapter. Its browser
renderer is not integrated or validated by this cleanup. See
[the integration assessment](DIFFUSION_INTEGRATION.md) and the independent
`research/diffusion-compiler/` harness for the tested seam, adapter contract,
license boundary and remaining acceptance checks.

Passing these checks establishes the changes above; it does not prove the
repository has no remaining bugs or validate every rendering backend.
