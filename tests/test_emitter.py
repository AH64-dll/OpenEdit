from open_edit.ir.types import Timeline, Track, Clip, Project
from open_edit.render.emitter import emit_timeline, EmitterConfig


def test_emitter_includes_clip_positions():
    clip = Clip(
        clip_id="c1",
        track_id="t1",
        track_kind="video",
        asset_hash="abc123",
        in_point_sec=0.0,
        out_point_sec=10.0,
        position_sec=30.0,
    )
    timeline = Timeline(duration_sec=40.0, tracks=[Track(track_id="t1", kind="video", clips=[clip])])

    xml = emit_timeline(timeline, asset_paths={"abc123": "/path/to/video.mp4"})

    assert "<blank" in xml, "No blank entry found for position offset"
    assert 'video.mp4' in xml, "Clip entry missing"
