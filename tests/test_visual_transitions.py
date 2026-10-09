"""Non-destructive cut controls and decoded crossfade/wipe pixels."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from open_edit.ir.derive import derive_timeline
from open_edit.ir.types import AddClipOp, AddTransitionOp, Project
from open_edit.kernel.studio_service import commit_studio
from open_edit.render.preview_invalidation import slice_timeline
from open_edit.render.profiles import RenderProfile
from open_edit.render.visual_transitions import transition_overlay
from open_edit.storage.edit_graph import EditGraphStore


def timeline(kind='dissolve'):
    return derive_timeline(Project(name='transitions', edit_graph=[
        AddClipOp(author='user', clip_id='a', asset_hash='a', track_id='v', position_sec=0, in_point_sec=.5, out_point_sec=2.5),
        AddClipOp(author='user', clip_id='b', asset_hash='b', track_id='v', position_sec=2, in_point_sec=.5, out_point_sec=2.5),
        AddTransitionOp(author='user', edit_id='cut', clip_a_id='a', clip_b_id='b', duration_sec=1, transition_type=kind, layout='centered'),
    ]), strict=True)


def test_transition_keeps_trim_cut_history_and_validates_resizing(tmp_path):
    store = EditGraphStore(tmp_path / '.open_edit/edit_graph.db')
    commit_studio(tmp_path, expected_revision=0, changes=[], ops=[
        {'kind':'add_clip','clip_id':'a','asset_hash':'a','track_id':'v','position_sec':0,'out_point_sec':2},
        {'kind':'add_clip','clip_id':'b','asset_hash':'b','track_id':'v','position_sec':2,'out_point_sec':2},
        {'kind':'add_transition','edit_id':'cut','clip_a_id':'a','clip_b_id':'b','duration_sec':1,'transition_type':'dissolve','layout':'centered'},
    ])
    def current():
        return derive_timeline(Project(name='transitions', edit_graph=store.load_all()), strict=True)
    assert current().duration_sec == 4
    assert [(c.position_sec,c.in_point_sec,c.out_point_sec) for c in current().tracks[0].clips] == [(0,0,2),(2,0,2)]
    revision = store.graph_revision()
    for value in ['nan','0','3']:
        with pytest.raises(ValueError):
            commit_studio(tmp_path, expected_revision=revision, changes=[], ops=[{'kind':'set_transition_property','transition_id':'transition_cut','prop_name':'duration_sec','value':value}])
    assert store.graph_revision() == revision
    commit_studio(tmp_path, expected_revision=revision, changes=[], ops=[{'kind':'set_transition_property','transition_id':'transition_cut','prop_name':'type','value':'wipe'}])
    assert current().visual_transitions[0].kind == 'wipe'
    commit_studio(tmp_path, expected_revision=store.graph_revision(), changes=[], ops=[{'kind':'remove_transition','transition_id':'transition_cut'}])
    assert not current().visual_transitions and current().tracks[0].clips[0].out_point_sec == 2
    store.history_step('undo',store.graph_revision())
    assert current().visual_transitions[0].kind == 'wipe'


def test_transition_slice_retains_both_source_windows_and_offset():
    source = timeline()
    sliced = slice_timeline(source, render_start_frame=48,render_end_frame=60,fps_num=24,fps_den=1,plane='video')
    spec = sliced.visual_transitions[0]
    assert spec.position_sec == 0 and spec.in_point_sec == .5 and spec.visible_duration_sec == .5
    assert spec.clip_a.in_point_sec == .5 and spec.clip_a.out_point_sec == 2.5
    assert len(sliced.tracks[0].clips) == 1
    assert not slice_timeline(source,render_start_frame=0,render_end_frame=96,fps_num=24,fps_den=1,plane='audio').visual_transitions


def compositor_pixels(tmp_path, monkeypatch, *, real_mlt):
    if real_mlt and not shutil.which('melt'):
        pytest.skip('Actual MLT is required')
    paths = {}
    for name,color in [('a','red'),('b','blue')]:
        path=tmp_path/f'{name}.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',f'color=c={color}:s=320x180:r=24:d=3','-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True)
        paths[name]=str(path)
    if not real_mlt:
        def extract(track,duration,asset_paths,cache_dir,profile):
            clip=track.clips[0]
            out=tmp_path/f'{clip.clip_id}-half.mov'
            subprocess.run(['ffmpeg','-v','error','-y','-ss',str(clip.in_point_sec),'-i',asset_paths[clip.asset_hash],'-t',str(duration),'-an','-c:v','qtrle','-pix_fmt','argb',str(out)],check=True)
            return out
        monkeypatch.setattr('open_edit.render.visual_transitions.materialize_layer',extract)
    profile=RenderProfile(name='transition-test',width=320,height=180,frame_rate_num=24,frame_rate_den=1)
    evidence={}
    for kind in ['dissolve','wipe']:
        spec=timeline(kind).visual_transitions[0]
        overlay=transition_overlay(spec,paths,tmp_path/'cache',profile)
        def pixel(time,x,overlay=overlay):
            data=subprocess.check_output(['ffmpeg','-v','error','-ss',str(time),'-i',str(overlay.media_path),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
            return list(data[(90*320+x)*3:(90*320+x)*3+3])
        if kind=='dissolve':
            early,middle,late=pixel(.05,160),pixel(.5,160),pixel(.95,160)
            assert early[0]>200 and early[2]<40
            assert 90<middle[0]<170 and 90<middle[2]<170
            assert late[2]>200 and late[0]<40
            evidence[kind]=[early,middle,late]
        else:
            left,right=pixel(.5,40),pixel(.5,280)
            assert left[2]>200 and right[0]>200
            evidence[kind]=[left,right]
    return evidence


def test_actual_ffmpeg_transition_pixels(tmp_path,monkeypatch):
    compositor_pixels(tmp_path,monkeypatch,real_mlt=False)


@pytest.mark.browser
def test_actual_mlt_transition_pixels(tmp_path,monkeypatch):
    evidence=compositor_pixels(tmp_path,monkeypatch,real_mlt=True)
    artifact=Path('tests/browser/artifacts/studio-transitions.json')
    artifact.parent.mkdir(parents=True,exist_ok=True)
    artifact.write_text(json.dumps(evidence))
