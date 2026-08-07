# Task 5 Brief

### Task 5: Add preview profiles and independent video/audio/mux commands

**Files:**
- Create: `open_edit/render/preview_pipe.py`
- Modify: `open_edit/render/profiles.py`
- Read and regression-test: `open_edit/render/pipe_builder.py`
- Test: `tests/test_preview_pipe.py`
- Regression tests: `tests/test_render/test_pipe_builder.py`, `tests/test_render/test_encoder.py`

**Interfaces:**
- Consumes: `RenderProfile`, `EncoderSpec`, sliced local MLT XML, `OverlayClip` values, crop frame counts, and plane selection.
- Produces:

```python
@dataclass(frozen=True)
class PreviewPipeCommands:
    video_cmd: list[str] | None
    audio_cmd: list[str] | None
    mux_cmd: list[str] | None
    video_output: Path | None
    audio_output: Path | None
    playback_output: Path

def build_preview_pipe_commands(
    *,
    melt_bin: str,
    xml_path: Path,
    video_output: Path | None,
    audio_output: Path | None,
    playback_output: Path,
    profile: RenderProfile,
    encoder: EncoderSpec,
    overlays: Sequence[OverlayClip],
    crop_head_frames: int,
    crop_tail_frames: int,
    core_frames: int,
    media: Literal["video", "audio", "both"],
) -> PreviewPipeCommands:
    ...
```

- [ ] **Step 1: Write failing command assertions.**

```python
def test_video_command_preserves_rawvideo_contract_and_core_trim(tmp_path):
    cmds = build_preview_pipe_commands(
        melt_bin="melt", xml_path=tmp_path / "chunk.mlt",
        video_output=tmp_path / "v.mp4", audio_output=None,
        playback_output=tmp_path / "p.mp4",
        profile=preview_profile(), encoder=h264_encoder(),
        overlays=[], crop_head_frames=2, crop_tail_frames=1, core_frames=30,
        media="video",
    )
    assert "f=rawvideo" in cmds.video_cmd
    assert "trim=start_frame=2" in " ".join(cmds.video_cmd or [])
    assert "-frames:v" in cmds.video_cmd and "30" in cmds.video_cmd
    assert cmds.audio_cmd is None
    assert cmds.mux_cmd is None

def test_audio_only_command_does_not_build_video_pipe(tmp_path):
    cmds = build_preview_pipe_commands(
        melt_bin="melt", xml_path=tmp_path / "chunk.mlt",
        video_output=None, audio_output=tmp_path / "a.m4a",
        playback_output=tmp_path / "p.mp4",
        profile=preview_profile(), encoder=h264_encoder(),
        overlays=[], crop_head_frames=0, crop_tail_frames=0, core_frames=30,
        media="audio",
    )
    assert cmds.video_cmd is None
    assert cmds.audio_cmd is not None
    assert cmds.mux_cmd is None

def test_mux_command_copies_selected_planes(tmp_path):
    cmds = build_preview_pipe_commands(
        melt_bin="melt", xml_path=tmp_path / "chunk.mlt",
        video_output=tmp_path / "v.mp4", audio_output=tmp_path / "a.m4a",
        playback_output=tmp_path / "p.mp4",
        profile=preview_profile(), encoder=h264_encoder(),
        overlays=[], crop_head_frames=0, crop_tail_frames=0, core_frames=30,
        media="both",
    )
    assert cmds.mux_cmd[:2] == ["ffmpeg", "-y"]
    assert "-c:v" in cmds.mux_cmd and "copy" in cmds.mux_cmd
    assert "-c:a" in cmds.mux_cmd and "copy" in cmds.mux_cmd
```

- [ ] **Step 2: Run the focused tests and verify the new command builder is missing.**

Run: `pytest tests/test_preview_pipe.py -q`

Expected: FAIL.

- [ ] **Step 3: Add the `preview_chunk` profile.** Start at the current fast proxy dimensions (640×360), project FPS, H.264/AAC browser-safe codecs, and a lower audio bitrate. Give video, audio, and mux settings separate stable profile fingerprints. Reject client attempts to change chunk geometry through arbitrary profile overrides.

- [ ] **Step 4: Implement the three command forms.** Reuse the existing rawvideo and overlay filter helpers; preserve `f=rawvideo`, `vcodec=rawvideo`, profile size, and FPS. Video output must trim `crop_head_frames` and limit to exactly `core_frames`; audio output must be independently encoded and core-trimmed to the same duration. Mux must use `-c:v copy -c:a copy -shortest` and write only to a temporary output path before validation.

- [ ] **Step 5: Run focused and regression tests.**

Run: `pytest tests/test_preview_pipe.py tests/test_render/test_pipe_builder.py tests/test_render/test_encoder.py -q`

Expected: PASS with existing proxy/final command lists unchanged.

- [ ] **Step 6: Commit the independent plane commands.**

```bash
git add open_edit/render/preview_pipe.py open_edit/render/profiles.py tests/test_preview_pipe.py tests/test_render/test_pipe_builder.py tests/test_render/test_encoder.py
git commit -m "feat: build independent preview plane commands"
```
