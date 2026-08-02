"""Tests for the MLT XML emitter."""
from pathlib import Path

import pytest

from open_edit.ir.apply import apply_operation
from open_edit.ir.derive import derive_timeline
from open_edit.ir.types import (
    AddClipOp, AddEffectOp, AddTransitionOp, Asset, Project,
    SetKeyframeOp, Timeline, Track, Clip,
)
from open_edit.render.emitter import emit_timeline, EmitterConfig
from open_edit.render.timeline_plan import build_render_plan
from open_edit.storage.assets import AssetStore


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
    assert 'service="luma"' in xml


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
    assert xml.count("<track ") >= 2


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


def test_emit_timeline_hwaccel_properties(tmp_path: Path) -> None:
    asset = Asset(asset_hash="abc123", type="video", original_path="a.mp4",
                  stored_path="a.mp4", duration_sec=1.0, width=1920, height=1080,
                  alignment=[])
    clip = Clip(clip_id="c1", asset_hash="abc123", track_id="v1", track_kind="video",
                position_sec=0.0, in_point_sec=0.0, out_point_sec=1.0)
    timeline = Timeline(
        duration_sec=1.0, assets=[asset],
        tracks=[Track(track_id="v1", kind="video", clips=[clip])],
    )
    xml_off = emit_timeline(timeline, EmitterConfig())
    xml_on = emit_timeline(timeline, EmitterConfig(), hwaccel=True)
    assert "hwaccel" not in xml_off
    assert 'name="hwaccel">cuda' in xml_on
    assert 'name="hwaccel_device">0' in xml_on


def test_final_plan_emits_canonical_source_not_ready_proxy(tmp_path: Path) -> None:
    store = AssetStore(tmp_path / ".open_edit" / "assets")
    asset_hash = "a" * 64
    proxy_hash = "b" * 64
    canonical_path = store._cas_path(asset_hash)
    proxy_path = store._cas_path(proxy_hash)
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_path.write_bytes(b"canonical")
    proxy_path.parent.mkdir(parents=True, exist_ok=True)
    proxy_path.write_bytes(b"proxy")
    asset = _asset(asset_hash).model_copy(
        update={
            "stored_path": str(canonical_path),
            "proxy_hash": proxy_hash,
            "proxy_profile": "source_proxy_360_v1",
            "proxy_status": "ready",
        }
    )
    store._sidecar_path(asset_hash).write_text(asset.model_dump_json())
    op = AddClipOp(
        author="user",
        asset_hash=asset_hash,
        track_id="v1",
        position_sec=0.0,
        in_point_sec=0.0,
        out_point_sec=2.0,
    )
    timeline = apply_operation(Timeline(), op)
    plan = build_render_plan(
        timeline,
        [op],
        store,
        "final",
        emission_profile="final",
        enqueue_missing_proxies=False,
    )

    xml = emit_timeline(
        plan.melt_timeline,
        EmitterConfig(profile={"width": 320, "height": 240, "frame_rate_num": 30, "frame_rate_den": 1}),
        asset_paths=plan.asset_paths,
    )

    assert f'resource="{canonical_path}"' in xml
    assert str(proxy_path) not in xml
