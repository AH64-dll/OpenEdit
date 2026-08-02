"""Pipe command construction: melt rawvideo + audio pass + ffmpeg single encode."""
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

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


def test_blur_under_preserves_base_before_delayed_overlay(tmp_path: Path):
    """A future focus window must not discard earlier base frames."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("ffmpeg is required for the blur timing regression")

    overlay_png = tmp_path / "overlay.png"
    png_probe = subprocess.run(
        [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=red:s=64x64:d=1",
            "-frames:v", "1", "-vf", "format=rgba,colorchannelmixer=aa=0.5",
            str(overlay_png),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if png_probe.returncode != 0:
        pytest.skip(f"FFmpeg RGBA PNG unavailable: {png_probe.stderr}")

    overlay_mov = tmp_path / "overlay.mov"
    overlay_probe = subprocess.run(
        [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-loop", "1", "-framerate", "30", "-i", str(overlay_png),
            "-t", "1", "-c:v", "prores_ks", "-profile:v", "4444",
            "-pix_fmt", "yuva444p10le", str(overlay_mov),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if overlay_probe.returncode != 0:
        pytest.skip(f"FFmpeg ProRes 4444 unavailable: {overlay_probe.stderr}")

    profile = select_profile("fast_proxy").model_copy(
        update={"width": 128, "height": 128},
    )
    cmds = build_pipe_commands(
        "melt",
        tmp_path / "timeline.mlt",
        tmp_path / "composite.mp4",
        profile,
        select_encoder("cpu", final=False),
        [
            OverlayClip(
                position_sec=2.0,
                duration_sec=1.0,
                media_path=overlay_mov,
                blur_under=True,
            ),
        ],
        audio_bitrate="96k",
        workdir=tmp_path,
    )
    with wave.open(str(cmds.audio_wav), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(48_000)
        audio.writeframes(b"\0\0" * 48_000 * 4)

    frame = b"".join(
        bytes([64 + (index * 2) % 160]) * (128 * 128)
        + b"\x80" * (128 * 128 // 2)
        for index in range(120)
    )
    result = subprocess.run(
        cmds.ffmpeg_cmd, input=frame, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")

    samples = []
    for timestamp in ("0", "1"):
        sample = subprocess.run(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error",
                "-ss", timestamp, "-i", str(tmp_path / "composite.mp4"),
                "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-",
            ],
            capture_output=True,
            check=True,
            timeout=30,
        )
        samples.append(sum(sample.stdout) / len(sample.stdout))
    assert abs(samples[1] - samples[0]) > 10


def test_pipe_commands_shape(tmp_path: Path):
    profile, spec, overlays = _fixture()
    cmds = build_pipe_commands(
        "melt", Path("t.mlt"), tmp_path / "out.mp4", profile, spec, overlays,
        audio_bitrate="160k", workdir=tmp_path,
    )
    assert cmds.melt_video_cmd[0] == "melt"
    assert "avformat:pipe:" in cmds.melt_video_cmd
    assert "f=rawvideo" in cmds.melt_video_cmd
    assert "format=rawvideo" not in cmds.melt_video_cmd
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


def test_full_alpha_composite_preserves_transparent_overlay_pixels(tmp_path: Path):
    """The actual burn-in graph must blend alpha instead of producing black."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("ffmpeg is required for the alpha composite regression")

    overlay_png = tmp_path / "overlay.png"
    png_probe = subprocess.run(
        [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=red:s=64x64:d=1",
            "-frames:v", "1", "-vf", "format=rgba,colorchannelmixer=aa=0.5",
            str(overlay_png),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if png_probe.returncode != 0:
        pytest.skip(f"FFmpeg RGBA PNG unavailable: {png_probe.stderr}")
    overlay_mov = tmp_path / "overlay.mov"
    overlay_probe = subprocess.run(
        [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-loop", "1", "-framerate", "30", "-i", str(overlay_png),
            "-t", "1", "-c:v", "prores_ks", "-profile:v", "4444",
            "-pix_fmt", "yuva444p10le", str(overlay_mov),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if overlay_probe.returncode != 0:
        pytest.skip(f"FFmpeg ProRes 4444 unavailable: {overlay_probe.stderr}")

    profile = select_profile("fast_proxy").model_copy(
        update={"width": 64, "height": 64},
    )
    cmds = build_pipe_commands(
        "melt",
        tmp_path / "timeline.mlt",
        tmp_path / "composite.mp4",
        profile,
        select_encoder("cpu", final=False),
        [
            OverlayClip(
                position_sec=0.0,
                duration_sec=1.0,
                media_path=overlay_mov,
                blur_under=False,
                alpha=True,
            ),
        ],
        audio_bitrate="96k",
        workdir=tmp_path,
    )

    with wave.open(str(cmds.audio_wav), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(48_000)
        audio.writeframes(b"\0\0" * 48_000)

    # Gray yuv420p frames make the expected half-red blend unambiguous.
    frame = b"\x80" * (64 * 64) + b"\x80" * (32 * 32 * 2)
    result = subprocess.run(
        cmds.ffmpeg_cmd,
        input=frame * 30,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")

    extract = subprocess.run(
        [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(tmp_path / "composite.mp4"), "-frames:v", "1",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
        ],
        capture_output=True,
        timeout=30,
    )
    assert extract.returncode == 0, extract.stderr.decode(errors="replace")
    pixel_offset = (32 * 64 + 32) * 3
    red, green, blue = extract.stdout[pixel_offset:pixel_offset + 3]
    assert red > green + 30
    assert green > 0
    assert blue > 0
