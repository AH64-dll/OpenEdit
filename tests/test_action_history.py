"""Whole edits undo atomically, survive reopen, and reject stale writers."""
from types import SimpleNamespace

import httpx
import pytest

from open_edit.ir.types import AddClipOp, MoveClipOp
from open_edit.ir.validate import OpValidationError
from open_edit.serve.app import app
from open_edit.serve.routers import ops as routes
from open_edit.storage.edit_graph import EditGraphStore, GraphRevisionConflict


def clip(id, position=0):
    return AddClipOp(clip_id=id, author='user', asset_hash='a' * 64,
                     track_id='V1', position_sec=position, in_point_sec=0, out_point_sec=1)


def test_batch_undo_redo_and_branch_after_reopen(tmp_path):
    db = tmp_path / 'edit_graph.db'
    store = EditGraphStore(db)
    first, second = clip('first'), clip('second', 1)
    store.append_many([first, second], action_label='Import two clips')
    revision = store.graph_revision()
    assert store.history()['undo']['label'] == 'Import two clips'
    result = store.history_step('undo', revision)
    assert result['graph_revision'] == revision + 1
    assert [o.status for o in store.load_all()] == ['reverted', 'reverted']
    store = EditGraphStore(db)
    with pytest.raises(GraphRevisionConflict):
        store.history_step('redo', revision)
    assert store.history()['redo']
    result = store.history_step('redo', result['graph_revision'])
    assert [o.status for o in store.load_all()] == ['applied', 'applied']
    move = MoveClipOp(author='ai', clip_id='first', new_position_sec=3, new_track_id='V1')
    store.append_many([move])
    store.history_step('undo', store.graph_revision())
    store.history_step('undo', store.graph_revision())
    # Redo restores earlier batches before their dependent moves.
    store.history_step('redo', store.graph_revision())
    assert [o.status for o in store.load_all()] == ['applied', 'applied', 'reverted']
    store.append(clip('third', 4))
    assert store.history()['redo'] is None
    assert store.history()['actions'][-1]['operation_count'] == 2


def test_failed_batch_and_format_only_save_preserve_redo(tmp_path):
    store = EditGraphStore(tmp_path / 'edit_graph.db')
    store.append(clip('first'))
    store.history_step('undo', store.graph_revision())
    before = store.history()
    with pytest.raises(OpValidationError):
        store.append_many([clip('second'), MoveClipOp(author='user', clip_id='missing', new_position_sec=0, new_track_id='V1')])
    assert store.history() == before
    store.append_many([], expected_revision=store.graph_revision(), authoring_view=('test', '// draft'))
    assert store.history() == before


def test_legacy_status_changes_create_safe_history_barrier(tmp_path):
    store = EditGraphStore(tmp_path / 'edit_graph.db')
    op = clip('first')
    store.append(op)
    store.update_status(op.edit_id, 'reverted')
    assert store.history()['undo'] is None and store.history()['redo'] is None
    before = store.graph_revision()
    assert store.history_step('undo', before)['changed'] is False
    with pytest.raises(GraphRevisionConflict):
        store.history_step('undo', before - 1)


@pytest.mark.asyncio
async def test_http_group_history_is_revision_checked(tmp_path, monkeypatch):
    store = EditGraphStore(tmp_path / '.open_edit/edit_graph.db')
    store.append_many([clip('a'), clip('b', 1)])
    async def require(_):
        return SimpleNamespace(path=str(tmp_path))
    monkeypatch.setattr(routes, '_require_project', require)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as client:
        history = (await client.get('/api/projects/p/history')).json()
        assert history['actions'][0]['operation_count'] == 2
        response = await client.post('/api/projects/p/history/undo', json={'expected_revision': history['graph_revision']})
        assert response.status_code == 200
        assert all(op.status == 'reverted' for op in store.load_all())
        stale = await client.post('/api/projects/p/history/redo', json={'expected_revision': history['graph_revision']})
        assert stale.status_code == 409
        assert (await client.post('/api/projects/p/history/redo', json={})).status_code == 422


def test_source_comments_restore_with_whole_action(tmp_path):
    store = EditGraphStore(tmp_path / 'edit_graph.db')
    store.append(clip('first'))
    store.append_many([], authoring_view=('diffusion', '// Before\n<video start={0}/>'))
    move = MoveClipOp(author='user', clip_id='first', new_position_sec=3, new_track_id='V1')
    store.append_many([move], authoring_view=('diffusion', '// After\n<video start={3}/>'))
    # A later formatting save belongs to the same timeline state.
    store.append_many([], authoring_view=('diffusion', '// Keep this comment\n<video start={3}/>'))
    undone = store.history_step('undo', store.graph_revision())
    assert store.load_authoring_source('diffusion', undone['graph_revision']) == '// Before\n<video start={0}/>'
    redone = store.history_step('redo', undone['graph_revision'])
    assert store.load_authoring_source('diffusion', redone['graph_revision']) == '// Keep this comment\n<video start={3}/>'


def test_concurrent_undo_cannot_revert_two_actions(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    db = tmp_path / 'edit_graph.db'
    store = EditGraphStore(db)
    store.append(clip('first'))
    store.append(clip('second', 1))
    revision = store.graph_revision()
    def undo(_):
        try:
            return EditGraphStore(db).history_step('undo', revision)['changed']
        except GraphRevisionConflict:
            return 'stale'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(undo, range(2)))
    assert results.count(True) == results.count('stale') == 1
    assert [op.status for op in store.load_all()] == ['applied', 'reverted']


def test_upgrade_legacy_project_preserves_statuses_and_has_no_fake_redo(tmp_path):
    import sqlite3

    from open_edit.storage import migrations

    db = tmp_path / 'edit_graph.db'
    with sqlite3.connect(db) as conn:
        for version in range(1, 7):
            conn.executescript(migrations._migration_files()[version].read_text())
        for index, status in enumerate(('applied', 'reverted', 'superseded')):
            op = clip(str(index)).model_copy(update={'status': status})
            conn.execute('INSERT INTO edits VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                         (op.edit_id, None, op.kind, op.author, op.timestamp, status, index, op.model_dump_json()))
        conn.execute('PRAGMA user_version = 6')
    store = EditGraphStore(db)
    assert [op.status for op in store.load_all()] == ['applied', 'reverted', 'superseded']
    history = store.history()
    assert len(history['actions']) == 3
    assert history['undo'] and history['redo'] is None
    assert len(EditGraphStore(db).history()['actions']) == 3


def test_mcp_and_cli_share_one_history(tmp_path, monkeypatch, capsys):
    from open_edit.cli import main
    from open_edit.kernel.pillar_tools import dispatch_edit, dispatch_query

    store = EditGraphStore(tmp_path / '.open_edit/edit_graph.db')
    store.append_many([clip('a'), clip('b', 1)])
    history = dispatch_query('get_history', {}, tmp_path)
    assert history['status'] == 'ok'
    assert dispatch_edit('undo', {'expected_revision': True}, tmp_path)['status'] == 'error'
    assert dispatch_edit('undo', {'expected_revision': history['graph_revision']}, tmp_path)['changed']
    assert dispatch_edit('redo', {'expected_revision': history['graph_revision']}, tmp_path)['status'] == 'error'
    monkeypatch.chdir(tmp_path)
    assert main(['redo']) == 0
    assert 'Redo:' in capsys.readouterr().out
    assert all(op.status == 'applied' for op in store.load_all())
