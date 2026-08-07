# Task 4 Brief

### Task 4: Parallelize only Remotion cache misses with bounded workers

**Files:**
- Modify: `open_edit/render/materialize.py`, `open_edit/render/remotion/renderer.py`
- Test: `tests/test_remotion_ir_materialize.py`, `tests/test_remotion_renderer.py`

**Interfaces:**
- Consumes: pending composition records from Task 3, `MaterializeReport`, and `force_uids`.
- Produces: deterministic timeline injection, bounded subprocess concurrency, and per-composition cache-hit/miss diagnostics.

- [ ] **Step 1: Write failing concurrency and ordering tests.**

```python
def test_materialize_limits_inter_composition_workers(
    project_with_remotion, monkeypatch
):
    active = 0
    maximum = 0
    calls = []

    def fake_render(*args, **kwargs):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        calls.append(kwargs["composition_id"])
        time.sleep(0.03)
        active -= 1
        return fake_render_result(kwargs["output_path"])

    monkeypatch.setenv("OPEN_EDIT_REMOTION_WORKERS", "2")
    monkeypatch.setattr(materialize_module, "render_composition", fake_render)
    updated, report = materialize_with_report(project_with_remotion, count=5)
    assert maximum == 2
    assert report.worker_count == 2
    assert [c.composition_id for c in updated.remotion_compositions] == [
        "Comp0", "Comp1", "Comp2", "Comp3", "Comp4"
    ]
    assert len(calls) == 5


def test_render_failure_cancels_pending_workers_and_reports_uid(
    project_with_remotion, monkeypatch
):
    monkeypatch.setattr(
        materialize_module,
        "render_composition",
        failing_render_for_uid("broken"),
    )
    with pytest.raises(RemotionMaterializeError, match="broken"):
        materialize_with_report(project_with_remotion)
```

- [ ] **Step 2: Run the focused tests to verify they fail.**

Run: `pytest -q tests/test_remotion_ir_materialize.py tests/test_remotion_renderer.py`

Expected: the miss path remains serial and the report/concurrency assertions fail.

- [ ] **Step 3: Precompute and stage work in the caller thread.**

For every composition, validate the entry point, stage referenced assets, resolve the profile/extension, compute `composition_cache_key()`, and classify it as manifest reuse, composition-cache hit, or miss before creating a pool. Never perform timeline mutation from a worker. This also prevents concurrent writes to the same staged `public/` path.

- [ ] **Step 4: Add bounded worker selection.**

Implement:

```python
def remotion_worker_count() -> int:
    requested = int(os.environ.get("OPEN_EDIT_REMOTION_WORKERS", "2"))
    return min(4, max(1, requested))
```

Reject non-numeric or non-positive values by falling back to `2`. The worker pool is `ThreadPoolExecutor(max_workers=remotion_worker_count())`; each worker waits on one Remotion subprocess, so this does not rely on Python CPU parallelism. Keep the existing `OPEN_EDIT_REMOTION_CONCURRENCY` override for each Remotion invocation, but when it is unset derive a per-process value from a total CPU budget instead of allowing every subprocess to claim all cores.

- [ ] **Step 5: Make completion deterministic and failures hard.**

Collect `Future` results keyed by `composition_uid`, then apply `_inject_clip()` in the original timeline order. On the first failure, cancel pending futures, wait for the pool to close, and raise `RemotionMaterializeError` containing the UID and bounded error text. Do not write the successful manifest from a partial batch.

- [ ] **Step 6: Add structured report fields and run tests.**

Populate `MaterializeReport` with `worker_count`, `cache_hits`, `cache_misses`, `reused_manifest_entries`, `rendered_uids`, `dirty_uids`, and elapsed time. Run:

```bash
pytest -q tests/test_remotion_ir_materialize.py tests/test_remotion_renderer.py
```

Expected: PASS, including serial behavior when `OPEN_EDIT_REMOTION_WORKERS=1`.

- [ ] **Step 7: Commit bounded parallel materialization.**

```bash
git add open_edit/render/materialize.py open_edit/render/remotion/renderer.py \
  tests/test_remotion_ir_materialize.py tests/test_remotion_renderer.py
git commit -m "perf: parallelize bounded remotion cache misses"
```

---
