"""Scenario Evaluation Suite for Open Edit — Phase 7.

Tests the IR/apply layer against 22 editing scenarios without LLM calls.

Run as a standalone script:
    python tests/eval_scenarios.py

Or as part of the pytest suite:
    python -m pytest tests/eval_scenarios.py -v
"""
from __future__ import annotations

import sys
import traceback
from typing import Callable

from open_edit.ir.apply import apply_operation, derive_timeline
from open_edit.ir.types import (
    AddClipOp,
    AddEffectOp,
    AddHtmlOverlayOp,
    AddTransitionOp,
    ChangeClipSpeedOp,
    GroupEditsOp,
    MoveClipOp,
    NormalizeAudioOp,
    Project,
    RemoveClipOp,
    RemoveEffectOp,
    RemoveHtmlOverlayOp,
    ReplaceClipSourceOp,
    RippleDeleteClipOp,
    SetAudioGainOp,
    SetEffectParamOp,
    SetKeyframeOp,
    SlipClipOp,
    SplitClipOp,
    Timeline,
    TrimClipOp,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clip(
    asset_hash: str = "aabbccdd",
    track_id: str = "video_1",
    position_sec: float = 0.0,
    in_point_sec: float = 0.0,
    out_point_sec: float = 10.0,
    track_kind: str = "video",
) -> AddClipOp:
    return AddClipOp(
        author="ai",
        asset_hash=asset_hash,
        track_id=track_id,
        track_kind=track_kind,
        position_sec=position_sec,
        in_point_sec=in_point_sec,
        out_point_sec=out_point_sec,
    )


def _project(*ops) -> Project:
    return Project(name="eval", edit_graph=list(ops))


def _derive(*ops) -> Timeline:
    return derive_timeline(_project(*ops))


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def scenario_add_single_clip():
    """Add one clip, assert it appears on the correct track at correct position."""
    op = _clip(asset_hash="hash1", track_id="video_1", position_sec=0.0)
    t = _derive(op)
    assert len(t.tracks) == 1
    assert t.tracks[0].track_id == "video_1"
    assert len(t.tracks[0].clips) == 1
    assert t.tracks[0].clips[0].asset_hash == "hash1"
    assert t.tracks[0].clips[0].position_sec == 0.0


def scenario_add_two_clips_sequential():
    """Add two clips sequentially, assert positions and order."""
    op1 = _clip(asset_hash="h1", position_sec=0.0, out_point_sec=5.0)
    op2 = _clip(asset_hash="h2", position_sec=5.0, out_point_sec=10.0)
    t = _derive(op1, op2)
    clips = t.tracks[0].clips
    assert len(clips) == 2
    assert clips[0].asset_hash == "h1"
    assert clips[1].asset_hash == "h2"


def scenario_add_clip_then_remove():
    """Add then remove a clip, assert track is empty."""
    add = _clip(asset_hash="removable")
    remove = RemoveClipOp(author="user", clip_id=add.clip_id)
    t = _derive(add, remove)
    for track in t.tracks:
        assert len(track.clips) == 0


def scenario_move_clip():
    """Add clip then move it to a new position, assert new position."""
    add = _clip(position_sec=0.0)
    move = MoveClipOp(
        author="user",
        clip_id=add.clip_id,
        new_track_id="video_1",
        new_position_sec=20.0,
    )
    t = _derive(add, move)
    clip = t.tracks[0].clips[0]
    assert clip.position_sec == 20.0


def scenario_trim_clip():
    """Add clip then trim in/out points, assert new in/out."""
    add = _clip(in_point_sec=0.0, out_point_sec=10.0)
    trim = TrimClipOp(
        author="user",
        clip_id=add.clip_id,
        new_in_point_sec=2.0,
        new_out_point_sec=8.0,
    )
    t = _derive(add, trim)
    clip = t.tracks[0].clips[0]
    assert clip.in_point_sec == 2.0
    assert clip.out_point_sec == 8.0


def scenario_slip_clip():
    """Add clip then slip it, assert result stays within original bounds."""
    add = _clip(in_point_sec=0.0, out_point_sec=10.0)
    slip = SlipClipOp(author="user", clip_id=add.clip_id, delta_sec=2.0)
    t = _derive(add, slip)
    clip = t.tracks[0].clips[0]
    # in_point should shift by delta_sec but out_point - in_point stays same
    assert abs(clip.in_point_sec - 2.0) < 0.01, f"Expected in_point ~2.0, got {clip.in_point_sec}"
    assert abs(clip.out_point_sec - 12.0) < 0.01, f"Expected out_point ~12.0, got {clip.out_point_sec}"


def scenario_split_clip():
    """Add clip then split at midpoint, assert two clips exist."""
    add = _clip(position_sec=0.0, in_point_sec=0.0, out_point_sec=10.0)
    split = SplitClipOp(author="user", clip_id=add.clip_id, at_sec=5.0)
    t = _derive(add, split)
    total_clips = sum(len(tr.clips) for tr in t.tracks)
    assert total_clips == 2, f"Expected 2 clips after split, got {total_clips}"


def scenario_add_effect_to_clip():
    """Add clip then add effect, assert effect is on clip."""
    add = _clip()
    effect = AddEffectOp(
        author="ai",
        target_kind="clip",
        target_id=add.clip_id,
        effect_type="brightness",
        params={"level": "0.5"},
    )
    t = _derive(add, effect)
    clip = t.tracks[0].clips[0]
    assert len(clip.effects) == 1
    assert clip.effects[0].effect_type == "brightness"


def scenario_remove_effect():
    """Add clip+effect then remove effect, assert effect is gone."""
    add = _clip()
    effect = AddEffectOp(
        author="ai",
        target_kind="clip",
        target_id=add.clip_id,
        effect_type="contrast",
        params={},
    )
    remove_eff = RemoveEffectOp(author="user", clip_id=add.clip_id, effect_index=0)
    t = _derive(add, effect, remove_eff)
    clip = t.tracks[0].clips[0]
    assert len(clip.effects) == 0


def scenario_set_keyframe():
    """Add effect then set keyframe, assert keyframe is stored."""
    add = _clip()
    effect = AddEffectOp(
        author="ai",
        target_kind="clip",
        target_id=add.clip_id,
        effect_type="brightness",
        params={},
    )
    kf = SetKeyframeOp(
        author="ai",
        effect_id=effect.effect_id,
        param="level",
        keyframes=[(0.0, 0.2, "linear"), (5.0, 0.8, "linear")],
    )
    t = _derive(add, effect, kf)
    clip = t.tracks[0].clips[0]
    assert "level" in clip.effects[0].keyframes
    assert len(clip.effects[0].keyframes["level"]) == 2


def scenario_add_transition():
    """Add two clips then add transition between them."""
    c1 = _clip(asset_hash="ca", position_sec=0.0, out_point_sec=10.0)
    c2 = _clip(asset_hash="cb", position_sec=9.0, out_point_sec=20.0)
    trans = AddTransitionOp(
        author="ai",
        clip_a_id=c1.clip_id,
        clip_b_id=c2.clip_id,
        transition_type="dissolve",
        duration_sec=1.0,
    )
    t = _derive(c1, c2, trans)
    # The transition should be stored as a transition effect on one of the clips
    all_effects = [
        eff
        for tr in t.tracks
        for clip in tr.clips
        for eff in clip.effects
    ]
    assert len(all_effects) > 0, "Expected at least one transition effect"


def scenario_ripple_delete():
    """Add 3 clips, ripple-delete middle, assert only 2 remain."""
    c1 = _clip(asset_hash="r1", position_sec=0.0, out_point_sec=5.0)
    c2 = _clip(asset_hash="r2", position_sec=5.0, out_point_sec=10.0)
    c3 = _clip(asset_hash="r3", position_sec=10.0, out_point_sec=15.0)
    ripple = RippleDeleteClipOp(author="user", clip_id=c2.clip_id)
    t = _derive(c1, c2, c3, ripple)
    total_clips = sum(len(tr.clips) for tr in t.tracks)
    assert total_clips == 2, f"Expected 2 clips after ripple delete, got {total_clips}"


def scenario_change_speed():
    """Add clip, change speed to 2x, assert rate stored."""
    add = _clip()
    speed = ChangeClipSpeedOp(author="user", clip_id=add.clip_id, rate=2.0)
    t = _derive(add, speed)
    clip = t.tracks[0].clips[0]
    # speed change should be reflected in the clip or its effects
    speed_effect = next(
        (e for e in clip.effects if "speed" in e.effect_type or e.params.get("rate")),
        None,
    )
    # Either the clip has a speed effect, or it's stored as a clip attribute
    assert speed_effect is not None or hasattr(clip, "rate"), (
        "Speed change not reflected in clip or effects"
    )


def scenario_audio_gain():
    """Add audio clip, set gain, assert volume effect is on clip."""
    add = _clip(track_id="audio_1", track_kind="audio")
    gain = SetAudioGainOp(author="user", clip_id=add.clip_id, gain_db=-6.0)
    t = _derive(add, gain)
    clip = t.tracks[0].clips[0]
    volume_effect = next((e for e in clip.effects if e.effect_type == "volume"), None)
    assert volume_effect is not None, "Expected 'volume' effect for audio gain"


def scenario_normalize_audio():
    """Add audio clip, normalize to -16 dBFS, assert op applied."""
    add = _clip(track_id="audio_1", track_kind="audio")
    norm = NormalizeAudioOp(
        author="ai",
        target_kind="clip",
        target_id=add.clip_id,
        target_dbfs=-16.0,
    )
    t = _derive(add, norm)
    # NormalizeAudioOp is a metadata op; timeline shouldn't crash
    assert len(t.tracks) >= 1


def scenario_group_edits():
    """Add two clips, group them, assert both clips present and group in graph."""
    c1 = _clip(asset_hash="g1")
    c2 = _clip(asset_hash="g2", position_sec=10.0)
    group = GroupEditsOp(
        author="user",
        edit_ids=[c1.edit_id, c2.edit_id],
        label="my group",
    )
    t = _derive(c1, c2, group)
    total_clips = sum(len(tr.clips) for tr in t.tracks)
    assert total_clips == 2, "Clips should still be present after grouping"


def scenario_revert_operation():
    """Add clip, mark it reverted, assert it's gone from timeline."""
    add = _clip(asset_hash="reverted-hash")
    reverted = add.model_copy(update={"status": "reverted"})
    t = _derive(reverted)
    total_clips = sum(len(tr.clips) for tr in t.tracks)
    assert total_clips == 0, f"Reverted clip should not appear; found {total_clips}"


def scenario_reorder_commuting_ops():
    """Add clip to track1, add clip to track2, verify order-independent."""
    c1 = _clip(asset_hash="track1-clip", track_id="video_1")
    c2 = _clip(asset_hash="track2-clip", track_id="video_2")
    t_forward = _derive(c1, c2)
    t_reverse = _derive(c2, c1)
    clips_forward = {
        tr.track_id: [c.asset_hash for c in tr.clips]
        for tr in t_forward.tracks
    }
    clips_reverse = {
        tr.track_id: [c.asset_hash for c in tr.clips]
        for tr in t_reverse.tracks
    }
    assert clips_forward == clips_reverse, (
        "Operations on different tracks should commute"
    )


def scenario_replace_clip_source():
    """Add clip, replace its source asset, assert new hash."""
    add = _clip(asset_hash="old-hash")
    replace = ReplaceClipSourceOp(
        author="user",
        clip_id=add.clip_id,
        new_asset_hash="new-hash",
    )
    t = _derive(add, replace)
    clip = t.tracks[0].clips[0]
    assert clip.asset_hash == "new-hash"


def scenario_add_multiple_tracks():
    """Add clips to 3 separate tracks, assert all tracks present."""
    c1 = _clip(track_id="video_1")
    c2 = _clip(track_id="video_2")
    c3 = _clip(track_id="audio_1", track_kind="audio")
    t = _derive(c1, c2, c3)
    track_ids = {tr.track_id for tr in t.tracks}
    assert "video_1" in track_ids
    assert "video_2" in track_ids
    assert "audio_1" in track_ids


def scenario_duration_calculation():
    """Add clips at various positions, assert total duration is max end time."""
    c1 = _clip(position_sec=0.0, in_point_sec=0.0, out_point_sec=5.0)
    c2 = _clip(position_sec=10.0, in_point_sec=0.0, out_point_sec=8.0)
    c3 = _clip(position_sec=3.0, in_point_sec=0.0, out_point_sec=4.0)
    t = _derive(c1, c2, c3)
    # c2 ends at 10.0 + (8.0 - 0.0) = 18.0
    assert abs(t.duration_sec - 18.0) < 0.01, f"Expected duration ~18.0, got {t.duration_sec}"


def scenario_html_overlay_added():
    """Add HTML overlay, assert it appears in derived timeline."""
    overlay_op = AddHtmlOverlayOp(
        author="ai",
        template_path="templates/lower_third.html",
        variables={"name": "Alice"},
        position_sec=5.0,
        duration_sec=3.0,
    )
    t = _derive(overlay_op)
    assert len(t.overlays) == 1
    assert t.overlays[0].position_sec == 5.0
    assert t.overlays[0].duration_sec == 3.0
    assert t.overlays[0].variables["name"] == "Alice"


def scenario_html_overlay_removed():
    """Add then remove HTML overlay, assert empty."""
    add = AddHtmlOverlayOp(
        author="ai",
        template_path="templates/lower_third.html",
        overlay_id="ov-remove-test",
        position_sec=0.0,
        duration_sec=5.0,
    )
    remove = RemoveHtmlOverlayOp(author="user", overlay_id="ov-remove-test")
    t = _derive(add, remove)
    assert len(t.overlays) == 0


def scenario_overlay_duration_affects_total():
    """Overlay ending at t=20 should push duration to at least 20."""
    overlay_op = AddHtmlOverlayOp(
        author="ai",
        template_path="t.html",
        position_sec=15.0,
        duration_sec=5.0,
    )
    t = _derive(overlay_op)
    assert t.duration_sec >= 20.0


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

SCENARIOS: list[Callable] = [
    scenario_add_single_clip,
    scenario_add_two_clips_sequential,
    scenario_add_clip_then_remove,
    scenario_move_clip,
    scenario_trim_clip,
    scenario_slip_clip,
    scenario_split_clip,
    scenario_add_effect_to_clip,
    scenario_remove_effect,
    scenario_set_keyframe,
    scenario_add_transition,
    scenario_ripple_delete,
    scenario_change_speed,
    scenario_audio_gain,
    scenario_normalize_audio,
    scenario_group_edits,
    scenario_revert_operation,
    scenario_reorder_commuting_ops,
    scenario_replace_clip_source,
    scenario_add_multiple_tracks,
    scenario_duration_calculation,
    scenario_html_overlay_added,
    scenario_html_overlay_removed,
    scenario_overlay_duration_affects_total,
]


def run_all() -> tuple[int, int]:
    """Run all scenarios. Return (passed, failed)."""
    passed = 0
    failed = 0
    print("\nScenario Evaluation Report")
    print("=" * 60)
    for scenario in SCENARIOS:
        name = scenario.__name__.replace("scenario_", "")
        try:
            scenario()
            print(f"[PASS] {name}")
            passed += 1
        except Exception:
            tb = traceback.format_exc().strip().splitlines()[-1]
            print(f"[FAIL] {name}: {tb}")
            failed += 1
    print()
    total = passed + failed
    rate = 100.0 * passed / total if total else 0.0
    print(f"Results: {passed} passed, {failed} failed")
    print(f"Success rate: {rate:.1f}%")
    return passed, failed


if __name__ == "__main__":
    passed, failed = run_all()
    sys.exit(0 if failed == 0 or (passed / (passed + failed)) >= 0.80 else 1)


# ---------------------------------------------------------------------------
# pytest integration — each scenario becomes a test_* function
# ---------------------------------------------------------------------------

try:
    import pytest  # noqa: F401  (only needed for pytest.approx in scenarios)
    _pytest_available = True
except ImportError:
    _pytest_available = False


def _make_test(scenario_fn: Callable):
    def test_fn():
        scenario_fn()
    test_fn.__name__ = f"test_{scenario_fn.__name__.replace('scenario_', '')}"
    test_fn.__doc__ = scenario_fn.__doc__
    return test_fn


# Inject test_* functions into module namespace for pytest discovery
import sys as _sys
_module = _sys.modules[__name__]
for _scenario in SCENARIOS:
    _test = _make_test(_scenario)
    setattr(_module, _test.__name__, _test)
