"""Command construction for independent preview video and audio planes."""
from pathlib import Path

import pytest

from open_edit.render.encoder import EncoderSpec
from open_edit.render.preview_pipe import build_preview_pipe_commands
from open_edit.render.profiles import (
    preview_chunk_profile,
    preview_profile_fingerprint,
    profile_with_quality,
    select_profile,
)


def preview_profile():
    return select_profile("preview_chunk")


def h264_encoder():
    return EncoderSpec(
        vcodec="libx264",
        melt_args=("crf=23", "preset=veryfast"),
        ffmpeg_args=("-preset", "veryfast", "-crf", "20"),
    )


def test_preview_chunk_profile_is_bounded_and_plane_fingerprints_differ():
    profile = preview_chunk_profile(24, 1)
    assert (profile.width, profile.height) == (640, 360)
    assert (profile.frame_rate_num, profile.frame_rate_den) == (24, 1)
    assert profile.vcodec == "libx264"
    assert profile.acodec == "aac"
    assert profile.ab == "96k"
    assert len({
        preview_profile_fingerprint(profile, plane)
        for plane in ("video", "audio", "mux")
    }) == 3


def test_preview_chunk_rejects_geometry_overrides():
    assert profile_with_quality(None, "preview-chunks").name == "preview_chunk"
    with pytest.raises(ValueError, match="geometry"):
        profile_with_quality(
            "preview_chunk", "proxy", overrides={"scale": "1280x720"},
        )


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
    assert "end_frame=32" in " ".join(cmds.video_cmd or [])
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
    assert str(cmds.playback_output) not in cmds.mux_cmd
    assert ".tmp" in cmds.mux_cmd[-1]
