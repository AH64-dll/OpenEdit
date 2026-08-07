# Task 8 Brief

### Task 8: Run the integration gate and hand off stable M3 contracts

**Files:** No product files are created in this task; verification and
measurement only.

**Interfaces:**

- Consumes every Task 1–7 interface.
- Produces the evidence required to start M3 without reinterpreting
  `mode=proxy` or reimplementing cache/QC behavior.

- [ ] **Step 1: Run focused source-proxy, QC, cache, and job tests.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_render/test_source_proxy.py \
  tests/test_render/test_timeline_plan.py \
  tests/test_render/test_source_repair.py \
  tests/test_qc/ \
  tests/test_storage/test_cache_policy.py \
  tests/test_render/test_cache.py \
  tests/test_asset_proxy_jobs.py \
  tests/test_serve_asset_proxy_jobs.py \
  tests/test_render_jobs.py \
  -o addopts="" -q
```

Expected: 0 failures.

- [ ] **Step 2: Run all render, storage, serve, and layering tests.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_render/ tests/test_storage/ tests/test_qc/ \
  tests/test_serve_render_jobs.py tests/test_serve_projects.py \
  tests/test_serve_asset_stream.py tests/test_layering.py \
  -o addopts="" -q
```

Expected: 0 failures and no free-form sandbox changes.

- [ ] **Step 3: Run the complete suite and static checks.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  -o addopts="" -q tests/
/home/ah64/apps/mlt-pipeline/.venv/bin/ruff check open_edit/
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m compileall -q open_edit
```

Expected: the full suite passes, Ruff reports no errors, and bytecode
compilation succeeds.

- [ ] **Step 4: Re-run Phase 1 fixtures with source-proxy and QC diagnostics.**

Run the existing host-only benchmark harness against fixtures A, B, and C
once cold and once warm. Record JSON containing:

- source-proxy generation time, profile, source/proxy hashes, and bytes;
- `source_media_policy`, proxy hits, and fallback reasons;
- `qc_policy`, `qc_report.complete`, detector elapsed times, and timeout
  details;
- cache bytes before/after and `deleted_bytes`.

Acceptance evidence:

1. A final render’s emitted MLT references original source CAS paths even when
   a ready `proxy_hash` exists.
2. A preview-chunk/proxy-edit plan uses a ready source proxy and queues one
   job when it is missing; a fallback is explicit.
3. A warm proxy cache hit does not run blackdetect, freezedetect, silence, or
   thumbnail extraction under the default policy.
4. A long final does not fail at the old fixed 60-second blackdetect timeout;
   a budget exhaustion produces an explicit incomplete QC report.
5. Repeated renders cannot grow render/Remotion/source-proxy cache classes
   beyond their configured caps, and canonical source CAS remains intact.
6. The frame-server `f=rawvideo` tests and final-original guard remain green.

- [ ] **Step 5: Record the M3 handoff, then stop before chunk implementation.**

The handoff must name these stable calls:

```python
build_render_plan(
    timeline,
    ops,
    store,
    mode="proxy",
    emission_profile="preview-chunk",
)

source_media_policy_for("preview-chunk")  # "proxy"
source_media_policy_for("final")          # "original"

DEFAULT_ASSET_PROXY_JOB_SERVICE.enqueue(
    project_id,
    project_path,
    asset_hash,
)

enforce_project_cache(project_path)
```

M3 may add range emission, chunk sidecars, dirty invalidation, audio
independence, and Review Studio playback. It must not duplicate source-proxy
generation, final-original enforcement, QC policy resolution, or eviction.

---

## Explicit non-goals

- Do not implement the M3 `preview-chunks` job, chunk sidecar schema, dirty
  interval invalidation, playlist/MSE playback, or audio-independent chunk
  cache here.
- Do not rename or repurpose `mode=proxy`; it remains a whole-file review
  artifact and is not the interactive scrub solution.
- Do not use source proxies for `mode=final`, even when a proxy is newer or
  cheaper to decode.
- Do not replace MLT/melt, the rawvideo pipe, ffmpeg overlay burn-in, or the
  Remotion frame engine.
- Do not put ffmpeg, melt, Chromium, CUDA, or `/dev/dri` inside the free-form
  sandbox.
- Do not evict canonical source CAS bytes, rewrite source media, or make
  agents reference proxy filesystem paths directly.
- Do not add a new MCP tool or free-form IR operation for source-proxy
  generation in M2.
- Do not broaden this work into asset-library indexing, provider search,
  licensing, attribution, or semantic asset ranking.
- Do not make source-proxy generation synchronous on every ingest by default;
  generation is an explicit durable host job and preview/profile selection may
  queue it with an original-media fallback.
- Do not mark timed-out final QC as clean; preserve the successful render
  status while reporting incomplete diagnostic evidence.
- Do not implement speculative overlay concatenation or a greenfield
  zero-copy/GPU compositor without a new measurement-backed plan.

## Risks and mitigations

- **M1 merge overlap:** Tasks 4–6 touch M1 files. Rebase after M1 and preserve
  M1’s cache-hit gate, Remotion concurrency, and diagnostics rather than
  applying these hunks mechanically.
- **Proxy fallback hides a slow first preview:** return explicit fallback
  diagnostics and job id/status; never claim a proxy hit when the original was
  used.
- **Alpha or unsupported media is flattened:** probe alpha and mark such
  assets `not_needed`; use the canonical original until an alpha-preserving
  profile exists.
- **Proxy sidecar races with transcription/import metadata:** every sidecar
  update reloads the current model and atomically replaces only its own
  fields; add concurrent-update regression coverage if the existing store
  gains a lock.
- **Derived CAS files lose their owner:** eviction is reference-aware and
  clears `proxy_hash` before/with deletion; missing references cause
  regeneration, never source deletion.
- **Budgeted QC is mistaken for a full pass:** `policy`, `complete`, `skipped`,
  and timeout details are persisted in `qc_report` and documented for agents.
- **Long detector subprocesses outlive their budget:** every detector receives
  an explicit timeout and catches `TimeoutExpired`; the final job remains
  cancellable through the existing host-worker process lifecycle.
- **Source proxies are expected to fix Remotion cost:** benchmark and document
  that they reduce heavy-source decode/scale cost only; Remotion materialize
  remains M1’s responsibility.
