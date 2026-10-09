"""Source documents and marks are durable, atomic and share operation history."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from open_edit.ir.types import AddClipOp, MoveClipOp
from open_edit.ir.validate import OpValidationError
from open_edit.storage.edit_graph import EditGraphStore, GraphRevisionConflict


def change(id='title', data=None, kind='document'):
    return {'kind': kind, 'object_id': id, 'data': data}


def test_documents_and_annotations_share_atomic_history_after_reopen(tmp_path):
    store = EditGraphStore(tmp_path / 'graph.db')
    source = {'source': '// preserve me\n<text id="title">Hello</text>', 'format': 'graphics'}
    arrow = {'tool': 'arrow', 'points': [[1, 2], [20, 30]], 'target_ids': ['title']}
    store.append_many([], studio_changes=[change(data=source), change('arrow', arrow, 'annotation')],
                      author='ai', request_id='request-1', action_label='Create title and guidance')
    before = store.studio_snapshot()
    assert before['graph_revision'] == 1
    assert store.history()['actions'][0]['request_id'] == 'request-1'
    assert store.history()['actions'][0]['object_count'] == 2
    store = EditGraphStore(store.db_path)
    store.history_step('undo', 1)
    assert store.studio_snapshot() == {'graph_revision': 2, 'objects': []}
    store.history_step('redo', 2)
    restored = store.studio_snapshot()
    assert [o['data'] for o in restored['objects']] == [o['data'] for o in before['objects']]
    assert all(o['revision'] == 3 for o in restored['objects'])
    with store._conn() as conn:
        assert conn.execute('SELECT COUNT(*) FROM studio_object_versions').fetchone()[0] == 6
    assert store.load_all() == []  # marks never become render operations


def test_mixed_operation_and_source_batch_rolls_back_then_undoes_together(tmp_path):
    store = EditGraphStore(tmp_path / 'graph.db')
    add = AddClipOp(author='ai', clip_id='video', asset_hash='a' * 64,
                    track_id='V1', position_sec=0, out_point_sec=2)
    bad = MoveClipOp(author='ai', clip_id='missing', new_track_id='V1', new_position_sec=2)
    with pytest.raises(OpValidationError):
        store.append_many([add, bad], studio_changes=[change(data={'source': 'draft'})])
    assert store.studio_snapshot()['objects'] == []
    assert store.graph_revision() == 0 and not store.history()['actions']
    store.append_many([add], studio_changes=[change(data={'source': 'accepted'})])
    assert store.graph_revision() == 1
    store.history_step('undo', 1)
    assert store.load_all()[0].status == 'reverted'
    assert not store.studio_snapshot()['objects']
    store.history_step('redo', 2)
    assert store.load_all()[0].status == 'applied'
    assert store.studio_snapshot()['objects'][0]['data']['source'] == 'accepted'


def test_noop_preserves_redo_and_delete_has_recoverable_versions(tmp_path):
    store = EditGraphStore(tmp_path / 'graph.db')
    store.append_many([], studio_changes=[change(data={'source': 'original'})])
    store.append_many([], studio_changes=[change(data={'source': 'changed'})])
    store.history_step('undo', 2)
    before = store.history()
    store.append_many([], studio_changes=[change(data={'source': 'original'})])
    assert store.history() == before
    store.append_many([], studio_changes=[change(data=None)])
    assert store.history()['redo'] is None
    assert not store.studio_snapshot()['objects']
    store.history_step('undo', store.graph_revision())
    assert store.studio_snapshot()['objects'][0]['data']['source'] == 'original'


def test_concurrent_source_writers_have_exactly_one_winner(tmp_path):
    store = EditGraphStore(tmp_path / 'graph.db')
    store.append_many([], studio_changes=[change(data={'source': 'before'})])
    def write(value):
        try:
            EditGraphStore(store.db_path).append_many([], expected_revision=1,
                studio_changes=[change(data={'source': value})])
            return 'saved'
        except GraphRevisionConflict:
            return 'stale'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(write, ['a', 'b'])) == ['saved', 'stale']
    assert store.graph_revision() == 2


def test_explicit_lock_blocks_user_and_ai_and_undo_can_restore_it(tmp_path):
    store = EditGraphStore(tmp_path / 'graph.db')
    locked = {'source': 'before', 'locked': True}
    store.append_many([], studio_changes=[change(data=locked)])
    for author in ('user', 'ai'):
        for data in (None, {'source': 'after', 'locked': True}, {'source': 'after', 'locked': False}):
            with pytest.raises(ValueError, match='locked'):
                store.append_many([], author=author, studio_changes=[change(data=data)])
    store.append_many([], studio_changes=[change(data={**locked, 'locked': False})])
    store.append_many([], studio_changes=[change(data={'source': 'after', 'locked': False})])
    store.history_step('undo', store.graph_revision())
    store.history_step('undo', store.graph_revision())
    assert store.studio_snapshot()['objects'][0]['data'] == locked


@pytest.mark.parametrize('changes', [
    [{'kind': 'document', 'object_id': '../escape', 'data': {}}],
    [change(data={'x': float('nan')})], [change(data={'x': float('inf')})],
    [change(data={}), change(data={})], [{'kind': 'unknown', 'object_id': 'x', 'data': {}}],
])
def test_invalid_objects_leave_no_revision_or_action(tmp_path, changes):
    store = EditGraphStore(tmp_path / 'graph.db')
    with pytest.raises(ValueError):
        store.append_many([], studio_changes=changes)
    assert store.graph_revision() == 0 and not store.history()['actions']
