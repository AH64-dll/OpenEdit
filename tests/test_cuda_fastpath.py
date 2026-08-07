"""Tests for the CUDA fast path (pure-ffmpeg GPU render for simple timelines)."""
import shutil
from pathlib import Path

import pytest

from open_edit.ir.types import Clip, Effect, Timeline, Track
from open_edit.render.cuda_fastpath import (
    build_cuda_fastpath_command,
    timeline_supports_cuda_fastpath,
)
from open_edit.render.encoder import EncoderSpec
from open_edit.render.profiles import RenderProfile

TESTDATA = Path(__file__).parent / "testdata" / "raw_videos"


def _simple_timeline(duration: float = 2.0) -> Timeline:
    return Timeline(
        tracks=[
            Track(
                track_id="v1",
                kind="video",
                clips=[
                    Clip(
                        clip_id="c1",
                        asset_hash="h1",
                        track_id="v1",
                        track_kind="video",
                        position_sec=0.0,
                        in_point_sec=0.0,
                        out_point_sec=duration,
                    )
                ],
            )
        ],
        duration_sec=duration,
    )


def _profile() -> RenderProfile:
    return RenderProfile(
        name="1080p30",
        width=1920,
        height=1080,
        frame_rate_num=30,
        frame_rate_den=1,
        scale="1920x1080",
        acodec="aac",
        ab="192k",
        quality="standard",
    )


def test_timeline_supports_simple() -> None:
    assert timeline_supports_cuda_fastpath(_simple_timeline()) is True


def test_timeline_rejects_offsets() -> None:
    tl = _simple_timeline()
    tl.tracks[0].clips[0].position_sec = 1.0
    assert timeline_supports_cuda_fastpath(tl) is False


def test_timeline_rejects_in_point_trim() -> None:
    tl = _simple_timeline()
    tl.tracks[0].clips[0].in_point_sec = 0.5
    assert timeline_supports_cuda_fastpath(tl) is False


def test_timeline_rejects_multiple_clips() -> None:
    tl = _simple_timeline()
    tl.tracks[0].clips.append(
        Clip(
            clip_id="c2",
            asset_hash="h2",
            track_id="v1",
            track_kind="video",
            position_sec=2.0,
            in_point_sec=0.0,
            out_point_sec=2.0,
        )
    )
    assert timeline_supports_cuda_fastpath(tl) is False


def test_timeline_rejects_clip_effects() -> None:
    from open_edit.ir.types import Effect

    tl = _simple_timeline()
    tl.tracks[0].clips[0].effects = [
        Effect(effect_id="e1", effect_type="brightness")
    ]
    assert timeline_supports_cuda_fastpath(tl) is False


def test_timeline_allows_audio_only_effects() -> None:
    # volume/gain is applied by the separate melt-audio pass, so it must not
    # disqualify the pure-ffmpeg CUDA video path (a real editing hot path:
    # gain edits used to force a whole-file melt render).
    tl = _simple_timeline()
    tl.tracks[0].clips[0].effects = [
        Effect(effect_id="e1", effect_type="volume", params={"target_dbfs": -3.0})
    ]
    assert timeline_supports_cuda_fastpath(tl) is True


def test_timeline_still_rejects_video_effects() -> None:
    tl = _simple_timeline()
    tl.tracks[0].clips[0].effects = [
        Effect(effect_id="e1", effect_type="brightness", params={"brightness": 1.1})
    ]
    assert timeline_supports_cuda_fastpath(tl) is False


def test_timeline_rejects_track_effects() -> None:
    from open_edit.ir.types import Effect

    tl = _simple_timeline()
    tl.tracks[0].effects = [
        Effect(effect_id="e1", effect_type="brightness")
    ]
    assert timeline_supports_cuda_fastpath(tl) is False


def test_timeline_rejects_overlays() -> None:
    from open_edit.ir.types import HtmlOverlay

    tl = _simple_timeline()
    tl.overlays = [
        HtmlOverlay(
            id="o1",
            template_path="/tmp/t.html",
            variables={},
            position_sec=0.0,
            duration_sec=1.0,
        )
    ]
    assert timeline_supports_cuda_fastpath(tl) is False


def test_timeline_rejects_remotion() -> None:
    tl = _simple_timeline()
    tl.remotion_compositions = [object()]  # type: ignore[list-item]
    assert timeline_supports_cuda_fastpath(tl) is False


def test_build_command_requires_media_file(tmp_path: Path) -> None:
    tl = _simple_timeline()
    cmd = build_cuda_fastpath_command(
        tl, {"h1": "/nonexistent.mp4"}, tmp_path / "out.mp4",
        _profile(), EncoderSpec("h264_nvenc", (), ()),
    )
    assert cmd is None


def test_build_command_uses_scale_override(tmp_path: Path) -> None:
    clip_a = TESTDATA / "clip_a.mp4"
    if not clip_a.is_file():
        pytest.skip("clip_a.mp4 missing")
    tl = _simple_timeline()
    profile = _profile()
    profile.scale = "320x180"
    cmd = build_cuda_fastpath_command(
        tl, {"h1": str(clip_a)}, tmp_path / "out.mp4",
        profile, EncoderSpec("h264_nvenc", (), ()),
    )
    assert cmd is not None
    # scale_cuda must use the override resolution, not the profile width.
    assert any("scale_cuda=320:180" in part for part in cmd)


def test_build_command_has_cuda_flags(tmp_path: Path) -> None:
    clip_a = TESTDATA / "clip_a.mp4"
    if not clip_a.is_file():
        pytest.skip("clip_a.mp4 missing")
    tl = _simple_timeline()
    cmd = build_cuda_fastpath_command(
        tl, {"h1": str(clip_a)}, tmp_path / "out.mp4",
        _profile(), EncoderSpec("h264_nvenc", (), ()),
    )
    assert cmd is not None
    assert "-hwaccel" in cmd and "cuda" in cmd
    assert any("scale_cuda" in part for part in cmd)
