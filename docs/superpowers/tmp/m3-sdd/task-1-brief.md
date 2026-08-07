# Task 1 Brief

### Task 1: Freeze the M1 frame-engine handoff

**Files:**
- Create: `tests/test_preview_frame_engine_contract.py`
- Modify only if the M1 landmark is absent: `open_edit/render/frame_engine.py`
- Read for compatibility: `open_edit/render/materialize.py`, `open_edit/render/remotion/renderer.py`

**Interfaces:**
- Consumes: M1’s host-only Remotion/frame-engine implementation.
- Produces: the exact renderer contract used by `preview_chunks.py`:

```python
class PreviewVideoRequest(TypedDict):
    project_dir: Path
    timeline: Timeline
    render_start_frame: int
    render_end_frame: int
    core_start_frame: int
    core_end_frame: int
    composition_uids: tuple[str, ...]
    profile: RenderProfile
    output_path: Path

class PreviewVideoRenderer(Protocol):
    def render(self, request: PreviewVideoRequest) -> Path:
        """Render one range and return the validated video artifact path."""
```

- [ ] **Step 1: Write the failing contract test.** The test must instantiate a fake renderer, pass a request with two overlapping Remotion UIDs and a context range wider than the core range, and assert that `render()` receives the exact frame values and returns the requested output path.

```python
def test_preview_renderer_receives_core_and_context_frames(tmp_path):
    seen = {}

    class Fake:
        def render(self, request):
            seen.update(request)
            request["output_path"].write_bytes(b"video")
            return request["output_path"]

    output = tmp_path / "video.mp4"
    got = Fake().render({
        "project_dir": tmp_path,
        "timeline": Timeline(),
        "render_start_frame": 28,
        "render_end_frame": 62,
        "core_start_frame": 30,
        "core_end_frame": 60,
        "composition_uids": ("comp-a", "comp-b"),
        "profile": RenderProfile(name="preview_chunk", width=640, height=360),
        "output_path": output,
    })
    assert got == output
    assert seen["composition_uids"] == ("comp-a", "comp-b")
    assert (seen["render_start_frame"], seen["render_end_frame"]) == (28, 62)
    assert (seen["core_start_frame"], seen["core_end_frame"]) == (30, 60)
```

- [ ] **Step 2: Run the focused test to verify the contract is not accidentally satisfied by a different signature.**

Run: `pytest tests/test_preview_frame_engine_contract.py::test_preview_renderer_receives_core_and_context_frames -q`

Expected: FAIL until the M1 renderer seam and request type are present.

- [ ] **Step 3: Confirm the M1 implementation satisfies the contract.** If it does not, stop M3 execution and land the M1 adapter first. The adapter may materialize/reuse files internally or pull frames in the same pass, but `preview_chunks.py` must only call `PreviewVideoRenderer.render(request)` and must not invoke `render_composition()` directly.

- [ ] **Step 4: Run the contract and existing Remotion tests.**

Run: `pytest tests/test_preview_frame_engine_contract.py tests/test_remotion_renderer.py tests/test_render/test_orchestrator.py -q`

Expected: all selected tests pass; no M1 renderer test is skipped.

- [ ] **Step 5: Commit the contract gate.**

```bash
git add tests/test_preview_frame_engine_contract.py open_edit/render/frame_engine.py
git commit -m "test: freeze preview frame-engine handoff"
```
