"""Durable batch Undo/Redo. Called inside the graph's SQLite transactions."""
from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING

from open_edit.ir.ids import now_iso8601
from open_edit.ir.types import new_id
from open_edit.storage import studio

if TYPE_CHECKING:
    from open_edit.storage.edit_graph import EditGraphStore


def abandon_redo(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE edit_actions SET state = 'abandoned' WHERE state = 'undone'")


def invalidate(conn: sqlite3.Connection) -> None:
    """A legacy status/reorder/delete is a history barrier, never unsafe replay."""
    conn.execute("UPDATE edit_actions SET state = 'abandoned' WHERE state != 'abandoned'")


def record(conn: sqlite3.Connection, ops, label: str | None, before_revision: int, *,
           object_changes: list[dict] | None = None, author: str = 'user', request_id: str | None = None) -> None:
    abandon_redo(conn)
    if not label:
        kinds = {op.kind for op in ops}
        label = (next(iter(kinds)).replace('_', ' ').capitalize() if len(kinds) == 1
                 else 'Edit timeline' if kinds else 'Edit studio')
        if len(ops) > 1:
            label += f' ({len(ops)} changes)'
    conn.execute(
        "INSERT INTO edit_actions(action_id, label, author, created_at, state, operations, before_sources, after_sources, object_changes, request_id) "
        "VALUES (?, ?, ?, ?, 'applied', ?, ?, ?, ?, ?)",
        (new_id(), label, ops[0].author if ops else author, now_iso8601(),
         json.dumps({op.edit_id: op.status for op in ops}),
         json.dumps(_sources(conn, before_revision)),
         json.dumps(_sources(conn, int(conn.execute("SELECT value FROM project_meta WHERE key = 'graph_revision'").fetchone()[0]))),
         json.dumps(object_changes or []), request_id),
    )


def _sources(conn: sqlite3.Connection, revision: int) -> dict:
    return dict(conn.execute('SELECT format, source FROM authoring_views WHERE graph_revision = ?', (revision,)).fetchall())


def summary(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT action_id, label, author, created_at, state, operations, object_changes, request_id "
        "FROM edit_actions ORDER BY sequence DESC LIMIT 100"
    ).fetchall()
    undo = conn.execute(
        "SELECT action_id, label FROM edit_actions WHERE state = 'applied' ORDER BY sequence DESC LIMIT 1"
    ).fetchone()
    redo = conn.execute(
        "SELECT action_id, label FROM edit_actions WHERE state = 'undone' ORDER BY sequence ASC LIMIT 1"
    ).fetchone()
    return {
        'undo': dict(undo) if undo else None,
        'redo': dict(redo) if redo else None,
        'actions': [{k: row[k] for k in ('action_id', 'label', 'author', 'created_at', 'state', 'request_id')}
                    | {'operation_count': len(json.loads(row['operations'])),
                       'object_count': len(json.loads(row['object_changes']))} for row in rows],
    }


def step(store: EditGraphStore, direction: str, expected_revision: int) -> dict:
    if direction not in ('undo', 'redo'):
        raise ValueError('history action must be undo or redo')
    from open_edit.storage.edit_graph import GraphRevisionConflict

    with store._conn() as conn:
        conn.execute('BEGIN IMMEDIATE')
        current = store._revision_in(conn)
        if current != expected_revision:
            raise GraphRevisionConflict(expected_revision, current)
        state, order = ('applied', 'DESC') if direction == 'undo' else ('undone', 'ASC')
        row = conn.execute(
            f"SELECT * FROM edit_actions WHERE state = ? ORDER BY sequence {order} LIMIT 1", (state,)
        ).fetchone()
        if row is None:
            return {'graph_revision': current, 'changed': False, **summary(conn)}
        statuses = json.loads(row['operations'])
        object_changes = json.loads(row['object_changes'])
        current_objects = {(obj['kind'], obj['object_id']): obj['data'] for obj in studio.snapshot(conn)}
        for change in object_changes:
            expected_data = change['after' if direction == 'undo' else 'before']
            if current_objects.get((change['kind'], change['object_id'])) != expected_data:
                raise ValueError('An object in this action was changed; reload history.')
        if direction == 'undo':
            latest_sources = _sources(conn, current)
            if latest_sources:
                conn.execute('UPDATE edit_actions SET after_sources = ? WHERE action_id = ?',
                             (json.dumps(latest_sources), row['action_id']))
        changed_at = now_iso8601()
        for edit_id, original in statuses.items():
            existing = conn.execute('SELECT status FROM edits WHERE edit_id = ?', (edit_id,)).fetchone()
            expected = original if direction == 'undo' else 'reverted'
            if existing is None or existing['status'] != expected:
                raise ValueError('This action was changed by another editor; reload history.')
            target = 'reverted' if direction == 'undo' else original
            conn.execute('UPDATE edits SET status = ? WHERE edit_id = ?', (target, edit_id))
            conn.execute(
                'INSERT INTO edit_status_events '
                '(event_id, edit_id, from_status, to_status, command_id, reason, changed_at) '
                'VALUES (?, ?, ?, ?, ?, ?, ?)',
                (new_id(), edit_id, expected, target, row['action_id'], direction, changed_at),
            )
        conn.execute('UPDATE edit_actions SET state = ? WHERE action_id = ?',
                     ('undone' if direction == 'undo' else 'applied', row['action_id']))
        revision = store._check_and_bump_revision(conn, expected_revision)
        studio.apply(conn, object_changes, revision, direction='before' if direction == 'undo' else 'after')
        for format, source in json.loads(row['before_sources' if direction == 'undo' else 'after_sources']).items():
            store._save_authoring_source(conn, (format, source))
        conn.execute('DELETE FROM timeline_snapshots')
        return {'graph_revision': revision, 'changed': True, 'label': row['label'], **summary(conn)}
