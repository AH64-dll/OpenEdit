# Task 2 Brief

### Task 2: Wire stage timing and reconcile UI/documentation names

**Files:**
- Modify: `open_edit/render/orchestrator.py`, `open_edit/render/melt_runner.py`, `open_edit/kernel/render_jobs.py`, `open_edit/cli.py`
- Modify: `open_edit/serve/static/app.js`, `open_edit/serve/static/index.html`, `docs/MCP.md`
- Test: `tests/test_render/test_orchestrator.py`, `tests/test_render_jobs.py`, `tests/test_review_ui.py`

**Interfaces:**
- Consumes: `StageRecorder` and `product_descriptor()` from Task 1; `PipeResult.melt_elapsed_sec`, `audio_elapsed_sec`, and `ffmpeg_elapsed_sec`.
- Produces: a stable `diagnostics["product"]`, canonical stage entries, and compatibility aliases for existing consumers.

- [ ] **Step 1: Write failing timing and copy tests.**

```python
def test_render_diagnostics_include_canonical_stages_and_product(
    monkeypatch, tmp_path
):
    result = run_fake_render(monkeypatch, tmp_path, mode="proxy")
    assert result.diagnostics["product"]["kind"] == "review_artifact"
    assert result.diagnostics["product"]["width"] == 640
    assert set(result.diagnostics["stages"]) >= {
        "derive_timeline",
        "render_cache_lookup",
        "remotion_materialize",
        "build_render_plan",
        "emit_mlt",
        "melt_audio",
        "melt_video",
        "ffmpeg_encode",
        "source_repair",
    }
    assert result.diagnostics["legacy_stage_aliases"]["ffmpeg"] == "ffmpeg_encode"


def test_review_ui_uses_actual_profile_and_separate_source_copy():
    app = Path("open_edit/serve/static/app.js").read_text(encoding="utf-8")
    html = Path("open_edit/serve/static/index.html").read_text(encoding="utf-8")
    docs = Path("docs/MCP.md").read_text(encoding="utf-8")
    assert "Review artifact · 640×360" in app
    assert "Proxy 720p" not in app
    assert "540p" not in app
    assert "Source media" in app or "Source media" in html
    assert "timeline preview chunks" in docs.lower()
```

- [ ] **Step 2: Run the focused tests to verify they fail.**

Run: `pytest -q tests/test_render/test_orchestrator.py tests/test_render_jobs.py tests/test_review_ui.py`

Expected: failures for missing canonical names and stale “720p”/“540p” copy.

- [ ] **Step 3: Add non-breaking stage wiring.**

Time these boundaries in `render_project()`:

1. `derive_timeline`
2. profile/content fingerprint and `render_cache_lookup`
3. `remotion_materialize`
4. `build_render_plan`
5. `emit_mlt`
6. `run_pipe()` overall, with `PipeResult` values mapped to `melt_audio`, `melt_video`, and `ffmpeg_encode`
7. `source_repair`
8. `qc` in the job/CLI layer

Keep the existing top-level `RenderResult.elapsed_sec` and legacy `melt`, `ffmpeg`, and `audio` stage entries. Add `legacy_stage_aliases` to point consumers to the canonical names rather than removing old keys. Record skipped stages explicitly with `status="skipped"` and a reason.

- [ ] **Step 4: Update user-facing copy without adding preview behavior.**

Use these exact labels:

```text
proxy render list: "Review artifact · 640×360"
final render list: "Final export · 1080p"
source fallback badge: "Source media"
command palette: "Render review artifact (640×360)"
preview panel helper: "Render a review artifact (`mode=proxy`) to review the full cut."
```

In `docs/MCP.md`, state that `mode=proxy` is a full-timeline review artifact, that source proxies are per-asset derivatives, and that timeline preview chunks are a separate future/interactive product. Replace the old “Render proxy (720p)” workflow text with the actual 640×360 profile.

- [ ] **Step 5: Run the focused tests and inspect the static copy.**

Run: `pytest -q tests/test_render/test_orchestrator.py tests/test_render_jobs.py tests/test_review_ui.py`

Run: `rg -n "Proxy 720p|Render Proxy Video \\(540p\\)|Render proxy \\(720p\\)" open_edit/serve docs/MCP.md`

Expected: the pytest command passes and the stale-copy search returns no matches.

- [ ] **Step 6: Commit M0 naming and timing.**

```bash
git add open_edit/render/orchestrator.py open_edit/render/melt_runner.py \
  open_edit/kernel/render_jobs.py open_edit/cli.py \
  open_edit/serve/static/app.js open_edit/serve/static/index.html docs/MCP.md \
  tests/test_render/test_orchestrator.py tests/test_render_jobs.py tests/test_review_ui.py
git commit -m "feat: instrument render stages and clarify artifact names"
```

---
