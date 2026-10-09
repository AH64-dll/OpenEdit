
import pytest

from open_edit.ir.derive import derive_timeline
from open_edit.ir.types import Clip, Project, Timeline, Track
from open_edit.ir.validate import TimelineValidationError, validate_timeline

# open_edit/tests/test_ir_validation.py



def _clip(clip_id, start, in_p, out_p):
    return Clip(
        clip_id=clip_id, asset_hash="h", track_id="V1", track_kind="video",
        position_sec=start, in_point_sec=in_p, out_point_sec=out_p,
    )


def test_validate_timeline_detects_overlap():
    tl = Timeline(tracks=[Track(track_id="V1", kind="video", clips=[
        _clip("a", 0.0, 0.0, 5.0),
        _clip("b", 4.0, 0.0, 5.0),  # starts at 4.0 < a's end 5.0 -> overlap
    ])])
    errs = validate_timeline(tl)
    assert any("Overlap" in e for e in errs), errs


def test_validate_timeline_detects_nonpositive_duration():
    tl = Timeline(tracks=[Track(track_id="V1", kind="video", clips=[
        _clip("a", 0.0, 5.0, 5.0),  # out == in -> zero duration
    ])])
    errs = validate_timeline(tl)
    assert any("duration" in e.lower() for e in errs), errs


def test_validate_timeline_clean():
    tl = Timeline(tracks=[Track(track_id="V1", kind="video", clips=[
        _clip("a", 0.0, 0.0, 5.0),
        _clip("b", 5.0, 0.0, 5.0),  # abuts exactly, no overlap
    ])])
    assert validate_timeline(tl) == []




def _overlapping_project():
    # A project whose derived timeline has two overlapping clips on V1.
    from open_edit.ir.types import AddClipOp
    ops = [
        AddClipOp(asset_hash="h", track_id="V1", position_sec=0.0,
                  in_point_sec=0.0, out_point_sec=5.0, author="ai"),
        AddClipOp(asset_hash="h", track_id="V1", position_sec=4.0,
                  in_point_sec=0.0, out_point_sec=5.0, author="ai"),
    ]
    return Project(project_id="p", name="p", workdir="/tmp", assets={}, edit_graph=ops)


def test_derive_timeline_strict_raises_on_overlap():
    with pytest.raises(TimelineValidationError):
        derive_timeline(_overlapping_project(), strict=True)


def test_derive_timeline_lenient_loads_overlap():
    # Default stays lenient so legacy projects still load.
    tl = derive_timeline(_overlapping_project(), strict=False)
    assert any(len(t.clips) == 2 for t in tl.tracks)


# =========================================================================
# CORE-03: the speed effect synthesized by ChangeClipSpeedOp is a supported
# keyframe target. The append-door reference check resolves effect ids from
# an ordered per-clip projection that mirrors the actual apply mutations:
# first speed mints op.edit_id, a later speed supersedes in place (id
# unchanged, the later op's own id stays unregistered), an index-addressed
# RemoveEffectOp drops exactly the projected entry, and the next speed op
# re-mints a fresh id. Split/duplicate copies keep recognized identities.
# =========================================================================

def _append_speed_clip(project, clip_id='c1'):
    from open_edit.ir.types import AddClipOp
    clip = AddClipOp(author='user', clip_id=clip_id, asset_hash='h',
                     track_id='v1', position_sec=0, out_point_sec=4)
    project.edit_graph.append(clip)
    return clip


def test_keyframe_on_first_speed_effect_accepted():
    from open_edit.ir.types import AddClipOp, ChangeClipSpeedOp, SetKeyframeOp
    from open_edit.ir.validate import validate_op

    project = Project(project_id='p', name='p', workdir='/tmp', assets={})
    clip = _append_speed_clip(project)
    speed = ChangeClipSpeedOp(author='user', clip_id=clip.clip_id, rate=2.0)
    project.edit_graph.append(speed)
    keyframe = SetKeyframeOp(author='user', effect_id=speed.edit_id,
                             param='rate', keyframes=[(0.0, 1.0, 'linear')])
    assert validate_op(keyframe, project) == []


def test_keyframe_on_later_speed_op_id_still_rejected():
    from open_edit.ir.types import AddClipOp, ChangeClipSpeedOp, SetKeyframeOp
    from open_edit.ir.validate import validate_op

    project = Project(project_id='p', name='p', workdir='/tmp', assets={})
    clip = _append_speed_clip(project)
    first = ChangeClipSpeedOp(author='user', clip_id=clip.clip_id, rate=2.0)
    second = ChangeClipSpeedOp(author='user', clip_id=clip.clip_id, rate=3.0)
    project.edit_graph.extend([first, second])
    # A second speed op supersedes the existing speed effect in place; its
    # own op id mints nothing, so keyframing it stays a phantom reference.
    keyframe = SetKeyframeOp(author='user', effect_id=second.edit_id,
                             param='rate', keyframes=[(0.0, 1.0, 'linear')])
    errors = validate_op(keyframe, project)
    assert any(second.edit_id in e for e in errors)
    # ...and the preserved first id still resolves.
    ok = SetKeyframeOp(author='user', effect_id=first.edit_id,
                       param='rate', keyframes=[(0.0, 1.0, 'linear')])
    assert validate_op(ok, project) == []


def test_index_removal_is_faithful_then_speed_re_mints():
    from open_edit.ir.types import (AddClipOp, AddEffectOp, ChangeClipSpeedOp,
                                    RemoveEffectOp, SetKeyframeOp)
    from open_edit.ir.validate import validate_op

    project = Project(project_id='p', name='p', workdir='/tmp', assets={})
    clip = _append_speed_clip(project)
    older = AddEffectOp(author='user', effect_id='older', effect_type='brightness',
                        target_kind='clip', target_id=clip.clip_id)
    speed = ChangeClipSpeedOp(author='user', clip_id=clip.clip_id, rate=2.0)
    # effects = [older(0), speed(1)] exactly as apply orders them.
    project.edit_graph.extend([older, speed])
    late_speed = ChangeClipSpeedOp(author='user', clip_id=clip.clip_id, rate=4.0)
    remove_speed = RemoveEffectOp(author='user', clip_id=clip.clip_id, effect_index=1)
    project.edit_graph.extend([remove_speed, late_speed])
    # The next speed op mints a fresh id at the same index.
    ok = SetKeyframeOp(author='user', effect_id=late_speed.edit_id,
                       param='rate', keyframes=[(0.0, 1.0, 'linear')])
    assert validate_op(ok, project) == []
    # The removed first id no longer resolves.
    stale = SetKeyframeOp(author='user', effect_id=speed.edit_id,
                          param='rate', keyframes=[(0.0, 1.0, 'linear')])
    errors = validate_op(stale, project)
    assert any(speed.edit_id in e for e in errors)


def test_removal_at_neighbor_index_keeps_speed_identity():
    from open_edit.ir.types import (AddClipOp, AddEffectOp, ChangeClipSpeedOp,
                                    RemoveEffectOp, SetKeyframeOp)
    from open_edit.ir.validate import validate_op

    project = Project(project_id='p', name='p', workdir='/tmp', assets={})
    clip = _append_speed_clip(project)
    older = AddEffectOp(author='user', effect_id='older', effect_type='brightness',
                        target_kind='clip', target_id=clip.clip_id)
    speed = ChangeClipSpeedOp(author='user', clip_id=clip.clip_id, rate=2.0)
    project.edit_graph.extend([older, speed])
    # Remove index 0 = 'older'; the speed effect's identity survives and a
    # later speed op supersedes in place instead of minting.
    project.edit_graph.append(RemoveEffectOp(author='user', clip_id=clip.clip_id, effect_index=0))
    late = ChangeClipSpeedOp(author='user', clip_id=clip.clip_id, rate=4.0)
    project.edit_graph.append(late)
    ok = SetKeyframeOp(author='user', effect_id=speed.edit_id,
                       param='rate', keyframes=[(0.0, 1.0, 'linear')])
    assert validate_op(ok, project) == []
    phantom = SetKeyframeOp(author='user', effect_id=late.edit_id,
                            param='rate', keyframes=[(0.0, 1.0, 'linear')])
    assert any(late.edit_id in e for e in validate_op(phantom, project))


def test_split_copy_speed_id_is_recognized_for_keyframes():
    from uuid import NAMESPACE_URL, uuid5

    from open_edit.ir.types import (AddClipOp, ChangeClipSpeedOp, SetKeyframeOp,
                                    SplitClipOp)
    from open_edit.ir.validate import validate_op

    project = Project(project_id='p', name='p', workdir='/tmp', assets={})
    clip = _append_speed_clip(project)
    speed = ChangeClipSpeedOp(author='user', clip_id=clip.clip_id, rate=2.0)
    split = SplitClipOp(author='user', clip_id=clip.clip_id, at_sec=2,
                        left_clip_id='left', right_clip_id='right')
    project.edit_graph.extend([speed, split])
    minted = str(uuid5(NAMESPACE_URL, f'openedit:split:right:{speed.edit_id}'))
    keyframe = SetKeyframeOp(author='user', effect_id=minted,
                             param='rate', keyframes=[(0.0, 1.0, 'linear')])
    errors = validate_op(keyframe, project)
    assert not any('not found' in e for e in errors), errors
