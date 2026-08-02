# Task 10 — M0/M1 render verification evidence

**Date:** 2026-08-03
**Branch:** `feat/render-m0-m1-remotion-engine`
**Scope:** Tasks 1–9 regression coverage, Phase 1 benchmark reruns, cache/disk safety, and naming/API gates.

## Matrix results

### Step 1 — focused regressions

The brief's exact command was attempted first. Collection stopped because
`tests/test_render/test_timeline_plan.py` does not exist in this checkout.
`tests/test_render/test_pipe_builder.py` and `tests/test_render/test_run_pipe.py`
do exist. The available command, omitting only that absent path, passed:

```text
tests/test_render/test_diagnostics.py
tests/test_render/test_cache.py
tests/test_render/test_orchestrator.py
tests/test_render/test_source_repair.py
tests/test_render/test_pipe_builder.py
tests/test_render/test_run_pipe.py
tests/test_remotion_renderer.py
tests/test_remotion_ir_materialize.py
tests/test_remotion_frame_engine.py
tests/test_render_jobs.py
tests/test_qc/test_gate.py
tests/test_review_ui.py
PASS (exit 0)
```

### Step 2 — broader render and sandbox regressions

```text
.venv/bin/python -m pytest -q \
  tests/test_e2e_render.py tests/test_remotion_proxy_golden.py \
  tests/test_phase567_edit_render.py tests/test_sandbox/test_render_sandbox.py \
  tests/test_serve_render_jobs.py
23 passed (exit 0), no skips
```

The sandbox regression remains host-only: no test authorizes GPU or Remotion
inside the free-form sandbox, and the existing `f=rawvideo` assertions remain
present.

### Step 3 — Phase 1 benchmark reruns

The disposable B/C fixtures existed, but their Remotion `node_modules` had been
pruned. The first exact C command therefore failed with npm's
`could not determine executable to run`. I restored only the disposable
fixture dependencies with `npm ci --no-fund --no-audit` and used the documented
Phase 1 system-Chrome bridge:

```text
OPEN_EDIT_REMOTION_BIN=docs/superpowers/scripts/remotion_with_chrome.sh
OPEN_EDIT_CHROME_EXECUTABLE=/usr/bin/google-chrome-stable
```

All three requested reruns returned `ok: true`:

| Run | Wall | Remotion materialize | Render-cache hit | Remotion cache / workers | `remotion_out` |
|---|---:|---:|---|---|---:|
| C cold (`C_proxy_m1_parallel`) | 143.708s | 48.513s | no | 12 misses / 2 workers | 3,567,809 B |
| C warm (`C_proxy_m1_warm`) | 4.092s | skipped | yes | deliverable hit / no materialize | 3,567,809 B |
| B alpha (`B_proxy_m1_alpha`) | 51.277s | 19.015s | no | 3 misses / 2 workers | 42,956,118 B |

The C Remotion stage is 51.7% of the old 93.720s stage (48.2% reduction);
the strict 46.860s half-way threshold is missed by 1.653s, so this records an
approximate rather than exact performance claim. The observed host context was
12 logical CPUs, 22 GiB RAM with 7.6 GiB available and 4 GiB swap fully used,
11.6 GiB free disk, RTX 4050 Laptop GPU (6,141 MiB), and Google Chrome
150.0.7871.114. The worker/concurrency diagnostics are retained in the raw
JSON; no unsupported hardware claim is made.

Warm C shows `remotion_materialize.status=skipped` with
`reason=deliverable_cache_hit`; the standalone harness still ran its explicit
QC probe (4.037s), while the job-level proxy cache-hit policy is covered by
the regression tests. C opaque cards produced `.mp4`; B transparent cards
produced `.mov` under the host's `probe_alpha_capability() == false` ProRes
fallback. The source CAS files remained present after the runs:

```text
fixture-c source CAS: 165de875...c2ff6d, 153,247,249 bytes
fixture-b source CAS: 4f83eeb1...916958, 53,404,870 bytes
```

Durable benchmark payloads:

- `docs/superpowers/specs/phase1-raw/C_proxy_m1_parallel.json`
- `docs/superpowers/specs/phase1-raw/C_proxy_m1_warm.json`
- `docs/superpowers/specs/phase1-raw/B_proxy_m1_alpha.json`

### Step 4 — cache and disk safety

The requested command was first run with the process-wide 1 KiB Remotion cap.
It exposed three materializer assertions that assumed retained fake media
cache entries. The cache behavior was correct: the fake Remotion media is
larger than 1 KiB, so `RenderCache.evict()` removed the artifact and metadata.
The Task 4–5 test fixture now clears that external cap before materializer
assertions; this is test isolation only and does not change product behavior.

The exact command was rerun and passed:

```text
OPEN_EDIT_REMOTION_CACHE_MAX_BYTES=1024 \
  .venv/bin/python -m pytest -q \
  tests/test_render/test_cache.py tests/test_remotion_ir_materialize.py
35 passed (exit 0)
```

The cache tests still cover LRU removal, oversized-entry removal, metadata
cleanup, tamper detection, and wipe. The materializer tests cover external
file invalidation, ProRes alpha extension, direct CAS ingest, and cache reuse.
Repeated C cold/warm `remotion_out` stayed at 3,567,809 B; opaque C remained
small while alpha B used the expected `.mov` path. Existing source CAS bytes
were not removed.

### Step 5 — naming and API evidence

The requested `rg` search found the three distinct product systems and the
640×360 review artifact documentation. `node --check
open_edit/render/remotion_frame_server.mjs` passed. `npm ls
@remotion/bundler @remotion/renderer remotion` resolved every Remotion package
to `4.0.278`.

## A1–A10 acceptance evidence

- **A1 vocabulary/schema:** diagnostics product-descriptor tests, Review UI
  copy test, and `docs/MCP.md` naming search passed.
- **A2 cache gate:** materializer cache-reuse tests plus C warm deliverable-hit
  benchmark; Remotion materialization was skipped.
- **A3 dirty/parallel Remotion:** dirty-selection tests and materializer
  worker-limit/cancellation tests passed; C cold recorded 2 workers and 12
  misses.
- **A4 content-aware cache:** external-file invalidation, tamper, LRU,
  oversized-entry, metadata, and wipe tests passed.
- **A5 alpha policy:** capability/profile tests and transparent/opaque pipe
  tests passed; B used ProRes `.mov`, C opaque cards used `.mp4`.
- **A6 QC:** proxy cache-hit skip and final cache-hit run policy tests passed;
  benchmark warm C's explicit harness QC is distinguished from the job policy.
- **A7 repair:** no-source-baseline early-out and existing black/frozen repair
  regressions passed.
- **A8 frame engine:** protocol validation, bounds, timeout, fake-server
  parity, gate, and Node syntax checks passed.
- **A9 same-pass feeder:** gated frame-pull, `pipe:3+`, lifecycle, alpha, and
  real ffmpeg frame-pipe tests passed.
- **A10 constraints:** focused/broader rawvideo and sandbox regressions passed;
  no sandbox behavior was broadened.

## Environment concern

The known CLI subprocess issue remains unchanged: `/home/ah64/.local/bin/open_edit`
can resolve outside this checkout and raise `ModuleNotFoundError: open_edit`, as
documented by earlier Task reports. No global installation or unrelated
working-tree change was modified. The only code-area change in this checkpoint
is the test-fixture environment isolation described in Step 4.
