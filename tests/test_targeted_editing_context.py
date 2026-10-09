"""ROI delivery, bounded context and source-free edits through real shared APIs."""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from open_edit.ir.types import AddClipOp
from open_edit.kernel.pillar_tools import dispatch_edit, dispatch_query
from open_edit.kernel.studio_service import (
    commit_studio,
    get_editing_context,
    get_studio,
    save_editing_selection,
)
from open_edit.serve.app import app
from open_edit.serve.routers import studio as routes
from open_edit.storage.edit_graph import EditGraphStore, GraphRevisionConflict


@pytest.fixture
def project(tmp_path):
    store = EditGraphStore(tmp_path / '.open_edit/edit_graph.db')
    store.append_many([AddClipOp(author='user', clip_id='hero', asset_hash='a' * 64, track_id='video',
                               position_sec=1, in_point_sec=2, out_point_sec=6),
                       AddClipOp(author='user', clip_id='sound', asset_hash='b' * 64, track_id='audio', track_kind='audio',
                                 position_sec=1, out_point_sec=5)])
    return tmp_path, store


def region(**values):
    return {'left': 100, 'right': 300, 'top': 30, 'bottom': 150,
            'canvas_width': 640, 'canvas_height': 360, 'playhead_sec': 2, **values}


def focus(root, store, **values):
    return save_editing_selection(root, expected_revision=store.graph_revision(), selected_ids=[],
                                 annotation_ids=[], document_id=None, playhead_sec=4, **values)


def test_region_survives_external_query_at_its_anchor_without_history(project, monkeypatch):
    root, store = project
    before = store.history()
    # Saving focus does not derive the graph or serialize all source objects.
    with monkeypatch.context() as patch:
        patch.setattr('open_edit.kernel.studio_service.get_editing_context', lambda *a, **k: pytest.fail('Focus replayed graph'))
        focus(root, store, region=region())
    context = dispatch_query('get_editing_context', {}, root)
    assert context['region']['canvas_width'] == 640
    assert context['region']['playhead_sec'] == 2 and context['playhead_sec'] == 4
    assert [c['clip_id'] for c in context['region_clips']] == ['hero']
    assert context['region_clips'][0]['source_time_sec'] == 3
    assert store.history() == before
    focus(root, store, region=None)
    assert get_editing_context(root)['region'] is None


@pytest.mark.parametrize('values', [{'left': -1}, {'right': 641}, {'bottom': 0}, {'left': 300},
                                   {'playhead_sec': True}, {'canvas_width': float('inf')},
                                   {'top': float('nan')}, {'coordinate_space': 'object'}])
def test_invalid_regions_never_overwrite_focus(project, values):
    root, store = project
    focus(root, store, region=region())
    with pytest.raises(ValueError):
        focus(root, store, region=region(**values))
    assert get_editing_context(root)['region']['left'] == 100
    with pytest.raises(GraphRevisionConflict):
        save_editing_selection(root, expected_revision=0, selected_ids=[], annotation_ids=[],
                              document_id=None, playhead_sec=0, region=None)


def test_unrelated_timeline_growth_does_not_inflate_selected_context(project):
    root, store = project
    small = get_editing_context(root, selected_ids=['hero'])
    store.append_many([AddClipOp(author='user', clip_id=f'unrelated-{i}', asset_hash='c' * 64, track_id='video',
                               position_sec=10 + i, out_point_sec=1) for i in range(500)])
    large = get_editing_context(root, selected_ids=['hero'])
    assert large['timeline']['clip_count'] == 502
    assert large['selected_clips'] == small['selected_clips']
    assert len(json.dumps(large)) - len(json.dumps(small)) < 30
    assert 'tracks' not in large['timeline']
    expanded = get_editing_context(root, selected_ids=['hero'], include_timeline=True)
    assert sum(len(t['clips']) for t in expanded['timeline']['tracks']) == 502


def test_annotations_have_lossless_retrieval_and_pagination(project):
    root, store = project
    changes = [{'kind': 'annotation', 'object_id': f'mark-{i:03}', 'data': {
        'tool': 'freehand', 'points': [[j, j] for j in range(1024)], 'text': 'ر' * 10000,
        'anchor_sec': 2, 'end_sec': 5, 'scope': 'range', 'target_ids': ['hero']}} for i in range(25)]
    commit_studio(root, expected_revision=store.graph_revision(), changes=changes)
    context = get_editing_context(root, selected_ids=['hero'], playhead_sec=2)
    assert len(json.dumps(context, ensure_ascii=False).encode()) < 32 * 1024
    assert len(json.dumps(context).encode()) < 32 * 1024  # MCP wire representation too.
    assert context['context_limits']['collections']['annotations']['total'] == 25
    assert context['context_limits']['collections']['annotations']['next_offset'] is not None
    assert context['context_limits']['omitted_fields']
    assert context['annotations'][0]['data']['points_count'] == 1024
    assert context['annotations'][0]['data']['bounds']['right'] == 1023
    assert len(context['annotations'][0]['data']['text']) == 1000
    complete = get_studio(root, kind='annotation', object_id='mark-000', include_source=True)['objects'][0]
    assert len(complete['data']['text']) == 10000 and len(complete['data']['points']) == 1024
    expanded = get_editing_context(root, selected_ids=['hero'], annotation_ids=['mark-000'], include_source=True)
    assert expanded['annotations'][0] == complete
    seen = []
    while True:
        seen.extend(o['object_id'] for o in context['annotations'])
        offset = context['context_limits']['collections']['annotations']['next_offset']
        if offset is None:
            break
        context = get_editing_context(root, selected_ids=['hero'], playhead_sec=2, offset=offset)
    assert seen == [c['object_id'] for c in changes]
    page = get_editing_context(root, selected_ids=['hero'], playhead_sec=2, section='annotations', offset=24)
    assert [o['object_id'] for o in page['annotations']] == ['mark-024']
    assert 'documents' not in page and page['context_limits']['collections']['annotations']['next_offset'] is None
    with pytest.raises(ValueError):
        get_editing_context(root, section='wrong')
    # Future instructions and marks for another clip do not leak into an implicit focus.
    assert not get_editing_context(root, selected_ids=['sound'], playhead_sec=2)['annotations']
    assert not get_editing_context(root, selected_ids=['hero'], playhead_sec=8)['annotations']
    assert get_editing_context(root, selected_ids=['sound'], annotation_ids=['mark-000'], playhead_sec=8)['annotations']


def test_context_uses_one_snapshot_during_a_concurrent_edit(project, monkeypatch):
    from open_edit.storage import studio as storage

    root, store = project
    revision = store.graph_revision()
    original = storage.snapshot
    def read_then_write(conn):
        objects = original(conn)
        monkeypatch.setattr(storage, 'snapshot', original)
        store.append(AddClipOp(author='ai', clip_id='concurrent', asset_hash='c' * 64,
                               track_id='video', position_sec=10, out_point_sec=1))
        return objects
    monkeypatch.setattr(storage, 'snapshot', read_then_write)
    context = get_editing_context(root, selected_ids=['hero'])
    assert context['graph_revision'] == revision and context['timeline']['clip_count'] == 2
    assert store.graph_revision() == revision + 1


@pytest.mark.asyncio
async def test_http_and_mcp_share_region_and_reject_bad_bounds(project, monkeypatch):
    root, store = project
    async def require(_):
        return SimpleNamespace(path=str(root))
    monkeypatch.setattr(routes, '_require_project', require)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as client:
        revision = store.graph_revision()
        body = {'expected_revision': revision, 'region': region(), 'playhead_sec': 4}
        response = await client.post('/api/projects/p/studio/selection', json=body)
        assert response.status_code == 200
        external = dispatch_query('get_editing_context', {}, root)
        response = await client.post('/api/projects/p/editing-context', json={k: v for k, v in body.items() if k != 'expected_revision'})
        assert response.status_code == 200 and response.json() == external
        response = await client.post('/api/projects/p/studio/selection', json={**body, 'region': region(right=700)})
        assert response.status_code == 422
        assert store.graph_revision() == revision


def test_small_graphics_edits_keep_source_ids_comments_locks_and_undo(tmp_path):
    from open_edit.integrations.diffusion.graphics import DEFAULT_SOURCE, graphics_ready

    if not graphics_ready():
        pytest.skip('Graphics compiler not installed')
    store = EditGraphStore(tmp_path / '.open_edit/edit_graph.db')
    source = DEFAULT_SOURCE.replace('return <stage', '// Keep the original direction\n  return <stage')
    commit_studio(tmp_path, expected_revision=0, changes=[{'kind': 'document', 'object_id': 'title-doc',
                  'data': {'source': source, 'clip_id': 'title-clip'}}])
    context = get_editing_context(tmp_path, document_id='title-doc', selected_ids=['title'])
    assert 'source' not in context['documents'][0]['data']
    assert next(e for e in context['documents'][0]['data']['elements'] if e['id'] == 'title')['source_ref'] == 'index.tsx:title'
    for selection in (['title-doc'], ['title-clip']):
        view = get_editing_context(tmp_path, selected_ids=selection)
        assert {e['id'] for e in view['documents'][0]['data']['elements']} >= {'panel', 'title'}
    params = {'expected_revision': 1, 'document_id': 'title-doc', 'request_id': 'small-edit',
              'edits': [{'kind': 'set', 'source': 'index.tsx:title', 'props': {'x': 144}},
                        {'kind': 'text', 'source': 'index.tsx:title', 'text': 'Manually editable <title>'}]}
    result = dispatch_edit('apply_graphics_edits', {**params, 'author': 'user'}, tmp_path)
    assert result['status'] == 'ok' and result['graph_revision'] == 2 and 'source' not in result
    expanded = get_editing_context(tmp_path, document_id='title-doc', include_source=True)
    data = expanded['documents'][0]['data']
    assert 'Keep the original direction' in data['source']
    title = next(e for e in data['elements'] if e['id'] == 'title')
    assert title['x'] == 144 and title['text'] == 'Manually editable <title>'
    assert store.history()['actions'][0]['author'] == 'ai'
    assert dispatch_edit('apply_graphics_edits', params, tmp_path)['status'] == 'error'
    store.history_step('undo', 2)
    assert get_studio(tmp_path, include_source=True)['objects'][0]['data']['source'] == source
    store.history_step('redo', 3)
    locked = get_studio(tmp_path, include_source=True)['objects'][0]['data']
    commit_studio(tmp_path, expected_revision=4, changes=[{'kind': 'document', 'object_id': 'title-doc',
                  'data': {**locked, 'locked_ids': ['title']}}])
    result = dispatch_edit('apply_graphics_edits', {**params, 'expected_revision': 5}, tmp_path)
    # An identical edit is a no-op; an actual edit of a locked layer is rejected.
    assert result['status'] == 'ok' and not result['changed']
    result = dispatch_edit('apply_graphics_edits', {**params, 'expected_revision': 5,
                           'edits': [{'kind': 'set', 'source': 'index.tsx:title', 'props': {'x': 300}}]}, tmp_path)
    assert result['status'] == 'error' and store.graph_revision() == 5


@pytest.mark.asyncio
async def test_real_stdio_agent_reads_region_and_applies_small_graphics_edit(tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    from open_edit.integrations.diffusion.graphics import DEFAULT_SOURCE, graphics_ready

    if not graphics_ready():
        pytest.skip('Graphics compiler not installed')
    store = EditGraphStore(tmp_path / '.open_edit/edit_graph.db')
    commit_studio(tmp_path, expected_revision=0, changes=[{'kind': 'document', 'object_id': 'title-doc',
                  'data': {'source': DEFAULT_SOURCE, 'clip_id': 'title-clip'}}])
    save_editing_selection(tmp_path, expected_revision=1, selected_ids=['title'], annotation_ids=[],
                           document_id='title-doc', playhead_sec=2, region=region())
    params = StdioServerParameters(command=sys.executable, args=['-m', 'open_edit.mcp.server', '--project', str(tmp_path)],
                                   env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1])})
    async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as session:
        initialized = await session.initialize()
        assert 'query_project' in initialized.instructions
        assert len((await session.list_tools()).tools) == 6
        response = await session.call_tool('query_project', {'query': 'get_editing_context', 'params': {}})
        context = json.loads(response.content[0].text)
        assert context['region']['right'] == 300 and 'source' not in context['documents'][0]['data']
        response = await session.call_tool('edit_project', {'operation': 'apply_graphics_edits', 'params': {
            'expected_revision': context['graph_revision'], 'document_id': 'title-doc',
            'request_id': 'stdio-precise-edit', 'edits': [{'kind': 'text', 'source': 'index.tsx:title',
                                                        'text': 'Edited through real MCP'}]}})
        result = json.loads(response.content[0].text)
        assert result['status'] == 'ok' and 'source' not in result
        assert 'Edited through real MCP' in get_studio(tmp_path, include_source=True)['objects'][0]['data']['source']
        assert store.history()['actions'][0]['request_id'] == 'stdio-precise-edit'
