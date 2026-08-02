from __future__ import annotations

import pytest

from open_edit.ir.types import (
    Clip,
    Effect,
    HtmlOverlay,
    RemotionComposition,
    Timeline,
    Track,
)
from open_edit.render.preview_invalidation import (
    make_chunk_windows,
    slice_timeline,
)


def _clip(
    *,
    clip_id: str = "clip",
    track_id: str = "v1",
    track_kind: str = "video",
    position: float = 0.0,
    in_point: float = 10.0,
    out_point: float = 14.0,
) -> Clip:
    return Clip(
        clip_id=clip_id,
        asset_hash=f"asset-{clip_id}",
        track_id=track_id,
        track_kind=track_kind,  # type: ignore[arg-type]
        position_sec=position,
        in_point_sec=in_point,
        out_point_sec=out_point,
    )


def test_chunk_windows_use_project_frames() -> None:
    windows = make_chunk_windows(75, 30, 1)

    assert [(w.start_frame, w.end_frame) for w in windows] == [
        (0, 30),
        (30, 60),
        (60, 75),
    ]
    assert windows[0].render_start_frame == 0
    assert windows[0].render_end_frame == 30
    assert windows[0].crop_head_frames == 0
    assert windows[0].crop_tail_frames == 0


def test_chunk_windows_keep_final_short_chunk_frame_aligned() -> None:
    windows = make_chunk_windows(75, 30000, 1001)

    assert [(w.start_frame, w.end_frame) for w in windows] == [
        (0, 30),
        (30, 60),
        (60, 75),
    ]
    assert all(
        value >= 0
        for window in windows
        for value in (
            window.start_frame,
            window.end_frame,
            window.render_start_frame,
            window.render_end_frame,
            window.crop_head_frames,
            window.crop_tail_frames,
        )
    )


def test_slice_crossing_clip_rebases_source_points() -> None:
    timeline = Timeline(
        duration_sec=4.0,
        tracks=[Track(track_id="v1", kind="video", clips=[_clip()])],
    )

    sliced = slice_timeline(
        timeline,
        render_start_frame=30,
        render_end_frame=60,
        fps_num=30,
        fps_den=1,
        plane="video",
    )

    clip = sliced.tracks[0].clips[0]
    assert clip.position_sec == pytest.approx(0.0)
    assert clip.in_point_sec == pytest.approx(11.0)
    assert clip.out_point_sec == pytest.approx(12.0)
    assert sliced.duration_sec == pytest.approx(1.0)


def test_slice_preserves_clip_effects_and_filters_audio_plane() -> None:
    effect = Effect(effect_id="fx", effect_type="volume", params={"gain": 0.5})
    video = _clip()
    video.effects = [effect]
    audio = _clip(
        clip_id="audio",
        track_id="a1",
        track_kind="audio",
        in_point=0.0,
        out_point=4.0,
    )
    timeline = Timeline(
        duration_sec=4.0,
        tracks=[
            Track(track_id="v1", kind="video", clips=[video]),
            Track(track_id="a1", kind="audio", clips=[audio]),
        ],
    )

    sliced = slice_timeline(
        timeline,
        render_start_frame=30,
        render_end_frame=60,
        fps_num=30,
        fps_den=1,
        plane="audio",
    )

    assert [track.kind for track in sliced.tracks] == ["audio"]
    assert sliced.tracks[0].clips[0].position_sec == pytest.approx(0.0)
    assert sliced.tracks[0].clips[0].in_point_sec == pytest.approx(1.0)
    assert sliced.tracks[0].clips[0].out_point_sec == pytest.approx(2.0)
    assert video.effects == [effect]


def test_slice_rebases_overlapping_html_and_remotion_overlays() -> None:
    timeline = Timeline(
        duration_sec=4.0,
        overlays=[
            HtmlOverlay(
                id="html",
                template_path="title.html",
                position_sec=0.5,
                duration_sec=2.0,
            ),
        ],
        remotion_compositions=[
            RemotionComposition(
                id="remotion",
                entry_point="src/index.ts",
                composition_id="Title",
                position_sec=0.5,
                duration_sec=2.0,
            ),
        ],
    )

    sliced = slice_timeline(
        timeline,
        render_start_frame=30,
        render_end_frame=60,
        fps_num=30,
        fps_den=1,
        plane="video",
    )

    assert sliced.overlays[0].position_sec == pytest.approx(0.0)
    assert sliced.overlays[0].duration_sec == pytest.approx(1.0)
    assert sliced.remotion_compositions[0].position_sec == pytest.approx(0.0)
    assert sliced.remotion_compositions[0].duration_sec == pytest.approx(1.0)
