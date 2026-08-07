# M2 Task 6 Report

## Status

Implemented source-repair and final-export polish on
`feat/render-m0-m1-remotion-engine`.

## Delivered

- Added the bounded `repair_render_output()` detector-window API with
  `detector_timeout_s` and `skip_if_no_source_defects`.
- Preserved the M1 empty-baseline early-out, while refusing that early-out for
  incomplete source baselines.
- Expanded source spans by one second, clamped/merged detection windows, and
  applied protected overlay subtraction immediately before repair-span merging.
- Added repair policy, budget, timeout, changed, protected-span, and detector
  diagnostics to the orchestrator.
- Final/review-artifact renders retain source repair; preview-chunk/proxy-edit
  profiles skip whole-file source repair and baseline collection.
- Source media remains read-only; repair writes only rendered-output paths.

## Verification

```text
.venv/bin/python -m pytest tests/test_render/test_source_repair.py \
  tests/test_render/test_orchestrator.py tests/test_e2e_render.py \
  -o addopts='' -q
23 passed

.venv/bin/python -m pytest tests/test_render/ tests/test_e2e_render.py \
  -o addopts='' -q
128 passed

IDE lint diagnostics: clean
git diff --check: clean
```

## Concerns

- The repair module accepts the Task 4 timeout-enabled detector API and
  retains a compatibility fallback while that parallel lane is integrated.
- Final QC remains attached by the existing host job/CLI path; the
  orchestrator records that final QC is required and passes its remaining
  budget into repair.
