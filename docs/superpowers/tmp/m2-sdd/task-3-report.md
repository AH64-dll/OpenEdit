# M2 Task 3 Report

## Status

Implemented explicit source-media emission profiles and the final-originals
guard.

The planner now:

- maps `final` and `review-artifact` to canonical originals;
- maps `proxy-edit` and `preview-chunk` to ready
  `source_proxy_360_v1` CAS objects;
- records source-proxy hits and fallback reasons while preserving the
  canonical logical asset-hash keys;
- queues a missing proxy through the Task 2 host service when available;
- leaves materialized Remotion assets on their materialized CAS paths.

`render_project()` infers `final` for final renders and `review-artifact` for
proxy review artifacts, rejects a final render whose source policy is proxy,
records emission diagnostics, and scopes non-default proxy-backed cache keys
with the source-proxy profile fingerprint.

## Verification

```text
.venv/bin/python -m pytest tests/test_render/test_timeline_plan.py \
  tests/test_render/test_orchestrator.py tests/test_render/test_emitter.py \
  -o addopts='' -q
26 passed

.venv/bin/python -m pytest tests/test_render/ -o addopts='' -q
122 passed
```

No linter diagnostics were reported for the owned files.
