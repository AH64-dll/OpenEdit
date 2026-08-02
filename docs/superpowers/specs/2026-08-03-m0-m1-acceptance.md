# M0/M1 Render Acceptance — 2026-08-03

This records the Task 10 verification checkpoint for
`feat/render-m0-m1-remotion-engine`. Tasks 1–9 behavior remains unchanged
except for one test-fixture isolation fix: materializer tests clear a
process-wide tiny Remotion cache cap so cache-retention assertions are not
coupled to the separate eviction tests.

## Result

The available focused matrix, broader render/sandbox matrix, exact tiny-cap
matrix, naming/API checks, and three Phase 1 reruns completed with exit code
zero after the fixture fix. The exact Step 1 command has one repository-path
gap: `tests/test_render/test_timeline_plan.py` is absent; the available
equivalent omitted only that path, and `test_remotion_proxy_golden.py`
exercises `timeline_plan`.

## Performance gate

The documented system-Chrome bridge was required because disposable fixture
`node_modules` had been pruned; B/C dependencies were restored locally with
`npm ci`, without changing the global CLI installation.

| Evidence | Result |
|---|---|
| C proxy cold | 143.708s wall; Remotion 48.513s; 12 misses; 2 workers |
| C proxy warm | 4.092s wall; deliverable cache hit; materialize/encode skipped |
| B proxy alpha | 51.277s wall; Remotion 19.015s; 3 misses; 2 workers; `.mov` |
| Old C Remotion baseline | 93.720s |
| C reduction | 48.2%; 51.7% of baseline; strict 50% residual target missed by 1.653s |

The near-half C result is recorded without an exact-threshold claim. Host
context: 12 logical CPUs, 22 GiB RAM, 7.6 GiB available, 4 GiB swap fully
used, 11.6 GiB free disk, RTX 4050 Laptop GPU (6,141 MiB), and Chrome
150.0.7871.114. Raw evidence:

- `phase1-raw/C_proxy_m1_parallel.json`
- `phase1-raw/C_proxy_m1_warm.json`
- `phase1-raw/B_proxy_m1_alpha.json`

Opaque C cards used `.mp4` and occupied 3,567,809 bytes of Remotion output
after cold and warm runs. Transparent B cards used `.mov` under the failed
VP8/VP9 capability probe's ProRes fallback and occupied 42,956,118 bytes.
The source CAS files remained present (C: 153,247,249 bytes; B: 53,404,870
bytes).

## A1–A10 gate record

1. **A1 vocabulary/schema:** diagnostics, UI/docs copy, and MCP naming evidence.
2. **A2 cache gate:** materializer reuse plus C warm deliverable-hit skip.
3. **A3 dirty/parallel:** dirty selection, worker bound/cancellation, and
   benchmark worker diagnostics.
4. **A4 content-aware cache:** external-file invalidation, tamper, LRU,
   oversized-entry, metadata, and wipe tests.
5. **A5 alpha:** capability/profile and transparent/opaque pipe tests.
6. **A6 QC:** proxy-hit skip and final-hit run policy tests.
7. **A7 repair:** no-baseline early-out and repair regressions.
8. **A8 frame engine:** protocol, bounds, timeout, fake-server, and syntax
   checks.
9. **A9 feeder:** gated same-pass frame pipe, lifecycle, alpha, and ffmpeg
   tests.
10. **A10 constraints:** rawvideo and free-form sandbox regressions.

Detailed commands, outputs, caveats, and test names are in
`docs/superpowers/tmp/m1-sdd/task-10-report.md`.

## Known environment constraint

Earlier Task reports' CLI subprocess issue remains: the stale
`/home/ah64/.local/bin/open_edit` can fail with `ModuleNotFoundError: open_edit`.
It was not fixed globally. No unrelated assets or investigation documents were
included in this checkpoint.
