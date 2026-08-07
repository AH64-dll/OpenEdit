# Task 9 Brief

### Task 9: Extend MCP and REST enqueue/poll contracts

**Files:**
- Modify: `open_edit/kernel/tool_registry.py`
- Modify: `open_edit/kernel/tool_executor.py`
- Modify: `open_edit/serve/routers/renders.py`
- Test: `tests/test_tool_registry.py`
- Test: `tests/test_tool_executor.py`
- Test: `tests/test_serve_render_jobs.py`

**Interfaces:**
- Consumes: `PreviewRange`, `PreviewMedia`, render-job params, and `RenderJobService`.
- Produces:

```python
class TriggerRenderArgs(BaseModel):
    mode: Literal["proxy", "final", "overlay", "preview-chunks"] = "proxy"
    encoder: Literal["gpu", "cpu"] | None = None
    wait: bool = False
    ranges: list[PreviewRange] = Field(default_factory=list)
    media: Literal["video", "audio", "both"] = "both"
    priority: Literal["interactive", "background"] = "interactive"
    # Existing proxy/final quality fields remain unchanged.
```

`RenderRequest` mirrors `mode`, `ranges`, `media`, `priority`, and `expected_revision`. `RenderJobResponse` adds `result: dict[str, Any] | None` so clients can inspect partial/graph-changed status without reading a private path.

- [ ] **Step 1: Write failing schema and forwarding tests.**

```python
def test_trigger_render_schema_advertises_preview_ranges():
    schema = next(s for s in build_tool_schemas() if s["name"] == "trigger_render")
    assert "preview-chunks" in schema["input_schema"]["properties"]["mode"]["enum"]
    assert "ranges" in schema["input_schema"]["properties"]

def test_execute_trigger_render_forwards_preview_params(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        RenderJobService, "enqueue",
        capture_enqueue(captured),
    )
    result = asyncio.run(execute_trigger_render({
        "mode": "preview-chunks",
        "ranges": [{"start_sec": 2, "end_sec": 4}],
        "media": "audio",
        "priority": "interactive",
    }, tmp_path))
    assert result["mode"] == "preview-chunks"
    assert captured["params"]["media"] == "audio"
    assert captured["params"]["ranges"] == [{"start_sec": 2, "end_sec": 4}]
```

- [ ] **Step 2: Run focused tests and verify the existing literal/validation rejects the new mode.**

Run: `pytest tests/test_tool_registry.py tests/test_tool_executor.py tests/test_serve_render_jobs.py -k "trigger_render or render_request" -q`

Expected: FAIL before the contract is extended.

- [ ] **Step 3: Implement validation and forwarding.** Normalize ranges, reject `end_sec <= start_sec`, reject negative starts, reject unknown media/priority values, cap the number of ranges per request, and preserve existing quality/codec validation. When `preview_chunks_enabled()` is false, return the established feature-disabled error for `preview-chunks` while leaving proxy/final/overlay untouched. For `wait=true`, return the manifest-oriented result rather than treating `manifest.json` as a playable MP4.

- [ ] **Step 4: Update REST enqueue/poll models and route validation.** Accept `preview-chunks`, pass params to `enqueue()`, return `result`, and keep invalid modes/quality/codec errors at HTTP 400. Preserve 409 stale-revision behavior.

- [ ] **Step 5: Run focused and full contract tests.**

Run: `pytest tests/test_tool_registry.py tests/test_tool_executor.py tests/test_serve_render_jobs.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the public render contract.**

```bash
git add open_edit/kernel/tool_registry.py open_edit/kernel/tool_executor.py open_edit/serve/routers/renders.py tests/test_tool_registry.py tests/test_tool_executor.py tests/test_serve_render_jobs.py
git commit -m "feat: expose preview-chunks through render APIs"
```
