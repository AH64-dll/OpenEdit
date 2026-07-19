"""Tests for the MLT XML emitter."""
import pytest

from open_edit.ir.apply import apply_operation, derive_timeline
from open_edit.ir.types import (
    AddClipOp, AddEffectOp, AddTransitionOp, Asset, Project,
    SetKeyframeOp, Timeline, Track, Clip,
)
from open_edit.render.emitter import emit_timeline, EmitterConfig


def _asset(asset_hash: str = "abc", duration_sec: float = 2.0) -> Asset:
    return Asset(
        asset_hash=asset_hash,
        original_path=f"/tmp/{asset_hash}.mp4",
        stored_path=f"/tmp/{asset_hash}.mp4",
        type="video",
        duration_sec=duration_sec,
        fps=30.0,
        width=320,
        height=240,
    )


def test_emitter_produces_valid_xml_declaration() -> None:
    timeline = Timeline()
    xml = emit_timeline(timeline, EmitterConfig())
    assert xml.startswith("<?xml")
    assert "<mlt" in xml
    assert "</mlt>" in xml


def test_emitter_includes_profile_element() -> None:
    timeline = Timeline()
    xml = emit_timeline(timeline, EmitterConfig(
        profile={"width": 1920, "height": 1080, "frame_rate_num": 30, "frame_rate_den": 1}
    ))
    assert 'width="1920"' in xml
    assert 'height="1080"' in xml
    assert 'frame_rate_num="30"' in xml


def test_emitter_no_kdenlive_namespaces() -> None:
    timeline = Timeline()
    xml = emit_timeline(timeline, EmitterConfig())
    assert "kdenlive:" not in xml


def test_emitter_emits_clips_as_entries() -> None:
    timeline = Timeline()
    op = AddClipOp(
        author="user", asset_hash="abc", track_id="v1",
        position_sec=0.0, in_point_sec=0.0, out_point_sec=2.0,
    )
    timeline = apply_operation(timeline, op)
    xml = emit_timeline(timeline, EmitterConfig(
        profile={"width": 320, "height": 240, "frame_rate_num": 30, "frame_rate_den": 1}
    ))
    assert "<entry" in xml
    assert 'producer="producer_abc"' in xml
    assert 'in="0"' in xml
    assert 'out="60"' in xml  # 2s @ 30fps = 60 frames


def test_emitter_emits_transitions() -> None:
    timeline = Timeline()
    a = AddClipOp(
        author="user", asset_hash="a", track_id="v1",
        position_sec=0.0, in_point_sec=0.0, out_point_sec=2.0,
    )
    b = AddClipOp(
        author="user", asset_hash="b", track_id="v1",
        position_sec=2.0, in_point_sec=0.0, out_point_sec=2.0,
    )
    timeline = apply_operation(timeline, a)
    timeline = apply_operation(timeline, b)
    t = AddTransitionOp(
        author="user", clip_a_id=a.clip_id, clip_b_id=b.clip_id,
        transition_type="luma", duration_sec=1.0,
    )
    timeline = apply_operation(timeline, t)
    xml = emit_timeline(timeline, EmitterConfig(
        profile={"width": 320, "height": 240, "frame_rate_num": 30, "frame_rate_den": 1}
    ))
    assert "<transition" in xml
    assert 'lti_rect=""' not in xml  # not blank


def test_emitter_emits_effects_as_filters() -> None:
    timeline = Timeline()
    op = AddClipOp(
        author="user", asset_hash="abc", track_id="v1",
        position_sec=0.0, in_point_sec=0.0, out_point_sec=2.0,
    )
    timeline = apply_operation(timeline, op)
    eff = AddEffectOp(
        author="user", target_kind="clip", target_id=op.clip_id,
        effect_type="volume", params={"gain": 0.5},
    )
    timeline = apply_operation(timeline, eff)
    xml = emit_timeline(timeline, EmitterConfig(
        profile={"width": 320, "height": 240, "frame_rate_num": 30, "frame_rate_den": 1}
    ))
    assert "<filter" in xml
    assert 'service="volume"' in xml
    assert "0.5" in xml  # gain value in the filter


def test_emitter_emits_audio_tracks_separately() -> None:
    timeline = Timeline()
    video_clip = AddClipOp(
        author="user", asset_hash="v", track_id="v1",
        position_sec=0.0, in_point_sec=0.0, out_point_sec=2.0,
    )
    audio_clip = AddClipOp(
        author="user", asset_hash="a", track_id="audio_1",
        track_kind="audio", position_sec=0.0, in_point_sec=0.0, out_point_sec=2.0,
    )
    timeline = apply_operation(timeline, video_clip)
    timeline = apply_operation(timeline, audio_clip)
    xml = emit_timeline(timeline, EmitterConfig(
        profile={"width": 320, "height": 240, "frame_rate_num": 30, "frame_rate_den": 1}
    ))
    # Should have a multitrack with both video and audio tracks
    assert xml.count("<track>") >= 2


def test_emitter_includes_producers() -> None:
    timeline = Timeline()
    op = AddClipOp(
        author="user", asset_hash="abc", track_id="v1",
        position_sec=0.0, in_point_sec=0.0, out_point_sec=2.0,
    )
    timeline = apply_operation(timeline, op)
    xml = emit_timeline(
        timeline,
        EmitterConfig(
            profile={"width": 320, "height": 240, "frame_rate_num": 30, "frame_rate_den": 1}
        ),
        asset_paths={"abc": "/tmp/abc.mp4"},
    )
    assert "<producer" in xml
    assert 'id="producer_abc"' in xml
    assert 'resource="/tmp/abc.mp4"' in xml
