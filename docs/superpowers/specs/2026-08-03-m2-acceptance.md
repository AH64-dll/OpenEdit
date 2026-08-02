# M2 Source Proxies & QC Acceptance — 2026-08-03

Branch: `feat/render-m0-m1-remotion-engine`

M2 Tasks 1–7 are integrated. Task 8 verified the contracts and recorded the
fixture evidence; no M2 product defect required a code fix.

## Verification gate

- Focused source-proxy/QC/cache/job command: **120 passed** in 7.70s.
- Broader render/storage/QC/serve/layering command: **288 passed** in 13.84s.
- Full `tests/` run: **1353 passed, 2 failed, 5 skipped**. The two failures
  are `tests/test_focus_popup_layout.py`, which requires the missing external
  files `/home/ah64/OpenEditProjects/timeline-test/.open_edit/remotion/{src/compositions/FocusPopup.tsx,src/Root.tsx}`.
- Full suite excluding that external-fixture test file: **1352 passed, 5
  skipped** in 69.23s.
- `python -m compileall -q open_edit`: passed.
- `.venv/bin/ruff` is absent. The fallback `/home/ah64/.local/bin/ruff`
  reports pre-existing repository-wide findings; no product source was changed
  to clear unrelated lint debt.

All pytest commands put `.venv/bin` first on `PATH`, preventing the stale
`~/.local/bin/open_edit` import path from affecting CLI tests.

## Contract evidence

The durable fixture record is
`docs/superpowers/specs/phase1-raw/m2_source_proxy_qc_cache_2026-08-03.json`.
It records source/proxy hashes and bytes, cold/warm generation time, policies,
plan hits/fallbacks, QC completeness, detector policy, budgets, cache bytes,
and source-integrity checks for fixtures A, B, and C.

- `build_render_plan(..., emission_profile="final")` and the default
  `review-artifact` plan use canonical source paths with no proxy hit, even
  when `proxy_hash` is ready.
- `proxy-edit` and `preview-chunk` use the ready
  `source_proxy_360_v1` CAS object with no fallback.
- `source_media_policy_for("final")` and
  `source_media_policy_for("review-artifact")` return `"original"`;
  `source_media_policy_for("proxy-edit")` and
  `source_media_policy_for("preview-chunk")` return `"proxy"`.
- Missing-proxy planning queues one durable host job and reports an explicit
  fallback (`tests/test_render/test_timeline_plan.py`).
- Warm whole-file proxy review hits resolve the default QC policy to
  `skip`, persist `complete=false`, and skip blackdetect, freezedetect,
  silence, and thumbnail work. Cold proxy renders use `light`.
- Final QC remains `full` and duration-budgeted: 180 seconds resolves to a
  135-second blackdetect budget; a 3600-second render is capped at 900
  seconds. Timeout evidence remains incomplete rather than clean.
- `enforce_project_cache()` protects canonical source CAS and sidecars. The
  A/B/C default-cap probe deleted `0` bytes and left all source and proxy
  objects intact; deletion/reference behavior is covered by
  `tests/test_storage/test_cache_policy.py`.
- `f=rawvideo` and final-original emitter guards remain green in the focused
  matrix.

## M3 handoff

M3 may consume these stable calls without duplicating M2 policy:

```python
build_render_plan(
    timeline, ops, store, mode="proxy", emission_profile="preview-chunk",
)
source_media_policy_for("preview-chunk")  # "proxy"
source_media_policy_for("final")          # "original"
DEFAULT_ASSET_PROXY_JOB_SERVICE.enqueue(project_id, project_path, asset_hash)
enforce_project_cache(project_path)
```

M3 may add range emission, chunk sidecars, dirty invalidation, audio
independence, and playback. It must not reimplement source-proxy generation,
final-original enforcement, QC policy resolution, or cache eviction. `mode=proxy`
remains a whole-file review artifact, not the interactive scrub solution.

Known concerns are limited to the missing external Review/FocusPopup fixture
and unavailable clean Ruff tooling; unrelated asset-indexer, `assets/`,
graphify, and tmp work remains untouched.
