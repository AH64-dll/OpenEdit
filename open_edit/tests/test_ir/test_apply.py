"""Tests for apply.py — unit test suite for operation replay and derived state."""
import tempfile
import unittest
from pathlib import Path

from open_edit.ir.apply import apply_operation, derive_timeline
from open_edit.ir.types import (
    AddClipOp,
    AddEffectOp,
    AddTransitionOp,
    ChangeClipSpeedOp,
    Effect,
    FreeFormCodeOp,
    GroupEditsOp,
    MoveClipOp,
    NormalizeAudioOp,
    Project,
    RawMltXmlOp,
    RemoveClipOp,
    RemoveEffectOp,
    RemoveKeyframeOp,
    RemoveTransitionOp,
    ReplaceClipSourceOp,
    RippleDeleteClipOp,
    SetAudioGainOp,
    SetClipSpeedRampOp,
    SetEffectParamOp,
    SetKeyframeOp,
    SetTransitionPropertyOp,
    SlipClipOp,
    SplitClipOp,
    Timeline,
    TrimClipOp,
    UngroupEditsOp,
)
from open_edit.storage.edit_graph import EditGraphStore


class TestApplyAddRemoveClip(unittest.TestCase):
    def test_add_clip_creates_track(self) -> None:
        timeline = Timeline()
        op = AddClipOp(author="user", asset_hash="abc", track_id="v1", position_sec=0.0)
        out = apply_operation(timeline, op)
        self.assertEqual(len(out.tracks), 1)
        self.assertEqual(out.tracks[0].track_id, "v1")
        self.assertEqual(len(out.tracks[0].clips), 1)
        self.assertEqual(out.tracks[0].clips[0].asset_hash, "abc")

    def test_add_clip_uses_position_sec(self) -> None:
        timeline = Timeline()
        op = AddClipOp(
            author="user", asset_hash="abc", track_id="v1", position_sec=12.5,
        )
        out = apply_operation(timeline, op)
        self.assertEqual(out.tracks[0].clips[0].position_sec, 12.5)

    def test_add_audio_clip_is_first_class(self) -> None:
        timeline = Timeline()
        op = AddClipOp(
            author="user", asset_hash="narr",
            track_id="audio_1", track_kind="audio", position_sec=0.0,
        )
        out = apply_operation(timeline, op)
        self.assertEqual(out.tracks[0].kind, "audio")
        self.assertEqual(out.tracks[0].clips[0].track_kind, "audio")

    def test_remove_clip_removes_from_track(self) -> None:
        timeline = Timeline()
        op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
        timeline = apply_operation(timeline, op)
        rm = RemoveClipOp(author="user", clip_id=op.clip_id)
        out = apply_operation(timeline, rm)
        self.assertEqual(out.tracks[0].clips, [])

    def test_remove_clip_for_unknown_id_is_no_op(self) -> None:
        timeline = Timeline()
        op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
        timeline = apply_operation(timeline, op)
        rm = RemoveClipOp(author="user", clip_id="nope")
        out = apply_operation(timeline, rm)
        self.assertEqual(len(out.tracks[0].clips), 1)


class TestApplyStrictMode(unittest.TestCase):
    """Bug A3: ``apply_operation`` silently no-ops on unknown references.

    Adding ``strict=True`` makes the helpers raise ``ApplyError`` instead of
    silently returning the timeline unchanged. The default ``strict=False``
    preserves the existing idempotent replay behavior used by
    ``derive_timeline`` (the bridge path).
    """

    def test_strict_false_keeps_silent_noop_behavior(self) -> None:
        from open_edit.ir.apply import ApplyError

        timeline = Timeline()
        mv = MoveClipOp(
            author="user", clip_id="missing", new_track_id="v2",
            new_position_sec=0.0,
        )
        try:
            out = apply_operation(timeline, mv, strict=False)
        except ApplyError as exc:
            self.fail(f"strict=False should not raise, got {exc!r}")
        self.assertEqual(out, timeline)

    def test_strict_true_raises_on_unknown_clip_in_move(self) -> None:
        from open_edit.ir.apply import ApplyError

        timeline = Timeline()
        timeline = apply_operation(
            timeline,
            AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0),
        )
        mv = MoveClipOp(
            author="user", clip_id="nope", new_track_id="v2",
            new_position_sec=0.0,
        )
        with self.assertRaises(ApplyError):
            apply_operation(timeline, mv, strict=True)

    def test_strict_true_raises_on_unknown_target_in_normalize_audio(self) -> None:
        from open_edit.ir.apply import ApplyError

        timeline = Timeline()
        norm = NormalizeAudioOp(
            author="user", target_kind="clip", target_id="missing",
            target_dbfs=-16.0,
        )
        with self.assertRaises(ApplyError):
            apply_operation(timeline, norm, strict=True)

    def test_strict_true_raises_on_unknown_target_in_add_effect(self) -> None:
        from open_edit.ir.apply import ApplyError

        timeline = Timeline()
        eff = AddEffectOp(
            author="user", target_kind="clip", target_id="missing",
            effect_type="volume", params={"gain": 1.0},
        )
        with self.assertRaises(ApplyError):
            apply_operation(timeline, eff, strict=True)

    def test_strict_true_raises_on_unknown_clip_in_slip(self) -> None:
        from open_edit.ir.apply import ApplyError

        timeline = Timeline()
        slip = SlipClipOp(author="user", clip_id="missing", delta_sec=1.0)
        with self.assertRaises(ApplyError):
            apply_operation(timeline, slip, strict=True)

    def test_strict_true_raises_on_unknown_effect_id_in_set_keyframe(self) -> None:
        from open_edit.ir.apply import ApplyError

        timeline = Timeline()
        timeline = apply_operation(
            timeline,
            AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0),
        )
        kf = SetKeyframeOp(
            author="user", effect_id="missing", param="gain",
            keyframes=[(0.0, 1.0, "linear")],
        )
        with self.assertRaises(ApplyError):
            apply_operation(timeline, kf, strict=True)


class TestApplyMoveTrimClip(unittest.TestCase):
    def test_move_clip_relocates(self) -> None:
        timeline = Timeline()
        op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
        timeline = apply_operation(timeline, op)
        mv = MoveClipOp(
            author="user", clip_id=op.clip_id,
            new_track_id="v2", new_position_sec=15.0,
        )
        out = apply_operation(timeline, mv)
        self.assertEqual(out.tracks[0].clips, [])
        self.assertEqual(len(out.tracks[1].clips), 1)
        self.assertEqual(out.tracks[1].clips[0].position_sec, 15.0)

    def test_trim_clip_updates_in_and_out(self) -> None:
        timeline = Timeline()
        op = AddClipOp(
            author="user", asset_hash="a", track_id="v1",
            position_sec=0.0, in_point_sec=0.0, out_point_sec=10.0,
        )
        timeline = apply_operation(timeline, op)
        tr = TrimClipOp(
            author="user", clip_id=op.clip_id,
            new_in_point_sec=2.0, new_out_point_sec=8.0,
        )
        out = apply_operation(timeline, tr)
        clip = out.tracks[0].clips[0]
        self.assertEqual(clip.in_point_sec, 2.0)
        self.assertEqual(clip.out_point_sec, 8.0)

    def test_slip_clip(self) -> None:
        timeline = Timeline()
        op = AddClipOp(
            author="user", asset_hash="a", track_id="v1",
            position_sec=5.0, in_point_sec=1.0, out_point_sec=6.0,
        )
        timeline = apply_operation(timeline, op)
        slip = SlipClipOp(author="user", clip_id=op.clip_id, delta_sec=2.0)
        out = apply_operation(timeline, slip)
        clip = out.tracks[0].clips[0]
        self.assertEqual(clip.position_sec, 5.0)
        self.assertEqual(clip.in_point_sec, 3.0)
        self.assertEqual(clip.out_point_sec, 8.0)

    def test_ripple_delete_clip(self) -> None:
        timeline = Timeline()
        op1 = AddClipOp(
            author="user", asset_hash="a", track_id="v1",
            position_sec=0.0, in_point_sec=0.0, out_point_sec=4.0,
        )
        op2 = AddClipOp(
            author="user", asset_hash="b", track_id="v1",
            position_sec=4.0, in_point_sec=0.0, out_point_sec=6.0,
        )
        op3 = AddClipOp(
            author="user", asset_hash="c", track_id="v1",
            position_sec=10.0, in_point_sec=0.0, out_point_sec=5.0,
        )
        timeline = apply_operation(timeline, op1)
        timeline = apply_operation(timeline, op2)
        timeline = apply_operation(timeline, op3)

        ripple = RippleDeleteClipOp(author="user", clip_id=op2.clip_id)
        out = apply_operation(timeline, ripple)

        clips = out.tracks[0].clips
        self.assertEqual(len(clips), 2)
        self.assertEqual(clips[0].clip_id, op1.clip_id)
        self.assertEqual(clips[0].position_sec, 0.0)
        self.assertEqual(clips[1].clip_id, op3.clip_id)
        self.assertAlmostEqual(clips[1].position_sec, 4.0, delta=0.001)

    def test_split_clip(self) -> None:
        timeline = Timeline()
        op = AddClipOp(
            author="user", asset_hash="a", track_id="v1",
            position_sec=0.0, in_point_sec=2.0, out_point_sec=10.0,
        )
        timeline = apply_operation(timeline, op)

        split = SplitClipOp(
            author="user", clip_id=op.clip_id, at_sec=4.0,
            left_clip_id="left_1", right_clip_id="right_1",
        )
        out = apply_operation(timeline, split)
        clips = out.tracks[0].clips
        self.assertEqual(len(clips), 2)

        self.assertEqual(clips[0].clip_id, "left_1")
        self.assertEqual(clips[0].position_sec, 0.0)
        self.assertEqual(clips[0].in_point_sec, 2.0)
        self.assertEqual(clips[0].out_point_sec, 6.0)

        self.assertEqual(clips[1].clip_id, "right_1")
        self.assertEqual(clips[1].position_sec, 4.0)
        self.assertEqual(clips[1].in_point_sec, 6.0)
        self.assertEqual(clips[1].out_point_sec, 10.0)

    def test_split_clip_with_no_effects(self) -> None:
        timeline = Timeline()
        op = AddClipOp(
            author="user", asset_hash="a", track_id="v1",
            position_sec=0.0, in_point_sec=2.0, out_point_sec=10.0,
        )
        timeline = apply_operation(timeline, op)
        self.assertEqual(timeline.tracks[0].clips[0].effects, [])

        split = SplitClipOp(
            author="user", clip_id=op.clip_id, at_sec=4.0,
            left_clip_id="left_1", right_clip_id="right_1",
        )
        out = apply_operation(timeline, split)
        clips = out.tracks[0].clips
        self.assertEqual(len(clips), 2)
        # Bug 2 regression: splitting a clip with no effects must keep a real
        # list (not None), otherwise downstream iteration breaks.
        self.assertEqual(clips[0].effects, [])
        self.assertEqual(clips[1].effects, [])

    def test_change_clip_speed(self) -> None:
        timeline = Timeline()
        op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
        timeline = apply_operation(timeline, op)

        speed_op = ChangeClipSpeedOp(author="user", clip_id=op.clip_id, rate=1.5)
        out = apply_operation(timeline, speed_op)
        effects = out.tracks[0].clips[0].effects
        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0].effect_type, "speed")
        self.assertEqual(effects[0].params.get("rate"), 1.5)

    def test_replace_clip_source(self) -> None:
        timeline = Timeline()
        op = AddClipOp(author="user", asset_hash="old_hash", track_id="v1", position_sec=0.0)
        timeline = apply_operation(timeline, op)

        replace_op = ReplaceClipSourceOp(
            author="user", clip_id=op.clip_id, new_asset_hash="new_hash",
        )
        out = apply_operation(timeline, replace_op)
        self.assertEqual(out.tracks[0].clips[0].asset_hash, "new_hash")

    def test_set_clip_speed_ramp(self) -> None:
        timeline = Timeline()
        op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
        timeline = apply_operation(timeline, op)

        ramp_points = [{"t": 0.0, "speed": 1.0}, {"t": 2.0, "speed": 2.0}]
        ramp_op = SetClipSpeedRampOp(
            author="user", clip_id=op.clip_id, keyframes=ramp_points,
        )
        out = apply_operation(timeline, ramp_op)
        effects = out.tracks[0].clips[0].effects
        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0].effect_type, "speed_ramp")
        self.assertEqual(effects[0].params.get("keyframes"), ramp_points)


class TestApplyTransitions(unittest.TestCase):
    def test_add_transition_centers_on_cut_not_midpoint(self) -> None:
        """Bug A regression test."""
        timeline = Timeline()
        op_a = AddClipOp(
            author="user", asset_hash="a", track_id="v1",
            position_sec=0.0, in_point_sec=0.0, out_point_sec=10.0,
        )
        op_b = AddClipOp(
            author="user", asset_hash="b", track_id="v1",
            position_sec=10.0, in_point_sec=0.0, out_point_sec=10.0,
        )
        timeline = apply_operation(timeline, op_a)
        timeline = apply_operation(timeline, op_b)

        op_t = AddTransitionOp(
            author="user", clip_a_id=op_a.clip_id, clip_b_id=op_b.clip_id,
            transition_type="luma", duration_sec=2.0,
        )
        out = apply_operation(timeline, op_t)
        clips = out.tracks[0].clips
        self.assertAlmostEqual(clips[0].out_point_sec, 9.0, delta=0.001)
        self.assertAlmostEqual(clips[1].in_point_sec, 1.0, delta=0.001)

    def test_add_transition_rejects_duration_larger_than_clips(self) -> None:
        timeline = Timeline()
        op_a = AddClipOp(
            author="user", asset_hash="a", track_id="v1",
            position_sec=0.0, in_point_sec=0.0, out_point_sec=5.0,
        )
        op_b = AddClipOp(
            author="user", asset_hash="b", track_id="v1",
            position_sec=5.0, in_point_sec=0.0, out_point_sec=5.0,
        )
        timeline = apply_operation(timeline, op_a)
        timeline = apply_operation(timeline, op_b)
        op_t = AddTransitionOp(
            author="user", clip_a_id=op_a.clip_id, clip_b_id=op_b.clip_id,
            transition_type="luma", duration_sec=12.0,
        )
        with self.assertRaises(ValueError):
            apply_operation(timeline, op_t)

    def test_add_transition_appends_effect_to_clip_a(self) -> None:
        timeline = Timeline()
        op_a = AddClipOp(
            author="user", asset_hash="a", track_id="v1",
            position_sec=0.0, in_point_sec=0.0, out_point_sec=10.0,
        )
        op_b = AddClipOp(
            author="user", asset_hash="b", track_id="v1",
            position_sec=10.0, in_point_sec=0.0, out_point_sec=10.0,
        )
        timeline = apply_operation(timeline, op_a)
        timeline = apply_operation(timeline, op_b)
        op_t = AddTransitionOp(
            author="user", clip_a_id=op_a.clip_id, clip_b_id=op_b.clip_id,
            transition_type="luma", duration_sec=2.0,
        )
        out = apply_operation(timeline, op_t)
        clip_a = out.tracks[0].clips[0]
        self.assertEqual(len(clip_a.effects), 1)
        self.assertEqual(clip_a.effects[0].effect_type, "transition_luma")
        self.assertEqual(clip_a.effects[0].params["clip_b_id"], op_b.clip_id)

    def test_add_transition_with_clip_a_already_trimmed(self) -> None:
        timeline = Timeline()
        op_a = AddClipOp(
            author="user", asset_hash="a", track_id="v1",
            position_sec=0.0, in_point_sec=0.5, out_point_sec=2.0,
        )
        op_b = AddClipOp(
            author="user", asset_hash="b", track_id="v1",
            position_sec=2.0, in_point_sec=0.0, out_point_sec=2.0,
        )
        timeline = apply_operation(timeline, op_a)
        timeline = apply_operation(timeline, op_b)
        op_t = AddTransitionOp(
            author="user", clip_a_id=op_a.clip_id, clip_b_id=op_b.clip_id,
            transition_type="luma", duration_sec=1.0,
        )
        out = apply_operation(timeline, op_t)
        clip_a = out.tracks[0].clips[0]
        clip_b = out.tracks[0].clips[1]
        self.assertGreater(clip_a.out_point_sec, clip_a.in_point_sec)
        self.assertGreaterEqual(clip_b.in_point_sec, 0.0)
        self.assertAlmostEqual(clip_a.out_point_sec, 1.5, delta=0.001)
        self.assertAlmostEqual(clip_b.in_point_sec, 0.0, delta=0.001)

    def test_add_transition_with_clip_b_already_trimmed(self) -> None:
        timeline = Timeline()
        op_a = AddClipOp(
            author="user", asset_hash="a", track_id="v1",
            position_sec=0.0, in_point_sec=0.0, out_point_sec=2.0,
        )
        op_b = AddClipOp(
            author="user", asset_hash="b", track_id="v1",
            position_sec=2.0, in_point_sec=0.5, out_point_sec=2.0,
        )
        timeline = apply_operation(timeline, op_a)
        timeline = apply_operation(timeline, op_b)
        op_t = AddTransitionOp(
            author="user", clip_a_id=op_a.clip_id, clip_b_id=op_b.clip_id,
            transition_type="luma", duration_sec=1.0,
        )
        out = apply_operation(timeline, op_t)
        clip_a = out.tracks[0].clips[0]
        clip_b = out.tracks[0].clips[1]
        # Bug 1 regression: clip_b's trim (in_point_sec=0.5) must be added
        # back when back-solving its new asset-local in-point.
        self.assertAlmostEqual(clip_a.out_point_sec, 1.5, delta=0.001)
        self.assertAlmostEqual(clip_b.in_point_sec, 1.0, delta=0.001)
        # Geometry: clip_a ends at timeline 1.5s, clip_b starts at timeline 2.0s;
        # the transition spans the 1.0-2.0s window.
        self.assertAlmostEqual(
            clip_a.position_sec + (clip_a.out_point_sec - clip_a.in_point_sec), 1.5, delta=0.001
        )
        self.assertAlmostEqual(
            clip_b.position_sec + (clip_b.out_point_sec - clip_b.in_point_sec), 3.0, delta=0.001
        )

    def test_remove_transition(self) -> None:
        timeline = Timeline()
        op_a = AddClipOp(
            author="user", asset_hash="a", track_id="v1",
            position_sec=0.0, in_point_sec=0.0, out_point_sec=10.0,
        )
        op_b = AddClipOp(
            author="user", asset_hash="b", track_id="v1",
            position_sec=10.0, in_point_sec=0.0, out_point_sec=10.0,
        )
        timeline = apply_operation(timeline, op_a)
        timeline = apply_operation(timeline, op_b)
        op_t = AddTransitionOp(
            author="user", clip_a_id=op_a.clip_id, clip_b_id=op_b.clip_id,
            transition_type="dissolve", duration_sec=2.0,
        )
        timeline = apply_operation(timeline, op_t)
        self.assertEqual(len(timeline.tracks[0].clips[0].effects), 1)

        rm_t = RemoveTransitionOp(author="user", transition_id=op_t.edit_id)
        out = apply_operation(timeline, rm_t)
        self.assertEqual(len(out.tracks[0].clips[0].effects), 0)

    def test_set_transition_property(self) -> None:
        timeline = Timeline()
        op_a = AddClipOp(
            author="user", asset_hash="a", track_id="v1",
            position_sec=0.0, in_point_sec=0.0, out_point_sec=10.0,
        )
        op_b = AddClipOp(
            author="user", asset_hash="b", track_id="v1",
            position_sec=10.0, in_point_sec=0.0, out_point_sec=10.0,
        )
        timeline = apply_operation(timeline, op_a)
        timeline = apply_operation(timeline, op_b)
        op_t = AddTransitionOp(
            author="user", clip_a_id=op_a.clip_id, clip_b_id=op_b.clip_id,
            transition_type="wipe", duration_sec=2.0,
        )
        timeline = apply_operation(timeline, op_t)

        set_prop = SetTransitionPropertyOp(
            author="user", transition_id=op_t.edit_id,
            prop_name="softness", value="0.5",
        )
        out = apply_operation(timeline, set_prop)
        eff = out.tracks[0].clips[0].effects[0]
        self.assertEqual(eff.params.get("softness"), "0.5")

    def test_remove_transition_does_not_match_unrelated_effect_by_endswith(self) -> None:
        """Bug A1 regression test.

        ``_apply_remove_transition`` previously used ``eff.effect_id.endswith(op.transition_id)``
        which would match a non-transition effect whose id merely ends with the same suffix
        (e.g. transition_id="abc" would match effect_id="xabc"). The canonical form for
        a transition effect is either the bare ``op.edit_id`` or ``transition_<edit_id>``;
        we use strict equality on those two forms only.
        """
        timeline = Timeline()
        op_a = AddClipOp(
            author="user", asset_hash="a", track_id="v1",
            position_sec=0.0, in_point_sec=0.0, out_point_sec=10.0,
        )
        timeline = apply_operation(timeline, op_a)
        unrelated = AddEffectOp(
            author="user", target_kind="clip", target_id=op_a.clip_id,
            effect_type="luma", params={},
        )
        # Force the unrelated effect's id to end with the transition_id suffix.
        # This simulates a tampered DB or accidental id collision.
        timeline = apply_operation(
            timeline,
            unrelated.model_copy(update={"effect_id": "xabc"}),
        )
        self.assertEqual(len(timeline.tracks[0].clips[0].effects), 1)

        rm_t = RemoveTransitionOp(author="user", transition_id="abc")
        out = apply_operation(timeline, rm_t)
        effects = out.tracks[0].clips[0].effects
        self.assertEqual(
            len(effects), 1,
            "Unrelated effect whose id merely endswith transition_id must not be removed",
        )
        self.assertEqual(effects[0].effect_id, "xabc")

    def test_set_transition_property_does_not_match_unrelated_effect_by_endswith(self) -> None:
        """Bug A1 regression test for ``_apply_set_transition_property``."""
        timeline = Timeline()
        op_a = AddClipOp(
            author="user", asset_hash="a", track_id="v1",
            position_sec=0.0, in_point_sec=0.0, out_point_sec=10.0,
        )
        timeline = apply_operation(timeline, op_a)
        unrelated = AddEffectOp(
            author="user", target_kind="clip", target_id=op_a.clip_id,
            effect_type="luma", params={},
        )
        timeline = apply_operation(
            timeline,
            unrelated.model_copy(update={"effect_id": "xabc"}),
        )

        set_prop = SetTransitionPropertyOp(
            author="user", transition_id="abc",
            prop_name="softness", value="0.5",
        )
        out = apply_operation(timeline, set_prop)
        eff = out.tracks[0].clips[0].effects[0]
        self.assertNotIn("softness", eff.params)


class TestApplyEffectsAndAudio(unittest.TestCase):
    def test_add_effect_appends_to_clip(self) -> None:
        timeline = Timeline()
        op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
        timeline = apply_operation(timeline, op)
        eff = AddEffectOp(
            author="user", target_kind="clip", target_id=op.clip_id,
            effect_type="volume", params={"gain": 0.5},
        )
        out = apply_operation(timeline, eff)
        self.assertEqual(len(out.tracks[0].clips[0].effects), 1)

    def test_remove_effect(self) -> None:
        timeline = Timeline()
        op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
        timeline = apply_operation(timeline, op)
        eff1 = AddEffectOp(
            author="user", target_kind="clip", target_id=op.clip_id,
            effect_type="volume", params={"gain": 0.5},
        )
        eff2 = AddEffectOp(
            author="user", target_kind="clip", target_id=op.clip_id,
            effect_type="blur", params={"amount": 10},
        )
        timeline = apply_operation(timeline, eff1)
        timeline = apply_operation(timeline, eff2)
        self.assertEqual(len(timeline.tracks[0].clips[0].effects), 2)

        rm_eff = RemoveEffectOp(author="user", clip_id=op.clip_id, effect_index=0)
        out = apply_operation(timeline, rm_eff)
        effects = out.tracks[0].clips[0].effects
        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0].effect_type, "blur")

    def test_set_effect_param(self) -> None:
        timeline = Timeline()
        op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
        timeline = apply_operation(timeline, op)
        eff = AddEffectOp(
            author="user", target_kind="clip", target_id=op.clip_id,
            effect_type="brightness", params={"level": 1.0},
        )
        timeline = apply_operation(timeline, eff)

        set_param = SetEffectParamOp(
            author="user", clip_id=op.clip_id, effect_index=0,
            param_name="level", value="1.5", effect_id=eff.effect_id,
        )
        out = apply_operation(timeline, set_param)
        self.assertEqual(out.tracks[0].clips[0].effects[0].params["level"], "1.5")

    def test_set_keyframe_updates_existing_effect(self) -> None:
        timeline = Timeline()
        op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
        timeline = apply_operation(timeline, op)
        eff = AddEffectOp(
            author="user", target_kind="clip", target_id=op.clip_id,
            effect_type="volume", params={"gain": 1.0},
        )
        timeline = apply_operation(timeline, eff)
        kf = SetKeyframeOp(
            author="user", effect_id=eff.effect_id, param="gain",
            keyframes=[(0.0, 1.0, "linear"), (2.0, 0.0, "linear")],
        )
        out = apply_operation(timeline, kf)
        effects = out.tracks[0].clips[0].effects
        self.assertEqual(effects[0].keyframes["gain"], [(0.0, 1.0, "linear"), (2.0, 0.0, "linear")])

    def test_remove_keyframe(self) -> None:
        timeline = Timeline()
        op = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
        timeline = apply_operation(timeline, op)
        eff = AddEffectOp(
            author="user", target_kind="clip", target_id=op.clip_id,
            effect_type="volume", params={"gain": 1.0},
        )
        timeline = apply_operation(timeline, eff)
        kf = SetKeyframeOp(
            author="user", effect_id=eff.effect_id, param="gain",
            keyframes=[(0.0, 1.0, "linear"), (2.0, 0.0, "linear")],
        )
        timeline = apply_operation(timeline, kf)

        rm_kf = RemoveKeyframeOp(
            author="user", effect_id=eff.effect_id, param="gain", frame=2.0,
        )
        out = apply_operation(timeline, rm_kf)
        kfs = out.tracks[0].clips[0].effects[0].keyframes["gain"]
        self.assertEqual(len(kfs), 1)
        self.assertEqual(kfs[0], (0.0, 1.0, "linear"))

    def test_set_audio_gain_op(self) -> None:
        timeline = Timeline()
        op = AddClipOp(
            author="user", asset_hash="audio1", track_id="a1",
            track_kind="audio", position_sec=0.0,
        )
        timeline = apply_operation(timeline, op)

        gain_op = SetAudioGainOp(author="user", clip_id=op.clip_id, gain_db=-6.0)
        out = apply_operation(timeline, gain_op)
        effects = out.tracks[0].clips[0].effects
        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0].effect_type, "volume")
        self.assertAlmostEqual(effects[0].params["gain"], 10 ** (-6.0 / 20.0), delta=0.001)

    def test_normalize_audio_adds_volume_effect_to_clip(self) -> None:
        timeline = Timeline()
        add = AddClipOp(
            author="user", asset_hash="a", track_id="audio_1",
            track_kind="audio", position_sec=0.0,
        )
        timeline = apply_operation(timeline, add)
        norm = NormalizeAudioOp(
            author="user", target_kind="clip", target_id=add.clip_id,
            target_dbfs=-16.0,
        )
        out = apply_operation(timeline, norm)
        effects = out.tracks[0].clips[0].effects
        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0].effect_type, "volume")
        self.assertEqual(effects[0].params.get("target_dbfs"), -16.0)
        self.assertTrue(effects[0].params.get("normalize"))

    def test_normalize_audio_adds_volume_effect_to_track(self) -> None:
        timeline = Timeline()
        add = AddClipOp(
            author="user", asset_hash="a", track_id="audio_1",
            track_kind="audio", position_sec=2.0,
        )
        timeline = apply_operation(timeline, add)
        norm = NormalizeAudioOp(
            author="user", target_kind="track", target_id="audio_1",
            target_dbfs=-14.0,
        )
        out = apply_operation(timeline, norm)
        track = next(t for t in out.tracks if t.track_id == "audio_1")
        self.assertEqual(len(track.effects), 1)
        self.assertEqual(track.effects[0].effect_type, "volume")
        self.assertEqual(track.effects[0].params.get("target_dbfs"), -14.0)

    def test_normalize_audio_unknown_target_is_silent_noop(self) -> None:
        timeline = Timeline()
        norm = NormalizeAudioOp(
            author="user", target_kind="clip", target_id="nonexistent",
            target_dbfs=-16.0,
        )
        out = apply_operation(timeline, norm)
        self.assertEqual(out, timeline)

    def test_group_and_ungroup_and_raw_mlt_xml_edits_metadata(self) -> None:
        timeline = Timeline()
        add = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
        timeline = apply_operation(timeline, add)
        group = GroupEditsOp(
            author="user", edit_ids=[add.edit_id], label="intro",
        )
        out = apply_operation(timeline, group)
        self.assertEqual(len(out.tracks[0].clips), 1)

        ungroup = UngroupEditsOp(author="user", label="intro")
        out2 = apply_operation(out, ungroup)
        self.assertEqual(len(out2.tracks[0].clips), 1)

        raw_xml = RawMltXmlOp(author="user", xml="<mlt/>", description="raw test")
        out3 = apply_operation(out2, raw_xml)
        self.assertEqual(len(out3.tracks[0].clips), 1)


class TestDeriveTimelineReplay(unittest.TestCase):
    def test_derive_timeline_replays_all_applied_ops(self) -> None:
        project = Project(name="t")
        project.edit_graph.append(AddClipOp(
            author="user", asset_hash="a", track_id="v1",
            position_sec=0.0, in_point_sec=0.0, out_point_sec=5.0,
        ))
        project.edit_graph.append(AddClipOp(
            author="user", asset_hash="b", track_id="v1",
            position_sec=5.0, in_point_sec=0.0, out_point_sec=5.0,
        ))
        timeline = derive_timeline(project)
        self.assertEqual(len(timeline.tracks), 1)
        self.assertEqual(len(timeline.tracks[0].clips), 2)
        self.assertAlmostEqual(timeline.duration_sec, 10.0, delta=0.001)

    def test_derive_timeline_skips_reverted_ops(self) -> None:
        project = Project(name="t")
        op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
        op2 = AddClipOp(author="user", asset_hash="b", track_id="v1", position_sec=5.0)
        op2_reverted = op2.model_copy(update={"status": "reverted"})
        project.edit_graph.append(op1)
        project.edit_graph.append(op2_reverted)
        timeline = derive_timeline(project)
        self.assertEqual(len(timeline.tracks[0].clips), 1)

    def test_derive_timeline_skips_superseded_ops(self) -> None:
        project = Project(name="t")
        op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
        op2 = AddClipOp(author="user", asset_hash="b", track_id="v1", position_sec=5.0)
        op2_superseded = op2.model_copy(update={"status": "superseded"})
        project.edit_graph.append(op1)
        project.edit_graph.append(op2_superseded)
        timeline = derive_timeline(project)
        self.assertEqual(len(timeline.tracks[0].clips), 1)
        self.assertEqual(timeline.tracks[0].clips[0].asset_hash, "a")

    def test_derive_timeline_skips_child_of_reverted_op(self) -> None:
        project = Project(name="t")
        parent = AddClipOp(
            author="user", asset_hash="a", track_id="v1",
            position_sec=0.0, status="reverted",
        )
        child = AddEffectOp(
            author="ai", target_kind="clip", target_id=parent.clip_id,
            effect_type="volume", params={"gain": 0.8}, parent_id=parent.edit_id,
        )
        project.edit_graph.append(parent)
        project.edit_graph.append(child)
        timeline = derive_timeline(project)
        self.assertEqual(len(timeline.tracks), 0)

    def test_derive_timeline_raises_on_parent_cycle(self) -> None:
        """Bug A2 regression test.

        ``derive_timeline`` walks the parent_id chain to determine whether an op
        is "under a reverted parent" and should be skipped. The walk has no cycle
        protection; a tampered DB (or hand-crafted project) where two ops point
        at each other as parents would hang the test process. The fix is to
        raise ``ApplyError`` when a cycle is detected.
        """
        from open_edit.ir.apply import ApplyError

        op1 = AddClipOp(
            author="user", asset_hash="a", track_id="v1",
            position_sec=0.0, in_point_sec=0.0, out_point_sec=2.0,
        )
        op2 = AddClipOp(
            author="user", asset_hash="b", track_id="v1",
            position_sec=2.0, in_point_sec=0.0, out_point_sec=2.0,
            parent_id=op1.edit_id,
        )
        # Force op1 to be its own grandparent via op2 (cycle: op1 -> op2 -> op1).
        op1 = op1.model_copy(update={"parent_id": op2.edit_id})
        project = Project(name="cycle", edit_graph=[op1, op2])
        with self.assertRaises(ApplyError):
            derive_timeline(project)

    def test_derive_timeline_empty_project(self) -> None:
        project = Project(name="empty")
        timeline = derive_timeline(project)
        self.assertEqual(len(timeline.tracks), 0)
        self.assertEqual(timeline.duration_sec, 0.0)

    def test_derive_timeline_computes_duration_from_max_clip_end(self) -> None:
        project = Project(name="t")
        project.edit_graph.append(AddClipOp(
            author="user", asset_hash="a", track_id="v1",
            position_sec=0.0, in_point_sec=0.0, out_point_sec=3.0,
        ))
        project.edit_graph.append(AddClipOp(
            author="user", asset_hash="b", track_id="v1",
            position_sec=3.0, in_point_sec=0.0, out_point_sec=8.0,
        ))
        project.edit_graph.append(AddClipOp(
            author="user", asset_hash="c", track_id="v1",
            position_sec=11.0, in_point_sec=0.0, out_point_sec=2.0,
        ))
        timeline = derive_timeline(project)
        self.assertAlmostEqual(timeline.duration_sec, 13.0, delta=0.001)


class TestEditGraphReplayIntegration(unittest.TestCase):
    def test_edit_graph_store_load_all_derive_timeline_integration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_project.db"
            store = EditGraphStore(db_path)

            op1 = AddClipOp(
                author="user", asset_hash="asset_1", track_id="v1",
                position_sec=0.0, in_point_sec=0.0, out_point_sec=5.0,
            )
            op2 = AddClipOp(
                author="user", asset_hash="asset_2", track_id="v1",
                position_sec=5.0, in_point_sec=0.0, out_point_sec=5.0,
            )
            op3 = AddClipOp(
                author="user", asset_hash="asset_3_old", track_id="v1",
                position_sec=10.0, in_point_sec=0.0, out_point_sec=5.0,
            )

            store.append(op1)
            store.append(op2)
            store.append(op3)

            # Supersede op3 and add op4 instead
            store.update_status(op3.edit_id, "superseded")

            op4 = AddClipOp(
                author="user", asset_hash="asset_3_new", track_id="v1",
                position_sec=10.0, in_point_sec=0.0, out_point_sec=5.0,
            )
            store.append(op4)

            # Load back all ops from SQLite store
            ops = store.load_all()
            self.assertEqual(len(ops), 4)

            project = Project(name="integrated", edit_graph=ops)
            timeline = derive_timeline(project)

            clips = timeline.tracks[0].clips
            self.assertEqual(len(clips), 3)
            self.assertEqual(clips[0].asset_hash, "asset_1")
            self.assertEqual(clips[1].asset_hash, "asset_2")
            self.assertEqual(clips[2].asset_hash, "asset_3_new")
            self.assertAlmostEqual(timeline.duration_sec, 15.0, delta=0.001)


if __name__ == "__main__":
    unittest.main()
