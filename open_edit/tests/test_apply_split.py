from open_edit.ir.types import Timeline, Track, Clip, Effect, SplitClipOp
from open_edit.ir.apply import apply_operation


def test_split_clip_effects_are_independent():
    clip = Clip(
        clip_id="c1",
        track_id="t1",
        track_kind="video",
        asset_hash="abc",
        position_sec=0.0,
        in_point_sec=0.0,
        out_point_sec=10.0,
        effects=[Effect(effect_id="e1", effect_type="volume", params={"db": "0"})],
    )
    timeline = Timeline(tracks=[Track(track_id="t1", kind="video", clips=[clip])])

    op = SplitClipOp(
        edit_id="e1",
        author="ai",
        timestamp="2026-01-01T00:00:00",
        parent_id=None,
        clip_id=clip.clip_id,
        at_sec=5.0,
        left_clip_id="left",
        right_clip_id="right",
    )

    result = apply_operation(timeline, op)
    left = result.tracks[0].clips[0]
    right = result.tracks[0].clips[1]

    left.effects.append(Effect(effect_id="e2", effect_type="brightness", params={"value": "0.5"}))
    assert len(right.effects) == 1, "Split clip shares effects list"


def test_split_no_effects():
    clip = Clip(
        clip_id="c1",
        track_id="t1",
        track_kind="video",
        asset_hash="abc",
        position_sec=0.0,
        in_point_sec=0.0,
        out_point_sec=10.0,
    )
    timeline = Timeline(tracks=[Track(track_id="t1", kind="video", clips=[clip])])

    op = SplitClipOp(
        edit_id="e1",
        author="ai",
        timestamp="2026-01-01T00:00:00",
        parent_id=None,
        clip_id=clip.clip_id,
        at_sec=5.0,
        left_clip_id="left",
        right_clip_id="right",
    )

    result = apply_operation(timeline, op)
    assert len(result.tracks[0].clips) == 2
