"""HTTP/MCP share source and annotation writes with guarded action ownership."""
from types import SimpleNamespace

import httpx
import pytest

from open_edit.kernel.pillar_tools import dispatch_edit, dispatch_query
from open_edit.kernel.studio_service import (
    commit_studio,
    get_editing_context,
    save_editing_selection,
)
from open_edit.serve.app import app
from open_edit.serve.routers import studio as routes
from open_edit.storage.edit_graph import EditGraphStore


@pytest.fixture
def project(tmp_path):
    store = EditGraphStore(tmp_path / '.open_edit/edit_graph.db')
    return tmp_path, store


def mark(**overrides):
    return {'kind': 'annotation', 'object_id': 'arrow', 'data': {
        'tool': 'arrow', 'points': [[10, 20], [30, 40]], 'text': 'Move title here', **overrides}}


def test_annotations_context_is_structured_and_never_a_render_op(project):
    root, store = project
    result = commit_studio(root, expected_revision=0, changes=[mark()], label='Explain placement')
    assert result['changed'] and result['graph_revision'] == 1
    context = get_editing_context(root, selected_ids=['title'], annotation_ids=['arrow'], playhead_sec=2)
    assert context['annotations'][0]['data']['text'] == 'Move title here'
    assert context['annotations'][0]['data']['points'] == [[10, 20], [30, 40]]
    assert context['selected_ids'] == ['title'] and context['playhead_sec'] == 2
    assert not store.load_all()
    store.history_step('undo', 1)
    assert not get_editing_context(root)['annotations']


def test_external_agents_read_workspace_selection_without_an_edit_step(project):
    root, store = project
    commit_studio(root, expected_revision=0, changes=[mark()])
    saved = save_editing_selection(root, expected_revision=1, selected_ids=['title'],
                                  annotation_ids=['arrow'], document_id=None, playhead_sec=1.5)
    assert saved['graph_revision'] == 1
    context = dispatch_query('get_editing_context', {}, root)
    assert context['selected_ids'] == ['title'] and context['playhead_sec'] == 1.5
    assert context['annotations'][0]['object_id'] == 'arrow'
    assert store.graph_revision() == 1 and len(store.history()['actions']) == 1
    EditGraphStore(store.db_path)
    assert get_editing_context(root)['selected_ids'] == ['title']


def test_external_mcp_batch_is_identified_as_ai(project):
    root, store = project
    result = dispatch_edit('apply_studio_changes', {'expected_revision': 0, 'changes': [mark()],
                           'author': 'user', 'request_id': 'external-turn-1'}, root)
    assert result['status'] == 'ok'
    action = dispatch_query('get_history', {}, root)['actions'][0]
    assert action['author'] == 'ai' and action['request_id'] == 'external-turn-1'
    assert dispatch_query('get_studio', {'kind': 'annotation'}, root)['objects'][0]['object_id'] == 'arrow'
    assert dispatch_query('get_editing_context', {'selected_ids': ['title']}, root)['selected_ids'] == ['title']
    bad = dispatch_edit('apply_studio_changes', {'expected_revision': 0, 'changes': []}, root)
    assert bad['status'] == 'error'
    assert store.graph_revision() == 1


@pytest.mark.parametrize('values', [
    {'points': [[0, 1]]}, {'scope': 'object'}, {'scope': 'range'},
    {'anchor_sec': 3, 'end_sec': 2}, {'target_ids': ['a' * 129]},
    {'tool': 'script'}, {'locked': 'false'}, {'unexpected': 1},
])
def test_invalid_annotations_do_not_mutate(project, values):
    root, store = project
    with pytest.raises(ValueError):
        commit_studio(root, expected_revision=0, changes=[mark(**values)])
    assert store.graph_revision() == 0 and not store.history()['actions']


@pytest.mark.asyncio
async def test_http_read_write_conflict_context_and_history(project, monkeypatch):
    root, store = project
    async def require(_):
        return SimpleNamespace(path=str(root))
    monkeypatch.setattr(routes, '_require_project', require)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as client:
        saved = await client.post('/api/projects/p/studio', json={'expected_revision': 0, 'changes': [mark()]})
        assert saved.status_code == 200 and saved.json()['changed']
        read = await client.get('/api/projects/p/studio?kind=annotation')
        assert read.status_code == 200 and len(read.json()['objects']) == 1
        context = await client.post('/api/projects/p/editing-context', json={'selected_ids': ['title']})
        assert context.status_code == 200 and context.json()['annotations']
        stale = await client.post('/api/projects/p/studio', json={'expected_revision': 0, 'changes': [mark()]})
        assert stale.status_code == 409
        bad = await client.post('/api/projects/p/studio', json={'expected_revision': True, 'changes': [mark()]})
        assert bad.status_code == 422
        # Public UI route cannot attribute its writes to an external agent.
        bad = await client.post('/api/projects/p/studio', json={'expected_revision': 1, 'author': 'ai'})
        assert bad.status_code == 422
        assert store.history()['actions'][0]['author'] == 'user'


@pytest.mark.asyncio
async def test_live_compilation_routes_validate_source_and_share_selection(project, monkeypatch):
    from open_edit.integrations.diffusion.graphics import DEFAULT_SOURCE, graphics_ready

    if not graphics_ready():
        pytest.skip('Optional graphics compiler not installed')
    root, store = project
    async def require(_):
        return SimpleNamespace(path=str(root))
    monkeypatch.setattr(routes, '_require_project', require)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as client:
        compiled = await client.post('/api/projects/p/studio/compile', json={
            'expected_revision': 0, 'source': DEFAULT_SOURCE,
            'edits': [{'kind': 'text', 'source': 'index.tsx:title', 'text': 'Editable <title> & {text}'}]})
        assert compiled.status_code == 200 and compiled.json()['elements'][-1]['text'] == 'Editable <title> & {text}'
        assert 'code' in compiled.json() and store.graph_revision() == 0
        invalid = await client.post('/api/projects/p/studio/compile', json={
            'expected_revision': 0, 'source': 'export default function(){ return window.fetch("https://example.com"); }'})
        assert invalid.status_code == 400
        runtime = await client.get('/api/studio/runtime.js')
        assert runtime.status_code == 200 and 'OpenEditCanvas' in runtime.text
        assert (await client.get('/api/studio/font.woff2')).status_code == 200
        assert (await client.get('/api/projects/p/studio/assets/not-a-hash')).status_code == 404
        selected = await client.post('/api/projects/p/studio/selection', json={
            'expected_revision': 0, 'selected_ids': ['title'], 'playhead_sec': 1.0})
        assert selected.status_code == 200 and store.graph_revision() == 0
        assert dispatch_query('get_editing_context', {}, root)['selected_ids'] == ['title']
