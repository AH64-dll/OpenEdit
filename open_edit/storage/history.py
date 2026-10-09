"""Durable batch Undo/Redo. Called inside the graph's SQLite transactions."""
from __future__ import annotations

import json
import sqlite3
from contextvars import ContextVar
from typing import TYPE_CHECKING

from open_edit.ir.ids import now_iso8601
from open_edit.ir.types import new_id
from open_edit.storage import studio

if TYPE_CHECKING:
    from open_edit.storage.edit_graph import EditGraphStore

# One built-in AI turn may invoke many tools; threads inherit this context.
request_context: ContextVar[str | None] = ContextVar('editing_request', default=None)


def abandon_redo(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE edit_actions SET state = 'abandoned' WHERE state = 'undone'")


def invalidate(conn: sqlite3.Connection) -> None:
    """A legacy status/reorder/delete is a history barrier, never unsafe replay."""
    conn.execute("UPDATE edit_actions SET state = 'abandoned' WHERE state != 'abandoned'")


def record(conn: sqlite3.Connection, ops, label: str | None, before_revision: int, *,
           object_changes: list[dict] | None = None, author: str = 'user', request_id: str | None = None,
           status_changes: dict | None = None, reverted_targets: list[str] | None = None) -> str:
    abandon_redo(conn)
    if not label:
        kinds = {op.kind for op in ops}
        label = (next(iter(kinds)).replace('_', ' ').capitalize() if len(kinds) == 1
                 else 'Edit timeline' if kinds else 'Edit studio')
        if len(ops) > 1:
            label += f' ({len(ops)} changes)'
    author = ops[0].author if ops else author
    previous = conn.execute('SELECT * FROM edit_actions ORDER BY sequence DESC LIMIT 1').fetchone()
    # Merge only contiguous calls. A manual action is an ordering boundary.
    if (request_id and author == 'ai' and previous and previous['request_id'] == request_id
            and previous['author'] == 'ai' and previous['state'] == 'applied'
            and not previous['reverted_by'] and not status_changes and not reverted_targets):
        merged = {(c['kind'], c['object_id']): c for c in json.loads(previous['object_changes'])}
        for c in object_changes or []:
            key = c['kind'], c['object_id']
            merged[key] = {**c, 'before': merged[key]['before'] if key in merged else c['before']}
        operations = json.loads(previous['operations']) | {op.edit_id: op.status for op in ops}
        conn.execute('UPDATE edit_actions SET operations=?, object_changes=?, after_sources=? WHERE action_id=?',
                     (json.dumps(operations), json.dumps(list(merged.values())),
                      json.dumps(_sources(conn, int(conn.execute("SELECT value FROM project_meta WHERE key='graph_revision'").fetchone()[0]))),
                      previous['action_id']))
        return previous['action_id']
    action_id = new_id()
    conn.execute(
        "INSERT INTO edit_actions(action_id, label, author, created_at, state, operations, before_sources, after_sources, object_changes, request_id, status_changes, reverted_targets) "
        "VALUES (?, ?, ?, ?, 'applied', ?, ?, ?, ?, ?, ?, ?)",
        (action_id, label, author, now_iso8601(),
         json.dumps({op.edit_id: op.status for op in ops}),
         json.dumps(_sources(conn, before_revision)),
         json.dumps(_sources(conn, int(conn.execute("SELECT value FROM project_meta WHERE key = 'graph_revision'").fetchone()[0]))),
         json.dumps(object_changes or []), request_id, json.dumps(status_changes or {}), json.dumps(reverted_targets or [])),
    )
    for target in reverted_targets or []:
        updated = conn.execute("UPDATE edit_actions SET reverted_by=? WHERE action_id=? AND state='applied' AND reverted_by IS NULL", (action_id, target))
        if updated.rowcount != 1:
            raise ValueError('This request was already changed; reload history.')
    return action_id


def _sources(conn: sqlite3.Connection, revision: int) -> dict:
    return dict(conn.execute('SELECT format, source FROM authoring_views WHERE graph_revision = ?', (revision,)).fetchall())


def summary(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT action_id, label, author, created_at, state, operations, object_changes, request_id, reverted_by "
        "FROM edit_actions ORDER BY sequence DESC LIMIT 100"
    ).fetchall()
    undo = conn.execute(
        "SELECT action_id, label FROM edit_actions WHERE state = 'applied' AND reverted_by IS NULL ORDER BY sequence DESC LIMIT 1"
    ).fetchone()
    redo = conn.execute(
        "SELECT action_id, label FROM edit_actions WHERE state = 'undone' AND reverted_by IS NULL ORDER BY sequence ASC LIMIT 1"
    ).fetchone()
    return {
        'undo': dict(undo) if undo else None,
        'redo': dict(redo) if redo else None,
        'actions': [{k: row[k] for k in ('action_id', 'label', 'author', 'created_at', 'state', 'request_id', 'reverted_by')}
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
            f"SELECT * FROM edit_actions WHERE state = ? AND reverted_by IS NULL ORDER BY sequence {order} LIMIT 1", (state,)
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
        apply_status_changes(conn, json.loads(row['status_changes']), row['action_id'], direction)
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
        for target in json.loads(row['reverted_targets']):
            expected = row['action_id'] if direction == 'undo' else None
            existing = conn.execute('SELECT reverted_by FROM edit_actions WHERE action_id=?', (target,)).fetchone()
            if existing is None or existing[0] != expected:
                raise ValueError('Selective revert dependencies changed; reload history.')
            conn.execute('UPDATE edit_actions SET reverted_by=? WHERE action_id=?',
                         (None if direction == 'undo' else row['action_id'], target))
        revision = store._check_and_bump_revision(conn, expected_revision)
        studio.apply(conn, object_changes, revision, direction='before' if direction == 'undo' else 'after')
        for format, source in json.loads(row['before_sources' if direction == 'undo' else 'after_sources']).items():
            store._save_authoring_source(conn, (format, source))
        conn.execute('DELETE FROM timeline_snapshots')
        return {'graph_revision': revision, 'changed': True, 'label': row['label'], **summary(conn)}


def apply_status_changes(conn: sqlite3.Connection, changes: dict, action_id: str | None, direction: str = 'redo') -> None:
    for edit_id, delta in changes.items():
        expected, target = (delta['after'], delta['before']) if direction == 'undo' else (delta['before'], delta['after'])
        row = conn.execute('SELECT status FROM edits WHERE edit_id=?', (edit_id,)).fetchone()
        if row is None or row[0] != expected:
            raise ValueError('Request operations changed; reload history.')
        conn.execute('UPDATE edits SET status=? WHERE edit_id=?', (target, edit_id))
        conn.execute('INSERT INTO edit_status_events(event_id,edit_id,from_status,to_status,command_id,reason,changed_at) VALUES (?,?,?,?,?,?,?)',
                     (new_id(), edit_id, expected, target, action_id, 'selective revert ' + direction, now_iso8601()))
