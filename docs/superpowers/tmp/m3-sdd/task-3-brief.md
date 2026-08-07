# Task 3 Brief

### Task 3: Implement frame-aligned chunk geometry and local timeline slicing

**Files:**
- Create: `open_edit/render/preview_invalidation.py`
- Modify: `open_edit/render/timeline_plan.py`
- Modify: `open_edit/render/emitter.py`
- Test: `tests/test_preview_invalidation.py`
- Regression tests: `tests/test_render_emitter.py`, `tests/test_render/test_emitter.py`

**Interfaces:**
- Consumes: `Timeline`, `PreviewManifest`, project FPS, and the M1 renderer request.
- Produces:

```python
@dataclass(frozen=True)
class ChunkWindow:
    index: int
    start_frame: int
    end_frame: int
    render_start_frame: int
    render_end_frame: int
    crop_head_frames: int
    crop_tail_frames: int

def make_chunk_windows(
    duration_frames: int,
    fps_num: int,
    fps_den: int,
    chunk_frames: int | None = None,
) -> list[ChunkWindow]:
    ...

def slice_timeline(
    timeline: Timeline,
    *,
    render_start_frame: int,
    render_end_frame: int,
    fps_num: int,
    fps_den: int,
    plane: Literal["video", "audio", "both"],
) -> Timeline:
    """Return local coordinates with render_start mapped to zero."""
```

- [ ] **Step 1: Write failing tests for one-second defaults, final short chunk, crossing clips, and context trimming.**

```python
def test_chunk_windows_use_project_frames():
    windows = make_chunk_windows(75, 30, 1)
    assert [(w.start_frame, w.end_frame) for w in windows] == [
        (0, 30), (30, 60), (60, 75)
    ]
    assert windows[0].render_start_frame == 0
    assert windows[0].crop_head_frames == 0

def test_slice_crossing_clip_rebases_source_points():
    timeline = timeline_with_clip(position=0.0, in_point=10.0, out_point=14.0)
    sliced = slice_timeline(
        timeline, render_start_frame=30, render_end_frame=60,
        fps_num=30, fps_den=1, plane="video",
    )
    clip = sliced.tracks[0].clips[0]
    assert clip.position_sec == pytest.approx(0.0)
    assert clip.in_point_sec == pytest.approx(11.0)
    assert clip.out_point_sec == pytest.approx(12.0)
    assert sliced.duration_sec == pytest.approx(1.0)

def test_transition_context_is_cropped_back_to_core():
    window = make_chunk_windows(90, 30, 1)[1]
    assert window.start_frame == 30 and window.end_frame == 60
    assert window.render_start_frame <= window.start_frame
    assert window.render_end_frame >= window.end_frame
    assert window.crop_head_frames == window.start_frame - window.render_start_frame
```

- [ ] **Step 2: Run the focused tests to verify missing geometry/slicing behavior.**

Run: `pytest tests/test_preview_invalidation.py -q`

Expected: FAIL before the new functions exist.

- [ ] **Step 3: Implement frame conversion and slicing.** Use integer frame arithmetic; calculate seconds only for Pydantic/API display. Clip overlap must adjust `position_sec`, `in_point_sec`, and `out_point_sec`; preserve clip-local effects; retain audio tracks only for `audio`/`both`; retain Remotion/HTML overlays that overlap the render window; rebase all retained positions. Include neighboring transition/effect context in `render_start_frame`/`render_end_frame`, and carry crop counts to the pipe builder.

- [ ] **Step 4: Add range-aware plan/emitter calls without changing full renders.** `build_render_plan()` should accept an already sliced timeline and continue to call `timeline_for_melt()` exactly as before. `emit_timeline()` should emit the local duration and local clip positions. Existing proxy/final tests must compare the same XML properties as before.

- [ ] **Step 5: Run focused and regression tests.**

Run: `pytest tests/test_preview_invalidation.py tests/test_render_emitter.py tests/test_render/test_emitter.py -q`

Expected: PASS, including existing 30 ms micro-fade assertions.

- [ ] **Step 6: Commit the geometry/slicing work.**

```bash
git add open_edit/render/preview_invalidation.py open_edit/render/timeline_plan.py open_edit/render/emitter.py tests/test_preview_invalidation.py tests/test_render_emitter.py tests/test_render/test_emitter.py
git commit -m "feat: add frame-aligned preview range slicing"
```
