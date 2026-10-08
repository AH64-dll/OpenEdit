"""Real compiler/IR/MCP round trips and atomic failure boundaries."""
from __future__ import annotations

import json
import sys

import pytest

from open_edit.integrations.diffusion import authoring, compiler
from open_edit.ir.derive import derive_timeline
from open_edit.ir.types import (
    AddClipOp,
    AddEffectOp,
    AddHtmlOverlayOp,
    Asset,
    Project,
    SetAudioGainOp,
    TrimClipOp,
)
from open_edit.kernel.pillar_tools import dispatch_edit, dispatch_query
from open_edit.storage.edit_graph import EditGraphStore, GraphRevisionConflict


@pytest.fixture
def project(tmp_path):
    store = EditGraphStore(tmp_path / '.open_edit/edit_graph.db')
    for hash_, kind in [('video', 'video'), ('other', 'video'), ('music', 'audio'), ('still', 'image')]:
        folder = tmp_path / '.open_edit/assets' / hash_[:2]
        folder.mkdir(parents=True, exist_ok=True)
        asset = Asset(asset_hash=hash_, original_path=hash_, stored_path=hash_, type=kind, duration_sec=20 if kind != 'image' else 0)
        (folder / f'{hash_}.meta.json').write_text(asset.model_dump_json())
    store.append_many([
        AddClipOp(author='ai', clip_id='hero', asset_hash='video', track_id='main', position_sec=0, out_point_sec=5),
        AddClipOp(author='ai', clip_id='music', asset_hash='music', track_id='audio', track_kind='audio', position_sec=0, out_point_sec=5),
        AddClipOp(author='ai', clip_id='photo', asset_hash='still', track_id='images', position_sec=0, out_point_sec=3),
    ])
    return tmp_path, store


@pytest.fixture
def real_worker():
    if not compiler.worker_ready():
        pytest.skip('Optional Diffusion worker not installed; run python -m open_edit.integrations.diffusion.setup')


def view(path):
    return authoring.get_authoring_view(path, include_source=True)


def timeline(path, store):
    return derive_timeline(Project(project_id=store.project_id, name='p', workdir=path, edit_graph=store.load_all()))


def edit(path, store, edits):
    return authoring.apply_authoring_edit(path, expected_revision=store.graph_revision(), edits=edits)


def test_compact_export_without_optional_worker(project, monkeypatch):
    path, _ = project
    monkeypatch.setenv('OPEN_EDIT_DIFFUSION_WORKER_DIR', str(path / 'missing'))
    summary = dispatch_query('get_authoring_view', {}, path)
    assert summary['status'] == 'ok'
    assert summary['clip_count'] == 3
    assert summary['worker_ready'] is False
    assert 'source' not in summary
    full = dispatch_query('get_authoring_view', {'include_source': True}, path)
    assert '<video id="c-hero"' in full['source']
    assert '<audio id="c-music"' in full['source']
    assert '<image id="c-photo"' in full['source']
    result = dispatch_edit('apply_authoring_edit', {'source': full['source'], 'expected_revision': full['graph_revision']}, path)
    assert result['status'] == 'error'
    assert 'install' in result['error'].lower()


def test_noop_round_trip_does_not_increment_revision(project, real_worker):
    path, store = project
    before = view(path)
    result = authoring.apply_authoring_edit(path, expected_revision=before['graph_revision'], source=before['source'])
    assert result['ops_appended'] == 0
    assert store.graph_revision() == before['graph_revision']
    assert view(path)['source'] == before['source']


def test_actual_writeback_moves_trims_and_sets_absolute_volume(project, real_worker):
    path, store = project
    store.append(SetAudioGainOp(author='ai', clip_id='hero', gain_db=-3))
    result = edit(path, store, [{'kind': 'set', 'source': 'index.tsx:c-hero', 'props': {'start': 3, 'sourceIn': 2, 'sourceOut': 7, 'volume': -6}}])
    assert result['ops_appended'] == 3
    assert len(result['compiled_hash']) == 64
    clip = timeline(path, store).tracks[0].clips[0]
    assert (clip.position_sec, clip.in_point_sec, clip.out_point_sec) == (3, 2, 7)
    assert authoring._gain_db(clip) == pytest.approx(-6)
    repeated = edit(path, store, [{'kind': 'set', 'source': 'index.tsx:c-hero', 'props': {'volume': -6}}])
    assert repeated['ops_appended'] == 0
    changed = edit(path, store, [{'kind': 'set', 'source': 'index.tsx:c-hero', 'props': {'volume': -1}}])
    assert changed['ops_appended'] == 1
    assert authoring._gain_db(timeline(path, store).tracks[0].clips[0]) == pytest.approx(-1)


def test_full_source_can_add_media_and_append_a_track(project, real_worker):
    path, store = project
    exported = view(path)
    source = exported['source'].replace('      </scene>', '''        <group id="t-extra">
          <video id="c-new" src={"asset://other"} start={6} sourceIn={1} sourceOut={4} />
        </group>
      </scene>''')
    result = authoring.apply_authoring_edit(path, expected_revision=exported['graph_revision'], source=source)
    assert result['ops_appended'] == 1
    clip = timeline(path, store).tracks[-1].clips[0]
    assert (clip.clip_id, clip.track_id, clip.asset_hash) == ('new', 'extra', 'other')
    assert authoring.apply_authoring_edit(path, expected_revision=store.graph_revision(), source=view(path)['source'])['ops_appended'] == 0


def test_remove_and_replace_source(project, real_worker):
    path, store = project
    result = edit(path, store, [
        {'kind': 'remove', 'source': 'index.tsx:c-photo'},
        {'kind': 'set', 'source': 'index.tsx:c-hero', 'props': {'src': 'asset://other'}},
    ])
    assert result['ops_appended'] == 2
    current = timeline(path, store)
    assert current.tracks[0].clips[0].asset_hash == 'other'
    assert current.tracks[2].clips == []


def test_move_between_existing_video_tracks(project, real_worker):
    path, store = project
    result = edit(path, store, [
        {'kind': 'set', 'source': 'index.tsx:c-hero', 'props': {'start': 4}},
        {'kind': 'move', 'source': 'index.tsx:c-hero', 'parent': 'index.tsx:t-images'},
    ])
    assert result['ops_appended'] == 1
    current = timeline(path, store)
    assert current.tracks[0].clips == []
    assert current.tracks[2].clips[-1].clip_id == 'hero'
    assert current.tracks[2].clips[-1].position_sec == 4


def test_stale_unchanged_source_is_rejected_before_compiler(project, monkeypatch):
    path, store = project
    exported = view(path)
    store.append(SetAudioGainOp(author='ai', clip_id='hero', gain_db=-2))
    monkeypatch.setattr(authoring, 'parse_and_compile', lambda *a, **kw: pytest.fail('stale source must fail first'))
    result = dispatch_edit('apply_authoring_edit', {'source': exported['source'], 'expected_revision': exported['graph_revision']}, path)
    assert result['error_code'] == 'stale_revision'
    assert result['graph_revision'] == store.graph_revision()


def test_concurrent_write_during_compile_is_rejected(project, real_worker, monkeypatch):
    path, store = project
    original = authoring.parse_and_compile
    revision = store.graph_revision()
    def concurrent(*args, **kwargs):
        result = original(*args, **kwargs)
        store.append(SetAudioGainOp(author='ai', clip_id='hero', gain_db=-2))
        return result
    monkeypatch.setattr(authoring, 'parse_and_compile', concurrent)
    with pytest.raises(GraphRevisionConflict):
        authoring.apply_authoring_edit(path, expected_revision=revision, source=view(path)['source'])
    assert len(store.load_all()) == 4


@pytest.mark.parametrize('props', [
    {'sourceOut': 100}, {'sourceIn': -1}, {'sourceOut': 0}, {'start': -1},
    {'volume': 1000}, {'playbackRate': 2}, {'src': '/tmp/outside.mp4'}, {'src': 'asset://missing'},
])
def test_invalid_late_change_rolls_back_entire_batch(project, real_worker, props):
    path, store = project
    before = view(path)
    result = dispatch_edit('apply_authoring_edit', {'expected_revision': before['graph_revision'], 'edits': [
        {'kind': 'set', 'source': 'index.tsx:c-hero', 'props': {'start': 2}},
        {'kind': 'set', 'source': 'index.tsx:c-music', 'props': props},
    ]}, path)
    assert result['status'] == 'error'
    assert store.graph_revision() == before['graph_revision']
    assert view(path)['source'] == before['source']


@pytest.mark.parametrize('replacement', [
    '<text id="c-hero">unsupported</text>',
    '<video id="c-hero" {...props} />',
    '<video id="c-hero" src={doWork()} start={0} sourceIn={0} sourceOut={5} />',
])
def test_unsupported_source_does_not_mutate_graph(project, real_worker, replacement):
    path, store = project
    before = view(path)
    line = next(line for line in before['source'].splitlines() if '<video ' in line)
    source = before['source'].replace(line, replacement)
    with pytest.raises(ValueError):
        authoring.apply_authoring_edit(path, expected_revision=before['graph_revision'], source=source)
    assert store.graph_revision() == before['graph_revision']


def test_preserves_existing_visual_effects_and_overlays(project, real_worker):
    path, store = project
    store.append_many([
        AddEffectOp(author='ai', target_kind='clip', target_id='hero', effect_type='blur', params={'radius': 2}),
        AddHtmlOverlayOp(author='ai', overlay_id='overlay', template_path='title.html', position_sec=0, duration_sec=2),
    ])
    before = timeline(path, store)
    result = edit(path, store, [{'kind': 'set', 'source': 'index.tsx:c-hero', 'props': {'start': 2}}])
    assert result['ops_appended'] == 1
    after = timeline(path, store)
    assert after.overlays == before.overlays
    assert after.tracks[0].clips[0].effects == before.tracks[0].clips[0].effects


def test_worker_timeout_leaves_graph_and_source_unchanged(project, real_worker, monkeypatch):
    path, store = project
    before = view(path)
    monkeypatch.setattr(compiler, 'WORKER_TIMEOUT_SEC', 0.01)
    with pytest.raises(compiler.CompilerError, match='timed out'):
        authoring.apply_authoring_edit(path, expected_revision=before['graph_revision'], source=before['source'])
    assert store.graph_revision() == before['graph_revision']
    assert view(path)['source'] == before['source']


def test_noop_append_still_checks_revision(project):
    _, store = project
    revision = store.graph_revision()
    store.append(SetAudioGainOp(author='ai', clip_id='hero', gain_db=-1))
    with pytest.raises(GraphRevisionConflict):
        store.append_many([], expected_revision=revision)


def test_snapshot_keeps_revision_and_operations_consistent_during_write(project, monkeypatch):
    _, store = project
    writer = EditGraphStore(store.db_path)
    revision = store.graph_revision()
    original = store._load_all_in
    def write_between_reads(conn):
        # WAL allows another connection to commit while the export's read
        # transaction remains on its original snapshot.
        writer.append(SetAudioGainOp(author='ai', clip_id='hero', gain_db=-1))
        return original(conn)
    monkeypatch.setattr(store, '_load_all_in', write_between_reads)
    exported_revision, ops = store.read_snapshot()
    assert exported_revision == revision
    assert len(ops) == 3
    assert store.graph_revision() == revision + 1


def test_escaped_identities_round_trip_through_actual_source_writer(project, real_worker):
    path, store = project
    identity = 'حركة: clip/one'
    track = 'track: واحد'
    store.append(AddClipOp(author='ai', clip_id=identity, asset_hash='other', track_id=track, position_sec=0, out_point_sec=2))
    result = edit(path, store, [{'kind': 'set', 'source': f'index.tsx:{authoring.element_id("c", identity)}', 'props': {'start': 7}}])
    assert result['changed_clip_ids'] == [identity]
    assert timeline(path, store).tracks[-1].clips[0].position_sec == 7
    assert authoring.apply_authoring_edit(path, expected_revision=store.graph_revision(), source=view(path)['source'])['ops_appended'] == 0


def test_missing_source_edit_rolls_back_prior_writeback_and_worker_restarts(project, real_worker):
    path, store = project
    before = view(path)
    with pytest.raises(compiler.CompilerError, match='could not be applied'):
        edit(path, store, [
            {'kind': 'set', 'source': 'index.tsx:c-hero', 'props': {'start': 2}},
            {'kind': 'remove', 'source': 'index.tsx:c-missing'},
        ])
    assert store.graph_revision() == before['graph_revision']
    assert view(path)['source'] == before['source']
    assert edit(path, store, [{'kind': 'set', 'source': 'index.tsx:c-hero', 'props': {'start': 2}}])['ops_appended'] == 1


@pytest.mark.parametrize('change', ['duplicate', 'reorder', 'overlap', 'scene'])
def test_invalid_document_structure_is_atomic(project, real_worker, change):
    path, store = project
    before = view(path)
    source = before['source']
    if change == 'duplicate':
        source = source.replace('c-photo', 'c-hero')
    elif change == 'reorder':
        source = source.replace('t-main', 't-swap').replace('t-audio', 't-main').replace('t-swap', 't-audio')
    elif change == 'overlap':
        source = source.replace('        <group id="t-main">', '        <group id="t-main">\n          <video id="c-overlap" src={"asset://other"} start={2} sourceIn={0} sourceOut={5} />')
    else:
        source = source.replace('width={1920}', 'width={720}')
    with pytest.raises(ValueError):
        authoring.apply_authoring_edit(path, expected_revision=before['graph_revision'], source=source)
    assert store.graph_revision() == before['graph_revision']


def test_export_rejects_unrepresentable_existing_range(project):
    path, store = project
    store.append(TrimClipOp(author='ai', clip_id='hero', new_in_point_sec=0, new_out_point_sec=100))
    with pytest.raises(ValueError, match='exceeds asset duration'):
        view(path)


def test_project_javascript_is_rejected_without_execution(project, real_worker):
    path, store = project
    before = view(path)
    marker = path / 'executed.txt'
    source = f'import fs from "node:fs"; fs.writeFileSync({json.dumps(str(marker))}, "executed");\n' + before['source']
    with pytest.raises(compiler.CompilerError, match='other statements/imports'):
        authoring.apply_authoring_edit(path, expected_revision=before['graph_revision'], source=source)
    assert not marker.exists()
    assert store.graph_revision() == before['graph_revision']


@pytest.mark.asyncio
async def test_real_stdio_authoring_round_trip(project, real_worker):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    path, store = project
    parameters = StdioServerParameters(command=sys.executable, args=['-m', 'open_edit.mcp.server', '--project', str(path)])
    async with stdio_client(parameters) as (reader, writer), ClientSession(reader, writer) as session:
        initialized = await session.initialize()
        assert len(initialized.instructions.encode()) < 2000
        assert len((await session.list_tools()).tools) == 6
        result = await session.call_tool('query_project', {'query': 'get_authoring_view', 'params': {'include_source': True}})
        assert not result.isError
        source = json.loads(result.content[0].text)
        result = await session.call_tool('edit_project', {'operation': 'apply_authoring_edit', 'params': {'expected_revision': source['graph_revision'], 'edits': [{'kind': 'set', 'source': 'index.tsx:c-hero', 'props': {'start': 4}}]}})
        assert not result.isError
        assert json.loads(result.content[0].text)['ops_appended'] == 1
        stale = await session.call_tool('edit_project', {'operation': 'apply_authoring_edit', 'params': {'expected_revision': source['graph_revision'], 'source': source['source']}})
        assert stale.isError
    assert timeline(path, store).tracks[0].clips[0].position_sec == 4
