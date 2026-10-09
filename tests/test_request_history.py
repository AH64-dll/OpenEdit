"""An AI request can be inverted without discarding unrelated later work."""
from types import SimpleNamespace

import httpx
import pytest

from open_edit.integrations.diffusion.graphics import DEFAULT_SOURCE, graphics_ready, inspect_source
from open_edit.ir.derive import derive_timeline
from open_edit.ir.types import AddClipOp, MoveClipOp, Project
from open_edit.kernel.request_history import revert_request
from open_edit.kernel.studio_service import commit_studio, get_studio
from open_edit.storage.edit_graph import EditGraphStore, GraphRevisionConflict


@pytest.fixture
def project(tmp_path):
    return tmp_path, EditGraphStore(tmp_path / '.open_edit/edit_graph.db')


def annotation(text='Before', color='#ffcc55'):
    return {'kind': 'annotation', 'object_id': 'note', 'data': {'tool': 'note', 'points': [[10, 20]], 'text': text, 'color': color}}


def save(root, store, change, **kwargs):
    return commit_studio(root, expected_revision=store.graph_revision(), changes=[change], **kwargs)


def test_request_group_and_selective_inverse_survive_reopen(project):
    root, store = project
    save(root, store, annotation())
    save(root, store, annotation('AI first'), author='ai', request_id='turn')
    save(root, store, annotation('AI final'), author='ai', request_id='turn')
    assert len(store.history()['actions']) == 2
    assert store.history()['actions'][0]['object_count'] == 1
    save(root, store, annotation('AI final', '#112233'))
    revision = store.graph_revision()
    preview = revert_request(root, request_id='turn', expected_revision=revision, preview=True)
    assert preview['can_revert'] and not preview['changed'] and store.graph_revision() == revision
    reverted = revert_request(root, request_id='turn', expected_revision=revision)
    assert reverted['changed']
    obj = store.studio_snapshot()['objects'][0]['data']
    assert obj['text'] == 'Before' and obj['color'] == '#112233'
    store = EditGraphStore(store.db_path)
    assert next(a for a in store.history()['actions'] if a['request_id'] == 'turn')['reverted_by']
    store.history_step('undo', store.graph_revision())
    assert store.studio_snapshot()['objects'][0]['data']['text'] == 'AI final'
    store.history_step('redo', store.graph_revision())
    assert store.studio_snapshot()['objects'][0]['data']['text'] == 'Before'
    assert store.studio_snapshot()['objects'][0]['data']['color'] == '#112233'
    with pytest.raises(ValueError, match='No applied AI'):
        revert_request(root, request_id='turn', expected_revision=store.graph_revision())


def test_conflict_is_explicit_and_changes_nothing(project):
    root, store = project
    save(root, store, annotation())
    save(root, store, annotation('AI'), author='ai', request_id='turn')
    save(root, store, annotation('Later manual text'))
    before = store.studio_snapshot(), store.history()
    result = revert_request(root, request_id='turn', expected_revision=store.graph_revision())
    assert not result['can_revert'] and result['conflicts'][0]['field'] == 'note.text'
    assert (store.studio_snapshot(), store.history()) == before
    with pytest.raises(GraphRevisionConflict):
        revert_request(root, request_id='turn', expected_revision=0)


def test_reverting_ai_move_preserves_later_independent_clip(project):
    root, store = project
    store.append(AddClipOp(author='user', clip_id='a', asset_hash='a' * 64, track_id='V1', position_sec=0, in_point_sec=0, out_point_sec=1))
    store.append_many([MoveClipOp(author='ai', clip_id='a', new_track_id='V1', new_position_sec=3)], request_id='move')
    store.append(AddClipOp(author='user', clip_id='b', asset_hash='b' * 64, track_id='V1', position_sec=5, in_point_sec=0, out_point_sec=1))
    result = revert_request(root, request_id='move', expected_revision=store.graph_revision())
    assert result['changed']
    timeline = derive_timeline(Project(name='p', edit_graph=store.load_all()), strict=True)
    assert [(c.clip_id, c.position_sec) for c in timeline.tracks[0].clips] == [('a', 0), ('b', 5)]
    store.history_step('undo', store.graph_revision())
    timeline = derive_timeline(Project(name='p', edit_graph=store.load_all()), strict=True)
    assert timeline.tracks[0].clips[0].position_sec == 3


def test_dependent_clip_creation_blocks_inverse(project):
    root, store = project
    store.append_many([AddClipOp(author='ai', clip_id='a', asset_hash='a' * 64, track_id='V1', position_sec=0, in_point_sec=0, out_point_sec=1)], request_id='create')
    store.append(MoveClipOp(author='user', clip_id='a', new_track_id='V1', new_position_sec=3))
    revision = store.graph_revision()
    result = revert_request(root, request_id='create', expected_revision=revision)
    assert result['conflicts'] and not result['changed'] and store.graph_revision() == revision


def test_locked_media_clip_blocks_selective_revert(project):
    root, store = project
    store.append(AddClipOp(author='user', clip_id='a', asset_hash='a' * 64, track_id='V1', position_sec=0, in_point_sec=0, out_point_sec=1))
    store.append_many([MoveClipOp(author='ai', clip_id='a', new_track_id='V1', new_position_sec=3)], request_id='move')
    save(root, store, {'kind': 'clip', 'object_id': 'a', 'data': {'locked': True}})
    revision = store.graph_revision()
    result = revert_request(root, request_id='move', expected_revision=revision, preview=True)
    assert not result['can_revert'] and 'Unlock' in result['conflicts'][0]['reason']
    result = revert_request(root, request_id='move', expected_revision=revision)
    assert not result['changed'] and store.graph_revision() == revision


@pytest.mark.skipif(not graphics_ready(), reason='Optional graphics compiler is not installed')
def test_source_inverse_preserves_other_property_and_comments(project):
    root, store = project
    def doc(source):
        return {'kind': 'document', 'object_id': 'document', 'data': {'source': source, 'clip_id': 'graphics'}}
    save(root, store, doc(DEFAULT_SOURCE))
    after = DEFAULT_SOURCE.replace('Your title', 'AI text')
    save(root, store, doc(after), author='ai', request_id='source')
    current = '// Keep my later comment\n' + after.replace('fontSize={48}', 'fontSize={64}')
    save(root, store, doc(current))
    result = revert_request(root, request_id='source', expected_revision=store.graph_revision())
    assert result['changed'] and result['can_revert']
    document = get_studio(root, include_source=True)['objects'][0]['data']
    title = next(e for e in document['elements'] if e['id'] == 'title')
    assert title['text'] == 'Your title' and title['fontSize'] == 64
    assert 'Keep my later comment' in document['source']
    store.history_step('undo', store.graph_revision())
    assert 'AI text' in get_studio(root, include_source=True)['objects'][0]['data']['source']


@pytest.mark.skipif(not graphics_ready(), reason='Optional graphics compiler is not installed')
def test_source_same_property_conflict_and_layer_locks(project):
    root, store = project
    def doc(source, locks=None):
        return {'kind': 'document', 'object_id': 'document', 'data': {'source': source, 'clip_id': 'graphics', 'locked_ids': locks or []}}
    save(root, store, doc(DEFAULT_SOURCE))
    save(root, store, doc(DEFAULT_SOURCE.replace('Your title', 'AI text')), author='ai', request_id='source')
    save(root, store, doc(DEFAULT_SOURCE.replace('Your title', 'Manual text')))
    result = revert_request(root, request_id='source', expected_revision=store.graph_revision())
    assert not result['can_revert'] and result['conflicts'][0]['field'] == 'text'
    save(root, store, doc(DEFAULT_SOURCE.replace('Your title', 'AI text'), ['title']))
    result = revert_request(root, request_id='source', expected_revision=store.graph_revision())
    assert not result['can_revert'] and 'unlock' in result['conflicts'][0]['reason'].lower()
    assert inspect_source(DEFAULT_SOURCE)['scene']['width'] == 960


@pytest.mark.skipif(not graphics_ready(), reason='Optional graphics compiler is not installed')
def test_later_linked_mark_blocks_removal_of_ai_composition(project):
    root, store = project
    save(root, store, {'kind': 'document', 'object_id': 'doc', 'data': {'source': DEFAULT_SOURCE, 'clip_id': 'graphics'}}, author='ai', request_id='create')
    save(root, store, {'kind': 'annotation', 'object_id': 'mark', 'data': {'tool': 'note', 'points': [[10, 20]], 'document_id': 'doc', 'target_ids': ['title']}})
    result = revert_request(root, request_id='create', expected_revision=store.graph_revision())
    assert not result['changed'] and result['conflicts'][0]['field'] == 'mark'


def test_noncontiguous_request_preserves_manual_history_boundary(project):
    root, store = project
    save(root, store, annotation())
    save(root, store, annotation('First AI'), author='ai', request_id='turn')
    save(root, store, annotation('First AI', '#112233'))
    save(root, store, annotation('Final AI', '#112233'), author='ai', request_id='turn')
    assert len(store.history()['actions']) == 4
    result = revert_request(root, request_id='turn', expected_revision=store.graph_revision())
    assert result['changed'] and not result['conflicts']
    assert store.studio_snapshot()['objects'][0]['data']['text'] == 'Before'
    assert store.studio_snapshot()['objects'][0]['data']['color'] == '#112233'
    store.history_step('undo', store.graph_revision())
    assert store.studio_snapshot()['objects'][0]['data']['text'] == 'Final AI'


@pytest.mark.asyncio
async def test_http_selective_revert_preview_and_stale_revision(project, monkeypatch):
    from open_edit.serve.app import app
    from open_edit.serve.routers import ops

    root, store = project
    save(root, store, annotation())
    save(root, store, annotation('AI text'), author='ai', request_id='request')
    async def require(_):
        return SimpleNamespace(path=str(root))
    monkeypatch.setattr(ops, '_require_project', require)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as client:
        endpoint = '/api/projects/p/history/revert-request'
        preview = await client.post(endpoint, json={'request_id': 'request', 'expected_revision': 2, 'preview': True})
        assert preview.status_code == 200 and preview.json()['can_revert'] and store.graph_revision() == 2
        stale = await client.post(endpoint, json={'request_id': 'request', 'expected_revision': 1})
        assert stale.status_code == 409
        invalid = await client.post(endpoint, json={'request_id': 'request', 'expected_revision': True})
        assert invalid.status_code == 422
        changed = await client.post(endpoint, json={'request_id': 'request', 'expected_revision': 2})
        assert changed.status_code == 200 and changed.json()['changed']
        assert store.studio_snapshot()['objects'][0]['data']['text'] == 'Before'
