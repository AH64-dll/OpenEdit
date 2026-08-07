# Task 10 Brief

### Task 10: Run the M0/M1 verification matrix and performance gate

**Files:**
- Modify only files from Tasks 1–9 when verification exposes a defect.
- Test: all affected Python tests, existing golden/e2e render tests, and Phase 1 benchmark outputs under `docs/superpowers/specs/phase1-raw/` or a separately named benchmark directory.

**Interfaces:**
- Consumes: all Task 1–9 outputs and the approved Phase 1 fixtures/measurement harness.
- Produces: evidence for M0/M1 acceptance, a documented hardware/concurrency limit when necessary, and no unreviewed behavior change.

- [ ] **Step 1: Run the focused regression matrix.**

Run:

```bash
pytest -q \
  tests/test_render/test_diagnostics.py \
  tests/test_render/test_cache.py \
  tests/test_render/test_orchestrator.py \
  tests/test_render/test_source_repair.py \
  tests/test_render/test_timeline_plan.py \
  tests/test_render/test_pipe_builder.py \
  tests/test_render/test_run_pipe.py \
  tests/test_remotion_renderer.py \
  tests/test_remotion_ir_materialize.py \
  tests/test_remotion_frame_engine.py \
  tests/test_render_jobs.py \
  tests/test_qc/test_gate.py \
  tests/test_review_ui.py
```

Expected: PASS with no sandbox test changes and with the existing `f=rawvideo` assertions intact.

- [ ] **Step 2: Run the broader render and sandbox regressions.**

Run:

```bash
pytest -q tests/test_e2e_render.py tests/test_remotion_proxy_golden.py \
  tests/test_phase567_edit_render.py tests/test_sandbox/test_render_sandbox.py \
  tests/test_serve_render_jobs.py
```

Expected: PASS or explicit environment skips only for missing melt/ffmpeg/Chromium. No test may authorize GPU or Remotion inside the free-form sandbox.

- [ ] **Step 3: Re-benchmark cold proxy, warm proxy, and alpha cases.**

Use the existing Phase 1 harness against restored fixtures:

```bash
python docs/superpowers/scripts/phase1_run_bench.py C \
  --mode proxy --force --label C_proxy_m1_parallel \
  --out /tmp/C_proxy_m1_parallel.json
python docs/superpowers/scripts/phase1_run_bench.py C \
  --mode proxy --label C_proxy_m1_warm \
  --out /tmp/C_proxy_m1_warm.json
python docs/superpowers/scripts/phase1_run_bench.py B \
  --mode proxy --force --label B_proxy_m1_alpha \
  --out /tmp/B_proxy_m1_alpha.json
```

Compare `stage_breakdown_sec.remotion_materialize`, `cache_hit_render`, `remotion.composition_cache_hits`, `qc`, `project_bytes.remotion_out`, and worker/concurrency diagnostics against the Phase 1 raw JSON. The target is C proxy cold Remotion wall at or below roughly 50% of the measured 93.7s under parallel×2 or better; if the host cannot meet it, record the observed CPU/RAM/Chromium limit rather than making an unsupported performance claim. Warm proxy wall must be far below the old 5.0–15.4s QC-dominated range when the MP4 cache hits and proxy QC is skipped.

- [ ] **Step 4: Verify cache and disk safety.**

Run the cache-cap tests with a tiny cap, inspect that old entries and metadata are removed, and verify source CAS files remain:

```bash
OPEN_EDIT_REMOTION_CACHE_MAX_BYTES=1024 \
  pytest -q tests/test_render/test_cache.py tests/test_remotion_ir_materialize.py
```

Inspect benchmark `project_bytes.remotion_out` and confirm it does not grow without bound after repeated profile/content changes. Confirm ProRes alpha is used only when VP8/VP9 capability is not proven and that opaque cards do not request RGBA.

- [ ] **Step 5: Verify naming and API research evidence.**

Run:

```bash
rg -n "Proxy 720p|540p|mode=proxy|source proxy|timeline preview chunk|Review artifact" \
  open_edit/serve docs/MCP.md
node --check open_edit/render/remotion_frame_server.mjs
npm ls @remotion/bundler @remotion/renderer remotion
```

Expected: the three product systems are distinguishable, the actual 640×360 proxy profile is documented, and the installed Remotion versions are all `4.0.278`.

- [ ] **Step 6: Record the final M0/M1 acceptance evidence.**

The handoff must include:

```text
A1 vocabulary/schema: diagnostics + UI/docs tests
A2 cache gate: materializer call-count test + warm benchmark
A3 dirty/parallel Remotion: selection test + worker/concurrency benchmark
A4 content-aware cache: external-file invalidation + tamper/LRU tests
A5 alpha policy: capability probe + transparent/opaque pipe tests
A6 QC: proxy-hit skip and final-hit run policy tests
A7 repair: no-baseline early-out + existing repair regressions
A8 frame engine: protocol/API probe + fake-server parity
A9 same-pass feeder: gated ffmpeg pipe/lifecycle/alpha tests
A10 constraints: rawvideo and sandbox regression tests
```

- [ ] **Step 7: Make the verification checkpoint commit only after review.**

```bash
git status --short
git diff --check
git log -5 --oneline
```

If fixes were required, create a new focused commit with the relevant test evidence. Do not amend a prior commit unless the repository’s commit protocol explicitly permits it and the user requests that integration step.
