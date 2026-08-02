from __future__ import annotations

import pytest

from open_edit.ir.types import (
    AddRemotionCompositionOp,
    Clip,
    Effect,
    FreeFormCodeOp,
    HtmlOverlay,
    RemotionComposition,
    SetAudioGainOp,
    Timeline,
    Track,
)
from open_edit.render.preview_manifest import PreviewRange
from open_edit.render.preview_invalidation import (
    classify_operation_planes,
    compute_chunk_fingerprints,
    make_chunk_windows,
    select_dirty_windows,
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


def _three_second_timeline() -> Timeline:
    return Timeline(
        duration_sec=3.0,
        tracks=[
            Track(
                track_id="a1",
                kind="audio",
                clips=[
                    _clip(
                        clip_id="a1",
                        track_id="a1",
                        track_kind="audio",
                        in_point=0.0,
                        out_point=3.0,
                    ),
                ],
            ),
        ],
    )


def _fingerprints(
    *,
    old_timeline: Timeline | None,
    new_timeline: Timeline,
    operations: list,
    old_graph_hash: str | None = "old",
    new_graph_hash: str = "new",
):
    return compute_chunk_fingerprints(
        old_timeline=old_timeline,
        new_timeline=new_timeline,
        old_graph_hash=old_graph_hash,
        new_graph_hash=new_graph_hash,
        operations=operations,
        windows=make_chunk_windows(90, 30, 1),
        profile_fingerprint="profile",
        content_fingerprint="content",
    )


def test_gain_edit_keeps_video_key_and_dirties_audio() -> None:
    timeline = _three_second_timeline()
    baseline = _fingerprints(
        old_timeline=timeline,
        new_timeline=timeline,
        operations=[],
        old_graph_hash="same",
        new_graph_hash="same",
    )[0]
    gained = _fingerprints(
        old_timeline=timeline,
        new_timeline=timeline,
        operations=[
            SetAudioGainOp(
                clip_id="a1",
                gain_db=-3,
                author="user",
            ),
        ],
    )[0]

    assert gained.video_key == baseline.video_key
    assert gained.video_dirty is False
    assert gained.audio_key != baseline.audio_key
    assert gained.audio_dirty is True


def test_audio_effect_on_video_clip_is_excluded_from_video_key() -> None:
    old = Timeline(
        duration_sec=3.0,
        tracks=[Track(track_id="v1", kind="video", clips=[_clip(clip_id="v1")])],
    )
    changed = old.model_copy(deep=True)
    changed.tracks[0].clips[0].effects = [
        Effect(effect_id="gain", effect_type="volume", params={"gain": 0.5}),
    ]
    got = _fingerprints(
        old_timeline=old,
        new_timeline=changed,
        operations=[SetAudioGainOp(clip_id="v1", gain_db=-6, author="user")],
    )[0]

    assert got.video_dirty is False
    assert got.audio_dirty is True


def test_remotion_edit_dirties_only_overlapping_video_windows() -> None:
    old = Timeline(duration_sec=3.0)
    new = old.model_copy(
        update={
            "remotion_compositions": [
                RemotionComposition(
                    id="comp-1",
                    entry_point="src/index.ts",
                    composition_id="Title",
                    position_sec=2.0,
                    duration_sec=0.5,
                ),
            ],
        },
    )
    got = _fingerprints(
        old_timeline=old,
        new_timeline=new,
        operations=[
            AddRemotionCompositionOp(
                entry_point="src/index.ts",
                composition_id="Title",
                composition_uid="comp-1",
                position_sec=2.0,
                duration_sec=0.5,
                author="user",
            ),
        ],
    )

    assert [item.video_dirty for item in got] == [False, False, True]
    assert [item.audio_dirty for item in got] == [False, False, False]
    assert got[2].composition_uids == ("comp-1",)


def test_unknown_free_form_edit_invalidates_every_plane() -> None:
    got = _fingerprints(
        old_timeline=_three_second_timeline(),
        new_timeline=_three_second_timeline(),
        operations=[
            FreeFormCodeOp(
                code="mutate timeline",
                label="unknown",
                author="user",
            ),
        ],
    )

    assert all(item.video_dirty and item.audio_dirty for item in got)


def test_missing_old_snapshot_is_conservative() -> None:
    got = _fingerprints(
        old_timeline=None,
        new_timeline=_three_second_timeline(),
        operations=[],
        old_graph_hash=None,
    )

    assert all(item.video_dirty and item.audio_dirty for item in got)


def test_operation_plane_classification_uses_target_track() -> None:
    timeline = _three_second_timeline()

    assert classify_operation_planes(
        SetAudioGainOp(clip_id="a1", gain_db=-3, author="user"),
        timeline,
    ) == frozenset({"audio"})
    assert classify_operation_planes(
        AddRemotionCompositionOp(
            entry_point="src/index.ts",
            composition_id="Title",
            position_sec=0.0,
            duration_sec=1.0,
            author="user",
        ),
        timeline,
    ) == frozenset({"video"})


def test_select_dirty_windows_prioritizes_requested_range_and_neighbors() -> None:
    fingerprints = _fingerprints(
        old_timeline=_three_second_timeline(),
        new_timeline=_three_second_timeline(),
        operations=[
            FreeFormCodeOp(
                code="mutate timeline",
                label="unknown",
                author="user",
            ),
        ],
    )

    selected = select_dirty_windows(
        fingerprints,
        [PreviewRange(start_sec=2.0, end_sec=2.1)],
        background=False,
    )

    assert selected[0] == 2
    assert set(selected) == {1, 2}
