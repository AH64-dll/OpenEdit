"""Shared timeline controls preserve source, identities, history and rendering."""
import pytest
from lxml import etree

from open_edit.ir.apply_common import ApplyError
from open_edit.ir.derive import derive_timeline
from open_edit.ir.types import AddClipOp, AddEffectOp, Project
from open_edit.ir.validate import _known_ids_from_ops
from open_edit.kernel.studio_service import commit_studio
from open_edit.render.emitter import EmitterConfig, emit_timeline
from open_edit.render.pipe_builder import overlay_filter_chain
from open_edit.render.preview_invalidation import slice_timeline
from open_edit.render.timeline_plan import _video_track_overlay_clips, timeline_for_melt
from open_edit.storage.edit_graph import EditGraphStore


@pytest.fixture
def project(tmp_path):
    store = EditGraphStore(tmp_path / '.open_edit/edit_graph.db')
    store.append_many([
        AddClipOp(author='user', clip_id='base', asset_hash='one', track_id='v1', position_sec=0, out_point_sec=4),
        AddClipOp(author='user', clip_id='upper', asset_hash='two', track_id='v2', position_sec=1, in_point_sec=2, out_point_sec=4),
        AddEffectOp(author='user', effect_id='bright', effect_type='brightness', target_kind='clip', target_id='base', params={'value': .8}),
    ])
    return tmp_path, store


def derive(store):
    return derive_timeline(Project(name='controls', edit_graph=store.load_all()), strict=True)


def edit(project, *ops):
    root, store = project
    return commit_studio(root, expected_revision=store.graph_revision(), changes=[], ops=list(ops), label='Manual control')


def test_duplicate_stable_effect_ids_and_request_history(project):
    _, store = project
    edit(project, {'kind':'duplicate_clip','clip_id':'base','new_clip_id':'copy','position_sec':5,'effect_ids':{'bright':'copy-bright'}},
         {'kind':'control_effect','target_kind':'clip','target_id':'copy','effect_id':'copy-bright','params':{'value':.4}})
    assert _known_ids_from_ops(store.load_all())[0] == {'base','upper','copy'}
    copied = derive(store).tracks[0].clips[1]
    assert copied.effects[0].effect_id == 'copy-bright' and copied.effects[0].params['value'] == .4
    assert derive(store).tracks[0].clips[0].effects[0].params['value'] == .8
    reopened = EditGraphStore(store.db_path)
    revision = reopened.graph_revision()
    reopened.history_step('undo', revision)
    assert [c.clip_id for c in derive(reopened).tracks[0].clips] == ['base']
    reopened.history_step('redo', reopened.graph_revision())
    assert derive(reopened).tracks[0].clips[1].clip_id == 'copy'


@pytest.mark.parametrize('op,match', [
    ({'kind':'duplicate_clip','clip_id':'base','new_clip_id':'copy','position_sec':5}, 'stable ID'),
    ({'kind':'control_effect','target_kind':'clip','target_id':'base','effect_id':'bright','params':{'value':3}}, 'within'),
    ({'kind':'control_effect','target_kind':'clip','target_id':'base','effect_id':'bright','params':{'value':True}}, 'finite'),
    ({'kind':'control_effect','target_kind':'clip','target_id':'base','effect_id':'bright','params':{'unknown':1}}, 'Unknown'),
    ({'kind':'control_effect','target_kind':'clip','target_id':'base','effect_id':'missing'}, 'does not exist'),
    ({'kind':'remove_track','track_id':'v1'}, 'clips and effects'),
])
def test_invalid_controls_leave_atomic_history_and_revision(project, op, match):
    _, store = project
    before = store.graph_revision(), len(store.load_all()), store.history()
    with pytest.raises((ValueError, ApplyError), match=match):
        edit(project, op)
    assert (store.graph_revision(), len(store.load_all()), store.history()) == before


def test_clip_track_locks_and_explicit_unlock(project):
    _, store = project
    edit(project, {'kind':'set_clip_properties','clip_id':'base','locked':True})
    with pytest.raises(ValueError, match='Unlock'):
        edit(project, {'kind':'move_clip','clip_id':'base','new_track_id':'v1','new_position_sec':1})
    with pytest.raises(ValueError, match='Unlock'):
        edit(project, {'kind':'set_clip_properties','clip_id':'base','locked':False,'muted':True})
    edit(project, {'kind':'set_clip_properties','clip_id':'base','locked':False})
    edit(project, {'kind':'set_track_properties','track_id':'v1','locked':True})
    with pytest.raises(ValueError, match='Unlock'):
        edit(project, {'kind':'set_clip_properties','clip_id':'base','muted':True})
    edit(project, {'kind':'set_track_properties','track_id':'v1','locked':False})
    assert not derive(store).tracks[0].locked


def test_effect_stack_bypass_order_duplicate_reset_and_delete(project):
    _, store = project
    edit(project, {'kind':'control_effect','target_kind':'clip','target_id':'base','effect_id':'bright','action':'duplicate','new_effect_id':'second'})
    edit(project, {'kind':'control_effect','target_kind':'clip','target_id':'base','effect_id':'second','enabled':False},
         {'kind':'control_effect','target_kind':'clip','target_id':'base','effect_id':'second','action':'move','index':0})
    assert [e.effect_id for e in derive(store).tracks[0].clips[0].effects] == ['second','bright']
    xml = etree.fromstring(emit_timeline(derive(store)).encode())
    assert not xml.xpath('//filter[@id="second"]') and xml.xpath('//filter[@id="bright"]')
    edit(project, {'kind':'control_effect','target_kind':'clip','target_id':'base','effect_id':'second','action':'reset'},
         {'kind':'control_effect','target_kind':'clip','target_id':'base','effect_id':'bright','action':'remove'})
    effects = derive(store).tracks[0].clips[0].effects
    assert len(effects) == 1 and effects[0].enabled and effects[0].params == {'value':1.0}


def test_split_effects_have_independent_durable_identities(project):
    _, store = project
    edit(project, {'kind':'split_clip','clip_id':'base','at_sec':2,'left_clip_id':'left','right_clip_id':'right'})
    left, right = derive(store).tracks[0].clips
    assert left.effects[0].effect_id != right.effects[0].effect_id
    assert right.effects[0].effect_id in _known_ids_from_ops(store.load_all())[1]
    edit(project, {'kind':'control_effect','target_kind':'clip','target_id':'right','effect_id':right.effects[0].effect_id,'params':{'value':.3}})
    assert derive(store).tracks[0].clips[0].effects[0].params['value'] == .8


def test_compatible_tracks_and_sorting_moved_clips(project):
    _, store = project
    edit(project, {'kind':'set_track_properties','track_id':'audio','track_kind':'audio','label':'Music'})
    with pytest.raises(ValueError, match='compatible'):
        edit(project, {'kind':'move_clip','clip_id':'base','new_track_id':'audio','new_position_sec':0})
    edit(project, {'kind':'duplicate_clip','clip_id':'base','new_clip_id':'first','position_sec':0,'new_track_id':'new','effect_ids':{'bright':'first-effect'}},
         {'kind':'move_clip','clip_id':'base','new_track_id':'new','new_position_sec':5})
    # Replay insertion order differs from timeline order after the move.
    xml = etree.fromstring(emit_timeline(derive(store), EmitterConfig(enable_audio_micro_fades=False)).encode())
    entries = xml.xpath('//playlist[@id="playlist_new"]/entry')
    assert len(entries)==2 and entries[0].find('filter').get('id')=='first-effect'


def test_solo_hidden_picture_and_upper_track_audio_survive_projection(project):
    _, store = project
    edit(project, {'kind':'set_track_properties','track_id':'v2','solo':True,'hidden':True})
    rendered = timeline_for_melt(derive(store))
    assert not any(t.track_id=='v2' for t in rendered.tracks)
    upper = next(t for t in rendered.tracks if t.track_id=='audio:v2')
    base = next(t for t in rendered.tracks if t.track_id=='v1')
    assert not upper.muted and base.muted
    # A solo track outside a preview range must still mute other tracks there.
    sliced = slice_timeline(derive(store), render_start_frame=0,render_end_frame=15,fps_num=30,fps_den=1,plane='audio')
    assert all(t.muted for t in sliced.tracks)
    xml = etree.fromstring(emit_timeline(rendered).encode())
    assert xml.xpath('//multitrack/track[@producer="playlist_audio:v2"]')[0].get('hide')=='video'


def test_upper_layer_trim_and_stacking_are_preserved(project):
    _, store = project
    current = derive(store)
    overlays = _video_track_overlay_clips(current, {'one':'/base.mov','two':'/upper.mov'})
    assert overlays[0].in_point_sec == 2 and overlays[0].z_index == 1
    graph = ';'.join(overlay_filter_chain(overlays, 320, 180))
    assert 'trim=start=2.0:duration=2.0' in graph
    assert 'setpts=PTS-STARTPTS+1.0/TB' in graph


def test_linear_audio_gain_uses_mlt_decibels():
    from open_edit.ir.types import Effect
    from open_edit.render.emitter import _emit_filter

    parent = etree.Element('entry')
    _emit_filter(parent, Effect(effect_id='gain',effect_type='volume',params={'gain':.5},keyframes={'gain':[(0,.5,'linear'),(1,1,'linear')]}),30,1)
    assert float(parent.find('filter/property').text) == pytest.approx(-6.0206)
    assert '-6.020599' in parent.findall('filter/property')[1].text
