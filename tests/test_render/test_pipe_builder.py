"""Pipe command construction: melt rawvideo + audio pass + ffmpeg single encode."""
from pathlib import Path

from open_edit.render.encoder import select_encoder
from open_edit.render.pipe_builder import (
    OverlayClip,
    build_pipe_commands,
    overlay_filter_chain,
)
from open_edit.render.profiles import select_profile


def _fixture():
    profile = select_profile("720p30")
    spec = select_encoder("gpu", final=True)
    overlays = [
        OverlayClip(position_sec=1.0, duration_sec=2.0,
                    media_path=Path("/tmp/ov.mov"), label="card"),
    ]
    return profile, spec, overlays


def test_overlay_filter_chain_builds_inputs():
    overlays = [OverlayClip(position_sec=1.0, duration_sec=2.0,
                            media_path=Path("/tmp/ov.mov"))]
    filters = overlay_filter_chain(overlays, 1280, 720)
    assert isinstance(filters, list) and filters
    assert "overlay=" in "".join(filters)


def test_overlay_filter_chain_blur_under_prepass():
    overlays = [OverlayClip(position_sec=1.0, duration_sec=2.0,
                            media_path=Path("/tmp/ov.mov"), blur_under=True)]
    filters = overlay_filter_chain(overlays, 1280, 720)
    chain = ";".join(filters)
    assert "split=2" in chain
    assert "boxblur=20:10" in chain
    assert "enable='between(t\\,1.000\\,3.000)'" in chain
    assert chain.startswith("[0:v]split=2[sharp][toblur]")
    assert "[base]" in chain
    # blur windows across several overlays OR together
    overlays = [
        OverlayClip(position_sec=1.0, duration_sec=1.0,
                    media_path=Path("/tmp/a.mov"), blur_under=True),
        OverlayClip(position_sec=5.0, duration_sec=2.0,
                    media_path=Path("/tmp/b.mov"), blur_under=False),
        OverlayClip(position_sec=9.0, duration_sec=1.0,
                    media_path=Path("/tmp/c.mov"), blur_under=True),
    ]
    chain = ";".join(overlay_filter_chain(overlays, 1280, 720))
    assert "between(t\\,1.000\\,2.000)+between(t\\,9.000\\,10.000)" in chain


def test_overlay_filter_chain_no_blur_under():
    overlays = [OverlayClip(position_sec=1.0, duration_sec=2.0,
                            media_path=Path("/tmp/ov.mov"), blur_under=False)]
    filters = overlay_filter_chain(overlays, 1280, 720)
    chain = ";".join(filters)
    assert "split=2" not in chain
    assert "boxblur=20:10" not in chain
    assert "[0:v][ov1]overlay=0:0" in chain
    assert "[base]" not in chain


def test_pipe_commands_shape(tmp_path: Path):
    profile, spec, overlays = _fixture()
    cmds = build_pipe_commands(
        "melt", Path("t.mlt"), tmp_path / "out.mp4", profile, spec, overlays,
        audio_bitrate="160k", workdir=tmp_path,
    )
    assert cmds.melt_video_cmd[0] == "melt"
    assert "avformat:pipe:" in cmds.melt_video_cmd
    assert "rawvideo" in " ".join(cmds.melt_video_cmd)
    assert "format=wav" in cmds.melt_audio_cmd
    assert "video_off=1" in cmds.melt_audio_cmd
    assert "-f" in cmds.ffmpeg_cmd and "rawvideo" in cmds.ffmpeg_cmd
    assert cmds.ffmpeg_cmd[0] == "ffmpeg"
    assert str(tmp_path / "out.mp4") in cmds.ffmpeg_cmd
    assert str(cmds.audio_wav) in " ".join(cmds.melt_audio_cmd)
    assert " ".join(cmds.ffmpeg_cmd).count("-i") >= 2  # pipe + audio (+ overlays)


def test_pipe_commands_no_overlays(tmp_path: Path):
    profile, spec, _ = _fixture()
    cmds = build_pipe_commands(
        "melt", Path("t.mlt"), tmp_path / "out.mp4", profile, spec, [],
        audio_bitrate="160k", workdir=tmp_path,
    )
    assert "-map" in cmds.ffmpeg_cmd  # direct mapping, no filter_complex
    assert "filter_complex" not in cmds.ffmpeg_cmd


def test_pipe_commands_scale_override(tmp_path: Path):
    profile, spec, overlays = _fixture()
    profile = profile.model_copy(update={"scale": "640x360"})
    cmds = build_pipe_commands(
        "melt", Path("t.mlt"), tmp_path / "out.mp4", profile, spec, overlays,
        audio_bitrate="160k", workdir=tmp_path,
    )
    assert "s=640x360" in cmds.melt_video_cmd
    assert "-s" in cmds.ffmpeg_cmd and "640x360" in cmds.ffmpeg_cmd
