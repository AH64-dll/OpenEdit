# Task 7 Brief

### Task 7: Skip proxy QC on verified hits and add repair early-out

**Files:**
- Create: `open_edit/qc/policy.py`
- Modify: `open_edit/kernel/render_jobs.py`, `open_edit/cli.py`, `open_edit/render/source_repair.py`
- Test: `tests/test_render_jobs.py`, `tests/test_render/test_source_repair.py`

**Interfaces:**
- Consumes: `mode`, `cache_hit`, diagnostics, and the existing `run_qc_gate()`/`repair_render_output()`.
- Produces: a deterministic QC policy, a persisted skipped-QC report, QC stage timing, and no-op repair short-circuiting.

- [ ] **Step 1: Write failing policy tests.**

```python
def test_proxy_cache_hit_skips_qc_by_default(monkeypatch):
    monkeypatch.delenv("OPEN_EDIT_PROXY_QC_POLICY", raising=False)
    assert qc_policy("proxy", cache_hit=True) == "skip"
    assert qc_policy("proxy", cache_hit=False) == "run"


def test_final_cache_hit_still_runs_qc():
    assert qc_policy("final", cache_hit=True) == "run"


def test_proxy_policy_can_force_always_or_never(monkeypatch):
    monkeypatch.setenv("OPEN_EDIT_PROXY_QC_POLICY", "always")
    assert qc_policy("proxy", cache_hit=True) == "run"
    monkeypatch.setenv("OPEN_EDIT_PROXY_QC_POLICY", "never")
    assert qc_policy("proxy", cache_hit=False) == "skip"


@pytest.mark.asyncio
async def test_render_job_persists_skipped_qc_report(tmp_path, monkeypatch):
    service = service_with_fake_successful_launch(
        tmp_path, result={"mode": "proxy", "cache_hit": True}
    )
    called = False

    def fail_if_qc_runs(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("QC must be skipped")

    monkeypatch.setattr("open_edit.qc.gate.run_qc_gate", fail_if_qc_runs)
    job = await wait_for_service(service, tmp_path)
    report = job.qc_report
    assert called is False
    assert report["skipped"] is True
    assert report["reason"] == "deliverable_cache_hit"
    assert job.result["diagnostics"]["stages"]["qc"]["status"] == "skipped"
```

- [ ] **Step 2: Run the focused tests to verify they fail.**

Run: `pytest -q tests/test_render_jobs.py tests/test_render/test_source_repair.py`

Expected: no policy module exists and proxy cache-hit jobs currently invoke the full QC gate.

- [ ] **Step 3: Implement the explicit M1 policy.**

Use these values for `OPEN_EDIT_PROXY_QC_POLICY`: `always`, `skip_on_hit` (default), and `never`. `final` and `overlay` always run QC regardless of the variable. A skipped report is a JSON-compatible diagnostic, not a passing `QCReport` pretending checks ran:

```python
{
    "passed": True,
    "skipped": True,
    "reason": "deliverable_cache_hit",
    "checks": [],
}
```

`RenderJobService._attach_qc()` must copy diagnostics before editing them, time both a real gate and a skip, attach `qc_report` to the result and SQLite row, and keep a QC failure diagnostic-only as today. The CLI’s human-readable non-JSON path uses the same policy and prints `QC: SKIPPED (deliverable cache hit)` when applicable; the JSON path remains a single render-result object for the job service.

- [ ] **Step 4: Add the repair no-op guard.**

In `repair_render_output()`, when `source_baseline` has no black/frozen spans and `repair_intentional_black` is false, return the existing `changed=False` structure before invoking black/frozen detectors. Preserve all existing behavior when a baseline span or intentional-black mode is present. Add a `reason` field such as `no_source_baseline_spans` for diagnostics.

- [ ] **Step 5: Run policy, repair, and existing QC tests.**

Run:

```bash
pytest -q tests/test_render_jobs.py tests/test_render/test_source_repair.py \
  tests/test_qc/test_gate.py tests/test_serve_agent_visual_verify.py
```

Expected: PASS. A final cache hit still has a real QC report; a proxy cache hit has a clearly marked skipped report.

- [ ] **Step 6: Commit QC and repair policy.**

```bash
git add open_edit/qc/policy.py open_edit/kernel/render_jobs.py open_edit/cli.py \
  open_edit/render/source_repair.py tests/test_render_jobs.py \
  tests/test_render/test_source_repair.py
git commit -m "perf: skip proxy qc on verified cache hits"
```

---
