# Task 1 Brief

### Task 1: Establish the M0 product and diagnostics contract

**Files:**
- Create: `open_edit/render/diagnostics.py`
- Modify: `open_edit/render/orchestrator.py`
- Test: `tests/test_render/test_diagnostics.py`, `tests/test_render/test_orchestrator.py`

**Interfaces:**
- Consumes: `RenderResult`, `RenderProfile`, `mode`, and the existing `PipeResult` timing fields.
- Produces: `StageRecorder`, `product_descriptor(mode, profile)`, and the canonical diagnostics keys used by all later tasks.

- [ ] **Step 1: Write failing contract tests.**

```python
def test_product_descriptor_distinguishes_review_artifact_from_source_proxy():
    descriptor = product_descriptor("proxy", width=640, height=360)
    assert descriptor == {
        "kind": "review_artifact",
        "mode": "proxy",
        "label": "Review artifact",
        "width": 640,
        "height": 360,
        "interactive": False,
        "source_proxy": False,
        "timeline_preview_chunk": False,
    }


def test_stage_recorder_preserves_status_and_numeric_elapsed():
    recorder = StageRecorder()
    recorder.record("remotion_materialize", 1.25, cache_hits=2, cache_misses=1)
    recorder.skip("ffmpeg_encode", reason="deliverable_cache_hit")
    assert recorder.stages["remotion_materialize"]["elapsed_sec"] == 1.25
    assert recorder.stages["remotion_materialize"]["status"] == "completed"
    assert recorder.stages["ffmpeg_encode"] == {
        "elapsed_sec": 0.0,
        "status": "skipped",
        "reason": "deliverable_cache_hit",
    }


def test_legacy_stage_aliases_remain_available():
    result = RenderResult(
        ok=True,
        diagnostics={
            "stages": {
                "melt_video": {"elapsed_sec": 2.0},
                "ffmpeg_encode": {"elapsed_sec": 3.0},
            },
            "legacy_stage_aliases": {
                "melt": "melt_video",
                "ffmpeg": "ffmpeg_encode",
            },
        },
    )
    assert result.diagnostics["legacy_stage_aliases"]["melt"] == "melt_video"
```

- [ ] **Step 2: Run the focused tests to verify they fail.**

Run: `pytest -q tests/test_render/test_diagnostics.py tests/test_render/test_orchestrator.py`

Expected: collection or assertion failures because `open_edit.render.diagnostics` and the canonical stage schema do not yet exist.

- [ ] **Step 3: Implement the minimal diagnostics module.**

Use these canonical stage names:

```text
derive_timeline
render_cache_lookup
remotion_materialize
build_render_plan
emit_mlt
melt_audio
melt_video
ffmpeg_encode
source_repair
qc
```

`StageRecorder.record()` must coerce elapsed values to finite non-negative floats and retain additional scalar fields such as `bytes`, `cache_hits`, `cache_misses`, `worker_count`, and `reason`. `product_descriptor()` must map `proxy` to `review_artifact` and `final` to `final_export`; it must never claim that either mode is interactive.

- [ ] **Step 4: Run the focused tests and the current orchestrator tests.**

Run: `pytest -q tests/test_render/test_diagnostics.py tests/test_render/test_orchestrator.py`

Expected: PASS, with existing `diagnostics["stages"]["remotion_materialize"]`, `["melt"]`, `["ffmpeg"]`, and `["audio"]` assertions still passing during the transition.

- [ ] **Step 5: Commit the M0 diagnostics contract.**

```bash
git add open_edit/render/diagnostics.py open_edit/render/orchestrator.py \
  tests/test_render/test_diagnostics.py tests/test_render/test_orchestrator.py
git commit -m "feat: define render diagnostics contract"
```

---
