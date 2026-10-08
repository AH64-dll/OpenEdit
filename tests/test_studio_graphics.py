"""Source-backed graphics retain their identity through editing and rendering."""
import pytest

from open_edit.integrations.diffusion.graphics import DEFAULT_SOURCE, graphics_ready
from open_edit.ir.apply_common import ApplyError
from open_edit.ir.derive import derive_timeline
from open_edit.ir.types import (
    AddEffectOp,
    MoveClipOp,
    Project,
    RemoveGraphicsSourceOp,
    SetGraphicsSourceOp,
    SplitClipOp,
    TrimClipOp,
)
from open_edit.kernel.studio_service import commit_studio, get_studio
from open_edit.render.preview_invalidation import slice_timeline
from open_edit.render.studio_graphics import materialize_graphics_documents
from open_edit.storage.edit_graph import EditGraphStore


def source_op(**overrides):
    return SetGraphicsSourceOp(author='ai', document_id='title-doc', clip_id='title-clip',
                               source=DEFAULT_SOURCE, duration_sec=3, fps=30, **overrides)


def timeline(ops):
    return derive_timeline(Project(name='source-backed', edit_graph=ops), strict=True)


def test_source_clip_can_move_trim_and_have_effects_before_materialization(tmp_path):
    store = EditGraphStore(tmp_path / 'graph.db')
    store.append(source_op())
    store.append_many([
        MoveClipOp(author='user', clip_id='title-clip', new_track_id='V2', new_position_sec=4),
        TrimClipOp(author='user', clip_id='title-clip', new_in_point_sec=0.5, new_out_point_sec=2.5),
        AddEffectOp(author='user', target_kind='clip', target_id='title-clip', effect_type='brightness', params={'value': 0.8}),
    ])
    current = timeline(store.load_all())
    clip = next(c for t in current.tracks for c in t.clips)
    assert clip.document_id == 'title-doc' and clip.position_sec == 4
    assert clip.in_point_sec == 0.5 and clip.out_point_sec == 2.5
    updated = source_op().model_copy(update={'source': DEFAULT_SOURCE.replace('Your title', 'Updated'), 'duration_sec': 4})
    store.append(updated)
    after = timeline(store.load_all())
    clip = next(c for t in after.tracks for c in t.clips)
    assert clip.track_id == 'V2' and clip.position_sec == 4 and clip.out_point_sec == 2.5
    assert clip.effects[0].params['value'] == 0.8
    store.history_step('undo', store.graph_revision())
    assert timeline(store.load_all()).graphics_documents['title-doc']['source'] == DEFAULT_SOURCE


def test_full_source_duration_updates_but_explicit_trim_cannot_be_erased():
    first = source_op()
    longer = source_op().model_copy(update={'duration_sec': 5})
    assert timeline([first, longer]).tracks[0].clips[0].out_point_sec == 5
    shorter = source_op().model_copy(update={'duration_sec': 1})
    trim = TrimClipOp(author='user', clip_id='title-clip', new_in_point_sec=0.5, new_out_point_sec=2)
    with pytest.raises(ApplyError, match='explicit clip trim'):
        timeline([first, trim, shorter])


def test_source_updates_preserve_split_instances_and_validate_every_trim():
    first = source_op()
    split = SplitClipOp(author='user', clip_id='title-clip', at_sec=1,
                        left_clip_id='left', right_clip_id='right')
    changed = source_op().model_copy(update={'source': DEFAULT_SOURCE.replace('Your title', 'Updated'), 'duration_sec': 4})
    derived = timeline([first, split, changed])
    clips = [c for t in derived.tracks for c in t.clips]
    assert [c.clip_id for c in clips] == ['left', 'right']
    assert all(c.document_id == 'title-doc' for c in clips)
    assert [(c.in_point_sec, c.out_point_sec) for c in clips] == [(0, 1), (1, 3)]
    with pytest.raises(ApplyError, match='explicit clip trim'):
        timeline([first, split, source_op().model_copy(update={'duration_sec': 2})])
    from open_edit.ir.validate import _known_ids_from_ops

    assert _known_ids_from_ops([first, split, changed])[0] == {'left', 'right'}
    removed = RemoveGraphicsSourceOp(author='user', document_id='title-doc')
    assert not _known_ids_from_ops([first, split, changed, removed])[0]


def test_materialization_binds_checked_media_to_a_copy_preserving_source(monkeypatch):
    original = timeline([source_op()])
    calls = []
    def render(root, params):
        calls.append(params)
        return {'asset_hash': 'a' * 64, 'qc_report': {'passed': True}}
    monkeypatch.setattr('open_edit.integrations.diffusion.graphics.materialize', render)
    rendered = materialize_graphics_documents(original, '/unused')
    assert len(calls) == 1
    assert original.tracks[0].clips[0].asset_hash == 'studio:title-doc'
    assert rendered.tracks[0].clips[0].asset_hash == 'a' * 64
    assert rendered.graphics_documents == original.graphics_documents
    materialize_graphics_documents(rendered, '/unused')
    assert len(calls) == 1
    audio = slice_timeline(original, render_start_frame=0, render_end_frame=30, fps_num=30, fps_den=1, plane='audio')
    assert not audio.tracks  # graphics are silent and never decode a virtual asset as audio
    video = slice_timeline(original, render_start_frame=15, render_end_frame=30, fps_num=30, fps_den=1, plane='video')
    assert video.tracks[0].clips[0].in_point_sec == 0.5
    assert video.graphics_documents == original.graphics_documents


def test_disabled_document_and_failed_qc_never_publish_media(monkeypatch):
    hidden = timeline([source_op(enabled=False)])
    monkeypatch.setattr('open_edit.integrations.diffusion.graphics.materialize', lambda *a: pytest.fail('Hidden graphics must not render'))
    assert not materialize_graphics_documents(hidden, '/unused').tracks[0].clips
    monkeypatch.setattr('open_edit.integrations.diffusion.graphics.materialize', lambda *a: {'asset_hash': 'a', 'qc_report': {'passed': False}})
    with pytest.raises(ValueError, match='quality'):
        materialize_graphics_documents(timeline([source_op()]), '/unused')


def test_remove_document_removes_clip_and_undo_restores_both(tmp_path):
    store = EditGraphStore(tmp_path / 'graph.db')
    store.append(source_op())
    store.append(RemoveGraphicsSourceOp(author='user', document_id='title-doc'))
    assert not timeline(store.load_all()).graphics_documents
    assert not timeline(store.load_all()).tracks[0].clips
    store.history_step('undo', store.graph_revision())
    assert timeline(store.load_all()).tracks[0].clips[0].document_id == 'title-doc'


def test_real_compiler_commit_reopen_undo_redo_and_compact_query(tmp_path):
    if not graphics_ready():
        pytest.skip('Optional graphics compiler not installed')
    store = EditGraphStore(tmp_path / '.open_edit/edit_graph.db')
    data = {'source': DEFAULT_SOURCE, 'clip_id': 'lower-third'}
    change = {'kind': 'document', 'object_id': 'lower-third-doc', 'data': data}
    result = commit_studio(tmp_path, expected_revision=0, changes=[change], author='ai', request_id='create-title')
    assert result['changed'] and result['graph_revision'] == 1
    compact = get_studio(tmp_path)
    assert 'source' not in compact['objects'][0]['data']
    assert 'elements' not in compact['objects'][0]['data']
    expanded = get_studio(tmp_path, include_source=True)
    assert expanded['objects'][0]['data']['source'] == DEFAULT_SOURCE
    assert expanded['objects'][0]['data']['elements'][-1]['text'] == 'Your title'
    store = EditGraphStore(store.db_path)
    assert timeline(store.load_all()).tracks[0].clips[0].document_id == 'lower-third-doc'
    store.history_step('undo', 1)
    assert not get_studio(tmp_path)['objects']
    assert not timeline(store.load_all()).tracks
    store.history_step('redo', 2)
    assert get_studio(tmp_path, include_source=True)['objects'][0]['data']['source'] == DEFAULT_SOURCE


def test_layer_lock_blocks_ai_source_changes_and_combined_unlock(tmp_path):
    if not graphics_ready():
        pytest.skip('Optional graphics compiler not installed')
    EditGraphStore(tmp_path / '.open_edit/edit_graph.db')
    data = {'source': DEFAULT_SOURCE, 'clip_id': 'title', 'locked_ids': ['title']}
    change = {'kind': 'document', 'object_id': 'doc', 'data': data}
    commit_studio(tmp_path, expected_revision=0, changes=[change])
    for locks in [['title'], []]:
        with pytest.raises(ValueError, match='Unlock'):
            commit_studio(tmp_path, expected_revision=1, author='ai', changes=[{
                **change, 'data': {**data, 'locked_ids': locks, 'source': DEFAULT_SOURCE.replace('Your title', 'Changed')}}])
    assert get_studio(tmp_path)['graph_revision'] == 1
    commit_studio(tmp_path, expected_revision=1, changes=[{**change, 'data': {**data, 'locked_ids': []}}])
    commit_studio(tmp_path, expected_revision=2, author='ai', changes=[{**change, 'data': {
        **data, 'locked_ids': [], 'source': DEFAULT_SOURCE.replace('Your title', 'Changed')}}])
    assert get_studio(tmp_path, include_source=True)['objects'][0]['data']['source'].find('Changed') >= 0


def test_raw_graphics_ops_cannot_bypass_source_objects(tmp_path):
    EditGraphStore(tmp_path / '.open_edit/edit_graph.db')
    with pytest.raises(ValueError, match='document objects'):
        commit_studio(tmp_path, expected_revision=0, changes=[], ops=[source_op().model_dump(mode='json')])


def test_all_graph_writers_protect_locked_and_source_backed_clips(tmp_path):
    if not graphics_ready():
        pytest.skip('Optional graphics compiler not installed')
    from open_edit.ir.types import ReplaceClipSourceOp

    store = EditGraphStore(tmp_path / '.open_edit/edit_graph.db')
    commit_studio(tmp_path, expected_revision=0, changes=[{'kind': 'document', 'object_id': 'doc',
        'data': {'source': DEFAULT_SOURCE, 'clip_id': 'clip', 'locked': True}}])
    for op in [MoveClipOp(author='ai', clip_id='clip', new_track_id='V2', new_position_sec=4),
               ReplaceClipSourceOp(author='ai', clip_id='clip', new_asset_hash='a' * 64),
               SetGraphicsSourceOp(author='ai', document_id='doc', clip_id='clip', source=DEFAULT_SOURCE, duration_sec=3, fps=30)]:
        with pytest.raises(ValueError):
            store.append(op)
    assert store.graph_revision() == 1


def test_editor_compilation_preserves_source_validates_and_rejects_stale(tmp_path):
    if not graphics_ready():
        pytest.skip('Optional graphics compiler not installed')
    from open_edit.integrations.diffusion.graphics import compile_editor, editor_bundle
    from open_edit.storage.edit_graph import GraphRevisionConflict

    store = EditGraphStore(tmp_path / '.open_edit/edit_graph.db')
    compiled = compile_editor(tmp_path, source=DEFAULT_SOURCE, expected_revision=0)
    assert compiled['source'] == DEFAULT_SOURCE
    assert compiled['asset_manifest'] == [] and compiled['scene']['width'] == 960
    assert 'exports' in compiled['code'] and b'OpenEditCanvas' in editor_bundle()
    with pytest.raises(ValueError):
        compile_editor(tmp_path, source='export default function() { return process.exit(); }', expected_revision=0)
    store.append(source_op())
    with pytest.raises(GraphRevisionConflict):
        compile_editor(tmp_path, source=DEFAULT_SOURCE, expected_revision=0)


@pytest.mark.browser
def test_source_backed_timeline_export_is_checked_and_excludes_marks(tmp_path, monkeypatch):
    import shutil
    import subprocess
    from pathlib import Path

    from PIL import Image

    from open_edit.render.orchestrator import render_project

    if not graphics_ready() or not shutil.which('melt'):
        pytest.skip('Real graphics browser and MLT required')
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    monkeypatch.setenv('SDL_VIDEODRIVER', 'dummy')
    store = EditGraphStore(tmp_path / '.open_edit/edit_graph.db')
    source = '''export default function Graphics() { return <stage id="stage">
      <scene id="scene" width={320} height={180} active>
        <rect id="box" x={30} y={20} width={60} height={40} fill="#ff0000" end={0.3}/>
      </scene></stage>; }'''
    commit_studio(tmp_path, expected_revision=0, changes=[
        {'kind': 'document', 'object_id': 'doc', 'data': {'source': source, 'clip_id': 'clip', 'duration_sec': 0.3}},
        {'kind': 'annotation', 'object_id': 'private-mark', 'data': {'tool': 'rectangle',
          'points': [[200, 100], [300, 160]], 'text': 'This must not export', 'color': '#ffffff'}},
    ])
    revision = store.graph_revision()
    result = render_project(project_id='studio', project_dir=tmp_path, workdir=tmp_path / 'renders',
                            mode='proxy', overrides={'scale': '320x180'}, encoder_backend='cpu', force=True)
    assert result.ok, result.error
    raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', result.output_path,
                                   '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'])
    frame = Image.frombytes('RGB', (320, 180), raw)
    assert frame.getpixel((50, 40))[0] > 200
    assert max(frame.getpixel((200, 100))) < 30 and max(frame.getpixel((250, 130))) < 30
    artifacts = Path('tests/browser/artifacts')
    artifacts.mkdir(parents=True, exist_ok=True)
    frame.save(artifacts / 'studio-source-timeline-export.png')
    assert store.graph_revision() == revision and len(store.load_all()) == 1
    assert get_studio(tmp_path, include_source=True)['objects'][-1]['data']['source'] == source
