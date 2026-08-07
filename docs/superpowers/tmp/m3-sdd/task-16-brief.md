# Task 16 Brief

### Task 16: Verify rollout gates, cache safety, and final non-regression

**Files:**
- Test/modify only as needed: `tests/test_render_jobs.py`, `tests/test_serve_render_jobs.py`, `tests/test_preview_cache.py`, `tests/test_preview_frontend.py`
- Read-only verification: architecture/spec files and all changed implementation paths

**Interfaces:**
- Consumes: all completed M3 tasks and the M1 dependency evidence.
- Produces: a merge-ready verification record; no new product behavior.

- [ ] **Step 1: Run the full Python suite and frontend-focused suite.**

Run:

```bash
pytest -q
pytest tests/test_preview_frontend.py tests/test_serve_module_structure.py -q
```

Expected: all tests pass; no existing proxy/final/Review Studio regression appears.

- [ ] **Step 2: Run static/lint checks on every changed Python file and inspect diagnostics.**

Run:

```bash
python -m compileall -q open_edit
```

Expected: exit code 0. Run the repository-configured checks explicitly:

```bash
ruff check open_edit/render/preview_manifest.py open_edit/render/preview_invalidation.py open_edit/render/preview_cache.py open_edit/render/preview_pipe.py open_edit/render/preview_chunks.py open_edit/kernel/render_jobs.py open_edit/kernel/tool_registry.py open_edit/kernel/tool_executor.py open_edit/serve/routers/preview_chunks.py
mypy open_edit/render/preview_manifest.py open_edit/render/preview_invalidation.py open_edit/render/preview_cache.py open_edit/render/preview_pipe.py open_edit/render/preview_chunks.py
```

Do not introduce a new tool or dependency for M3.

- [ ] **Step 3: Exercise the manual host-worker smoke path.**

```text
1. Start Review Studio in review-only mode.
2. Load a project with a short video/audio timeline.
3. Click Render Proxy and confirm one full MP4 still appears in the renders list.
4. Click Render chunks for a 4–8 second window.
5. Confirm red → yellow → green map transitions and sequential playback across two green chunks.
6. Seek into a red chunk and confirm the UI labels the whole-file proxy fallback rather than silently claiming chunk readiness.
7. Apply one Remotion overlay edit; confirm only the affected range changes color.
8. Apply audio gain; confirm video artifact IDs remain unchanged while audio/playback IDs change.
9. Restart the server and confirm the manifest/job state is recoverable from disk/SQLite.
10. Use Clear chunk cache and confirm the edit graph and proxy render remain.
```

- [ ] **Step 4: Verify the M1/M2 gates explicitly.** Record the M1 frame-engine contract test result, dirty composition reuse result, Remotion eviction result, and optional M2 source-proxy result. If any M1 hard dependency is absent, keep the preview worker feature-disabled and report the exact gate rather than shipping a bake path that violates the in-pipeline Remotion decision.

- [ ] **Step 5: Verify the M3 acceptance criteria.**

```text
- One Remotion overlay edit produces a visible update in its chunk zone without waiting for the full proxy.
- Untouched green zones remain seekable.
- Silence/gain-only edits do not invalidate video chunk keys.
- A prior exact-range chunk or stale whole-file proxy remains available while a new chunk bakes.
- Cache size and wipe controls work.
- Free-form IR remains sandboxed and never owns preview rendering.
- No live MLT SDL/OpenGL consumer was added.
```

- [ ] **Step 6: Commit only verification/test adjustments, if any.**

```bash
git add tests/test_render_jobs.py tests/test_serve_render_jobs.py tests/test_preview_cache.py tests/test_preview_frontend.py
git commit -m "test: finalize chunked preview rollout gates"
```

If no test adjustment is required, do not create an empty commit.

## Commit Sequence

The intended reviewable commit sequence is:

1. `test: freeze preview frame-engine handoff`
2. `feat: define preview chunk manifest contract`
3. `feat: add frame-aligned preview range slicing`
4. `feat: add plane-aware preview invalidation`
5. `feat: build independent preview plane commands`
6. `feat: add bounded atomic preview cache`
7. `feat: bake dirty preview chunks with fallbacks`
8. `feat: schedule durable preview-chunks jobs`
9. `feat: expose preview-chunks through render APIs`
10. `feat: serve preview manifests and chunk files`
11. `feat: add preview manifest frontend state`
12. `feat: add sequential chunk preview consumer`
13. `feat: integrate chunk preview into Review Studio`
14. `docs: describe chunked timeline preview workflow`
15. `test: verify preview chunk invalidation and fallback`
16. `test: finalize chunked preview rollout gates`

Each commit must pass its task’s focused tests before the next task starts. Do not squash the commits until review has accepted the boundaries; the separate commits make it possible to reject MSE/consumer details without hiding cache or invalidation changes.

## Acceptance and Rollback

### M3 acceptance

- A `preview-chunks` MCP or REST request returns a durable job ID and never blocks by default.
- The job produces a schema-versioned manifest and independently addressable video/audio/playback artifacts.
- The manifest visibly exposes red/yellow/green state and preserves prior same-range fallbacks.
- A one-second, frame-aligned chunk can be selected and played by the Review Studio consumer with global timeline seek mapping.
- A Remotion edit invalidates only overlapping video chunks when the M1 frame-engine contract supplies the affected UIDs.
- Audio gain/silence/normalization changes do not flush unchanged video keys.
- Whole-file `mode=proxy` continues to render, list, stream, and load exactly as before.
- Cache cap, eviction, atomic recovery, path safety, and wipe are tested.
- No free-form GPU access or live MLT SDL consumer is introduced.

### Feature flag and rollback

Keep chunk generation behind `OPEN_EDIT_PREVIEW_CHUNKS=1` until the short-fixture acceptance test and manual smoke path pass. When unset, the API may return a clear 404/409 feature-disabled response for `preview-chunks`, while proxy/final remain fully available. If a worker or browser issue appears after enablement, set the flag to `0`; existing proxy artifacts and the Edit Graph remain untouched, and the cache wipe route can remove preview files without altering timeline state.

## Risks and Mitigations

- **M1 frame-engine seam is late or incompatible:** block worker enablement and use fake-renderer tests only; do not create an external Remotion bake relay. The hard dependency is the range-aware host renderer contract, not M1’s exact internal implementation.
- **Sequential source switching has visible gaps:** keep the last exact-range artifact and whole-file proxy fallback; pre-load the next source with `preload="auto"`; measure gap duration on a real browser before considering MSE.
- **MSE/fMP4 timestamp complexity:** do not make M3 depend on MSE. Preserve a strategy interface and manifest field so a later fMP4 implementation can be tested independently.
- **Audio/video drift during independent remux:** keep core frame/sample durations in the manifest, use local zero-based timestamps, mux with `-shortest`, and test two adjacent chunks with non-empty audio.
- **Transitions/effects cross boundaries:** render context frames and crop to core; conservatively invalidate adjacent chunks; unknown/raw-MLT/free-form changes invalidate the full timeline.
- **Graph changes during a long bake:** check graph revision/hash before every publication, stop stale workers, and retain the previous manifest/artifacts instead of replacing a newer graph’s manifest.
- **Disk pressure:** use the 512 MiB default cap, seven-day expiry, referenced-artifact protection, minimum-free-space refusal, and wipe API; never leave red temporary files unbounded.
- **Render-job schema migration:** rebuild only the old mode-check table when required and copy every existing row; run migration tests against a database created with the pre-M3 schema.
- **API/UI vocabulary regression:** filter preview jobs from the renders artifact list and retain explicit `Preview chunks`, `Proxy artifact`, and `Final export` labels.
- **Long timelines create too many DOM nodes or jobs:** coalesce adjacent status runs, request only a playhead window interactively, and process full dirty coverage only for explicit background requests.
- **M2 source proxies are unavailable:** resolve canonical assets for preview; source-proxy use is an optimization, not a correctness dependency.
- **Hardware variance:** preview profile defaults to CPU-safe browser codecs; optional host GPU encoding follows existing encoder selection and never enters the sandbox.
- **Live MLT scope creep:** any request for SDL/OpenGL/shared-memory playback is a separate M4 plan and is rejected from this M3 task sequence.

## Return Summary

- **Plan path:** `docs/superpowers/plans/2026-08-03-chunked-timeline-preview.md`
- **Task count:** 16 implementation tasks, each with focused TDD steps and a commit boundary.
- **Key files:** `open_edit/render/preview_manifest.py`, `preview_invalidation.py`, `preview_cache.py`, `preview_pipe.py`, `preview_chunks.py`; `open_edit/kernel/render_jobs.py`, `tool_registry.py`, `tool_executor.py`; `open_edit/serve/routers/preview_chunks.py`, `renders.py`; `open_edit/serve/static/js/preview.js`, `api.js`, `state.js`, `app.js`, `index.html`, `style.css`; and the corresponding preview/cache/route/frontend tests.
- **M1 dependencies:** stable profile/content fingerprints, a range-aware host Remotion frame-engine/renderer seam, dirty composition UID reuse, bounded Remotion output eviction, and passing M1 contract tests. M2 source proxies are optional.
- **Main risks:** HTML5 source-switch gaps, A/V sync during plane remux, transition boundary correctness, stale jobs racing graph edits, disk pressure, and M1 seam timing. The plan mitigates each with exact-range fallbacks, context cropping, atomic graph checks, cache caps/wipe, and a feature flag.
- **Out of scope:** live MLT SDL/OpenGL consumer and any GPU/free-form sandbox redesign; both remain M4 or later decisions.
