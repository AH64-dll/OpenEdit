# Task 9 Brief

### Task 9: Add the incremental same-pass ffmpeg frame feeder behind a feature gate

**Files:**
- Create: `open_edit/render/remotion/frame_feeder.py`
- Modify: `open_edit/render/pipe_builder.py`, `open_edit/render/melt_runner.py`, `open_edit/render/timeline_plan.py`, `open_edit/render/orchestrator.py`
- Test: `tests/test_remotion_frame_engine.py`, `tests/test_render/test_pipe_builder.py`, `tests/test_render/test_run_pipe.py`

**Interfaces:**
- Consumes: `FramePullClient` from Task 8, `OverlayClip`, the base melt rawvideo pipe, and a list of frame-overlay specifications.
- Produces: an opt-in ffmpeg overlay input that requests frames in PTS order and writes them directly to ffmpeg without a persistent Remotion MP4/MOV/WebM artifact.

- [ ] **Step 1: Write failing command and feeder tests.**

```python
def test_pull_overlay_adds_nonseekable_image_pipe_without_changing_melt_pipe(tmp_path):
    commands = build_pipe_commands(
        "melt",
        tmp_path / "timeline.mlt",
        tmp_path / "out.mp4",
        profile=proxy_profile(),
        spec=cpu_encoder(),
        overlays=[frame_overlay(position_sec=2.0, duration_sec=1.0)],
        frame_engine="pull",
        workdir=tmp_path,
    )
    assert "f=rawvideo" in commands.melt_video_cmd
    assert "pipe:3" in commands.ffmpeg_cmd
    assert "-f" in commands.ffmpeg_cmd
    assert "image2pipe" in commands.ffmpeg_cmd
    assert ".open_edit/remotion/out/cache" not in " ".join(commands.ffmpeg_cmd)


def test_frame_feeder_requests_monotonic_source_frames(monkeypatch):
    requests = []
    client = fake_client(record=requests)
    feeder = FrameFeeder(client, frame_overlay(position_sec=2.0, duration_sec=1.0))
    feeder.write_frames(output=io.BytesIO(), output_fps=30.0)
    assert [request.frame for request in requests] == list(range(30))
    assert all(request.frame >= 0 for request in requests)
```

- [ ] **Step 2: Run the focused tests to verify they fail.**

Run:

```bash
pytest -q tests/test_remotion_frame_engine.py tests/test_render/test_pipe_builder.py \
  tests/test_render/test_run_pipe.py
```

Expected: `build_pipe_commands()` has no frame-source input and `run_pipe()` cannot manage additional file descriptors/feeders.

- [ ] **Step 3: Define the frame-overlay input shape.**

Add a `FrameOverlaySpec` that carries:

```text
composition_uid, composition_id, entry_point, props,
position_sec, duration_sec, width, height, fps, alpha
```

Normalize file overlays and frame overlays into one filter metadata list so `overlay_filter_chain()` retains the same `setpts`, `enable=between(t,...)`, scale, and alpha rules. The input index must be deterministic: base video `0`, audio `1`, then overlays in timeline order. Do not let the frame engine alter the base melt command.

- [ ] **Step 4: Add a backpressured ffmpeg image pipe.**

For each frame overlay, add an explicit non-seekable input:

```text
-thread_queue_size 8
-f image2pipe
-vcodec png
-framerate <composition fps>
-i pipe:<allocated fd>
```

`run_pipe()` allocates the descriptors, starts the frame feeder after ffmpeg is ready, and closes/terminates all feeders when ffmpeg exits, melt fails, timeout occurs, or the frame server reports an error. The feeder requests frames monotonically from `0` through `ceil(duration_sec * fps)-1`; ffmpeg’s filter applies the timeline offset. A feeder must not pre-render the full composition or write its frames to CAS.

On Linux, use inherited descriptors with `pass_fds`. On Windows, keep `frame_engine=pull` disabled until a named-pipe implementation has equivalent lifecycle tests; the default materializer remains the cross-platform path. A pull failure is a render failure unless the caller explicitly sets `OPEN_EDIT_FRAME_PULL_FALLBACK=materialize`.

- [ ] **Step 5: Wire the feature gate and diagnostics.**

The orchestrator uses frame pull only when all of these are true:

```text
OPEN_EDIT_REMOTION_FRAME_ENGINE == "pull"
mode == "proxy" unless OPEN_EDIT_ALLOW_EXPERIMENTAL_FRAME_PULL=1
host protocol/API probe passed
platform feeder support passed
```

Otherwise it uses the Task 4 materializer. Record `remotion_frame_pull` with `requested`, `enabled`, `frames_requested`, `elapsed_sec`, `fallback`, and bounded error fields. The default remains `materialize`; final export does not silently switch engines.

- [ ] **Step 6: Run protocol/pipe parity tests.**

Run:

```bash
pytest -q tests/test_remotion_frame_engine.py tests/test_render/test_pipe_builder.py \
  tests/test_render/test_run_pipe.py
```

When ffmpeg is available, render a tiny base clip with a deterministic fake frame server through both paths and compare selected output-frame hashes, alpha blending, frame count, and PTS. The pull output must not create a composition artifact in `remotion/out/cache`; the materialize path must continue to create the expected `.mp4`, `.webm`, or `.mov`.

- [ ] **Step 7: Commit only after parity and lifecycle tests pass.**

```bash
git add open_edit/render/remotion/frame_feeder.py \
  open_edit/render/pipe_builder.py open_edit/render/melt_runner.py \
  open_edit/render/timeline_plan.py open_edit/render/orchestrator.py \
  tests/test_remotion_frame_engine.py tests/test_render/test_pipe_builder.py \
  tests/test_render/test_run_pipe.py
git commit -m "feat: gate same-pass remotion frame overlays"
```

---
