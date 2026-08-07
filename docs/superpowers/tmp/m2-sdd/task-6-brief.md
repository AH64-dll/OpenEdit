# Task 6 Brief

### Task 6: Apply M5 repair and final-export polish

**Files:**
- Modify: `open_edit/render/source_repair.py`
- Modify: `open_edit/render/orchestrator.py`
- Test: `tests/test_render/test_source_repair.py`
- Test: `tests/test_render/test_orchestrator.py`
- Test: `tests/test_e2e_render.py`

**Interfaces:**

- Consumes: Task 3’s source-media policy, Task 4’s detector budgets, existing
  source-baseline spans, and the overlay-protection interval logic.
- Produces a bounded repair API:

```python
def repair_render_output(
    video_path: str | Path,
    output_path: str | Path,
    source_baseline: dict[str, Any] | None = None,
    *,
    repair_source_black: bool = True,
    repair_source_frozen: bool = False,
    repair_intentional_black: bool = False,
    protected_spans: Iterable[dict[str, Any] | tuple[float, float]] = (),
    detector_timeout_s: float | None = None,
    skip_if_no_source_defects: bool = True,
) -> dict[str, Any]:
    """Repair only confirmed source defects within the allowed budget."""
```

- [ ] **Step 1: Write failing early-out and protected-overlay tests.**

Add:

```python
def test_repair_returns_without_output_decode_when_source_has_no_defects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    rendered = make_rendered_video(tmp_path / "rendered.mp4")
    monkeypatch.setattr(mod, "list_black_frames", fail_if_called)
    monkeypatch.setattr(mod, "list_frozen_frames", fail_if_called)

    result = mod.repair_render_output(
        rendered,
        tmp_path / "repaired.mp4",
        source_baseline={"black_frames": [], "frozen_frames": [], "errors": []},
    )

    assert result["ok"] is True
    assert result["changed"] is False
    assert result["output_path"] == str(rendered)


def test_repair_never_rewrites_protected_overlay_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    rendered = make_rendered_video(tmp_path / "rendered.mp4")
    captured: dict[str, object] = {}

    def fake_black(path, *args, **kwargs):
        captured["black_kwargs"] = kwargs
        return black_result_for_span(0.0, 4.0)

    monkeypatch.setattr(mod, "list_black_frames", fake_black)
    monkeypatch.setattr(mod, "list_frozen_frames", lambda *a, **k: frozen_result_empty())
    monkeypatch.setattr(mod, "_repair_stream", fake_repair_stream)

    result = mod.repair_render_output(
        rendered,
        tmp_path / "repaired.mp4",
        source_baseline={
            "black_frames": [{"start_sec": 0.0, "end_sec": 4.0}],
            "frozen_frames": [],
        },
        protected_spans=[(1.0, 3.0)],
        detector_timeout_s=30.0,
    )

    assert result["ok"] is True
    assert result["protected_spans"] == [{"start_sec": 1.0, "end_sec": 3.0}]
    assert captured["black_kwargs"]["timeout_s"] == 30.0
```

- [ ] **Step 2: Run source-repair tests to verify the optimization fails.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_render/test_source_repair.py tests/test_render/test_orchestrator.py \
  -o addopts="" -q
```

Expected: FAIL because repair currently probes the complete output even when
the baseline is empty and has no detector budget argument.

- [ ] **Step 3: Implement the safe M5 repair policy.**

Change `SOURCE_REPAIR_POLICY_VERSION` to a new value that names the early-out
and overlay-protected semantics. Before output detection, return
`changed=False` when all of these are true:

- `skip_if_no_source_defects` is true;
- both source black/frozen span lists are empty;
- `source_baseline["errors"]` is empty;
- `repair_intentional_black` is false.

When source spans exist, expand each source span by 1 second, clamp it to the
render duration, merge overlapping windows, and call black/frozen detection
only over those windows with `timeout_s=detector_timeout_s`. Keep
`_subtract_protected_spans()` as the final step before `_merge_repair_spans()`;
never interpolate over a Remotion or video-overlay interval.

In `render_project()`:

- `emission_profile="final"` always uses original source paths, source
  baseline collection, repair, and full final QC.
- `emission_profile="review-artifact"` retains the existing repair behavior but
  receives the same detector budget and policy diagnostics.
- `emission_profile` values used by future preview/chunk workers do not run
  source repair in this whole-file orchestrator.
- Pass final QC’s remaining budget to repair and record
  `diagnostics["repair_policy"]`, `changed`, `protected_spans`, and timeout
  details.
- Keep the optional “concat short overlays” optimization out of the default
  path. It may be implemented only in a later task if a Phase 1-style N-overlay
  rebench demonstrates a measured ffmpeg regression; it is not required for
  the source-proxy/QC contract.

- [ ] **Step 4: Run repair and final safety tests.**

```bash
/home/ah64/apps/mlt-pipeline/.venv/bin/python -m pytest \
  tests/test_render/test_source_repair.py \
  tests/test_render/test_orchestrator.py \
  tests/test_e2e_render.py \
  -o addopts="" -q
```

Expected: PASS, including the existing regression that source repair cannot
erase overlays and the existing source-byte immutability test.

- [ ] **Step 5: Commit M5 repair polish.**

```bash
git add open_edit/render/source_repair.py open_edit/render/orchestrator.py \
  tests/test_render/test_source_repair.py tests/test_render/test_orchestrator.py \
  tests/test_e2e_render.py
git commit -m "perf(render): bound source repair and preserve final overlays"
```

---
