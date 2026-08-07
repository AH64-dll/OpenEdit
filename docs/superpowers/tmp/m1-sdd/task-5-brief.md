# Task 5 Brief

### Task 5: Check the whole-file deliverable cache before materialization

**Files:**
- Modify: `open_edit/render/orchestrator.py`, `open_edit/cli.py`, `open_edit/kernel/render_jobs.py`
- Test: `tests/test_render/test_orchestrator.py`, `tests/test_render_jobs.py`

**Interfaces:**
- Consumes: the derived unmaterialized timeline, profile fingerprint, `render_reference_fingerprint()`, `RenderCache`, and Task 3 manifest path.
- Produces: a cache-hit fast path that never calls Remotion materialization, plus separate `force_remotion` and per-UID controls.

- [ ] **Step 1: Write the cache-ordering regression test.**

```python
def test_deliverable_cache_hit_skips_remotion_materialize(
    project_with_remotion, monkeypatch
):
    first = render_with_fake_pipe(project_with_remotion, force=False)
    assert first.ok and not first.cache_hit

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Remotion materialize must not run on MP4 hit")

    monkeypatch.setattr(orchestrator, "materialize_remotion_compositions", fail_if_called)
    second = render_with_fake_pipe(project_with_remotion, force=False)
    assert second.ok
    assert second.cache_hit is True
    assert second.diagnostics["cache"]["hit"] is True
    assert second.diagnostics["stages"]["remotion_materialize"]["status"] == "skipped"
    assert second.diagnostics["stages"]["remotion_materialize"]["reason"] == (
        "deliverable_cache_hit"
    )
```

- [ ] **Step 2: Run the regression test to verify it fails.**

Run: `pytest -q tests/test_render/test_orchestrator.py::test_deliverable_cache_hit_skips_remotion_materialize`

Expected: the second render calls the current materializer before checking the deliverable cache.

- [ ] **Step 3: Reorder `render_project()` without changing the cache key.**

The miss/hit order must become:

```text
load applied ops
→ derive/load unmaterialized timeline
→ resolve profile and alpha mode
→ compute graph hash and content fingerprint
→ compute deliverable cache key
→ RenderCache.get() + is_fresh()
→ return immediately on hit
→ load dirty manifest
→ materialize Remotion
→ build plan/source baseline
→ emit MLT
→ run melt→ffmpeg
→ repair
→ cache.put()
→ write successful materialization manifest
```

The pre-materialization content fingerprint must still hash Remotion source, props, referenced local-file bytes, duration, alpha mode, Remotion version, and repair policy. It is acceptable for the cache-hit path to inspect source content; it must not validate/render/ingest Remotion output unnecessarily.

- [ ] **Step 4: Add separate invalidation controls.**

Add `force_remotion: bool = False` and `remotion_uids: Collection[str] = ()` to `render_project()`. Add CLI `--force-remotion` and pass it through `RenderJobService` job params. `--force` bypasses only the whole-file MP4 cache; `--force-remotion` bypasses direct manifest reuse and composition-cache reuse for all current compositions; per-UID invalidation bypasses those entries only for the named UIDs. A normal cache hit must override neither control because `--force-remotion` still requires a full render to consume the invalidated composition.

- [ ] **Step 5: Run cache and job tests.**

Run:

```bash
pytest -q tests/test_render/test_orchestrator.py tests/test_render_jobs.py
```

Expected: PASS, including existing fake-pipe and durable-job tests. The warm path must show zero Remotion render calls.

- [ ] **Step 6: Commit cache-before-materialize ordering.**

```bash
git add open_edit/render/orchestrator.py open_edit/cli.py \
  open_edit/kernel/render_jobs.py tests/test_render/test_orchestrator.py \
  tests/test_render_jobs.py
git commit -m "perf: skip remotion on deliverable cache hits"
```

---
