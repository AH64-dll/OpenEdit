"""Revision-owned editor objects. Transactions and history belong to the graph.

Rendered assets are caches, not the only surviving representation of an edit.
Annotation objects live here too and never enter the render operation graph.
"""
from __future__ import annotations

import json
import re
import sqlite3
from copy import deepcopy

KINDS = frozenset({'document', 'annotation', 'caption', 'project', 'track', 'clip', 'font', 'style'})
_ID = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$')
MAX_OBJECT_BYTES = 2 * 1024 * 1024
MAX_CHANGES = 1000


def validate_changes(changes: list[dict]) -> list[dict]:
    if not isinstance(changes, list) or len(changes) > MAX_CHANGES:
        raise ValueError('Object changes must be a list with at most 1000 entries')
    seen = set()
    result = []
    total = 0
    for change in changes:
        if not isinstance(change, dict) or set(change) != {'kind', 'object_id', 'data'}:
            raise ValueError('Object changes require kind, object_id and data')
        kind, object_id, data = change['kind'], change['object_id'], change['data']
        if not isinstance(kind, str) or kind not in KINDS:
            raise ValueError('Unsupported studio object kind')
        if not isinstance(object_id, str) or not _ID.fullmatch(object_id):
            raise ValueError('Use a stable object ID of at most 128 ASCII characters')
        if (kind, object_id) in seen:
            raise ValueError('An object may only be changed once in a batch')
        seen.add((kind, object_id))
        if data is not None and not isinstance(data, dict):
            raise ValueError('Object data must be a JSON object; null deletes it')
        try:
            raw = json.dumps(data, ensure_ascii=False, allow_nan=False)
        except (ValueError, TypeError, RecursionError) as exc:
            raise ValueError('Object data must contain finite JSON values') from exc
        size = len(raw.encode())
        total += size
        if size > MAX_OBJECT_BYTES or total > 8 * MAX_OBJECT_BYTES:
            raise ValueError('Studio object/batch is too large')
        result.append({'kind': kind, 'object_id': object_id, 'data': deepcopy(data)})
    return result


def snapshot(conn: sqlite3.Connection, *, kind: str | None = None) -> list[dict]:
    if kind is not None and kind not in KINDS:
        raise ValueError('Unsupported studio object kind')
    sql = 'SELECT kind, object_id, revision, data FROM studio_objects'
    rows = conn.execute(sql + (' WHERE kind = ?' if kind else '') + ' ORDER BY kind, object_id',
                        (kind,) if kind else ())
    return [{'kind': row['kind'], 'object_id': row['object_id'], 'revision': row['revision'],
             'data': json.loads(row['data'])} for row in rows]


def prepare(conn: sqlite3.Connection, changes: list[dict]) -> list[dict]:
    """Capture before/after inside the writer transaction; omit true no-ops."""
    out = []
    for change in changes:
        row = conn.execute('SELECT data FROM studio_objects WHERE kind = ? AND object_id = ?',
                           (change['kind'], change['object_id'])).fetchone()
        before = json.loads(row['data']) if row else None
        after = change['data']
        if before == after:
            continue
        if before and before.get('locked') is True:
            unlocked = {**before, 'locked': False}
            if after != unlocked:
                raise ValueError(f"Object {change['object_id']} is locked; unlock it explicitly first")
        if change['kind'] == 'document' and before and before.get('locked_ids'):
            check_layer_locks(before, after)
        out.append({'kind': change['kind'], 'object_id': change['object_id'],
                    'before': before, 'after': after})
    return out


def check_layer_locks(before: dict, after: dict | None) -> None:
    """Protect locked subtrees and the ancestor transforms they inherit."""
    if after is None:
        raise ValueError('Unlock layers before deleting their document')
    old = {e['id']: e for e in before['elements']}
    new = {e['id']: e for e in after['elements']}
    protected = set()
    for id in before['locked_ids']:
        protected.add(id)
        pending = [id]
        while pending:
            parent_id = pending.pop()
            children = [e['id'] for e in old.values() if e.get('parent_id') == parent_id]
            protected.update(children)
            pending.extend(children)
        parent = old[id].get('parent_id')
        while parent:
            protected.add(parent)
            parent = old[parent].get('parent_id')
    if any(old.get(id) != new.get(id) for id in protected):
        raise ValueError('Unlock the affected layers before editing them')
    for id in protected:
        if old[id]['tag'] in ('group', 'sequence'):
            old_children = [e['id'] for e in before['elements'] if e.get('parent_id') == id]
            new_children = [e['id'] for e in after['elements'] if e.get('parent_id') == id]
            if old_children != new_children:
                raise ValueError('Unlock the affected layers before changing their hierarchy')


def check_operations(conn: sqlite3.Connection, ops, current_ops, changes: list[dict]) -> None:
    """All writers respect persisted locks and source-backed document ownership."""
    if not ops:
        return
    objects = snapshot(conn)
    documents = {o['object_id']: o['data'] for o in objects if o['kind'] == 'document'}
    source_clips = {d['clip_id'] for d in documents.values() if d.get('clip_id')}
    locked_clips = {d['clip_id'] for d in documents.values() if d.get('locked') and d.get('clip_id')}
    locked_documents = {id for id, data in documents.items() if data.get('locked')}
    locked_clips.update(o['object_id'] for o in objects if o['kind'] == 'clip' and o['data'].get('locked'))
    locked_tracks = {o['object_id'] for o in objects if o['kind'] == 'track' and o['data'].get('locked')}
    changed_documents = {c['object_id'] for c in changes if c['kind'] == 'document'}
    effect_owners = {}
    if documents or locked_clips or locked_tracks:
        from open_edit.ir.derive import derive_timeline
        from open_edit.ir.types import Project

        timeline = derive_timeline(Project(name='lock-validation', edit_graph=current_ops))
        for track in timeline.tracks:
            for clip in track.clips:
                if clip.document_id in documents:
                    source_clips.add(clip.clip_id)
                if clip.clip_id in locked_clips or clip.document_id in locked_documents or track.track_id in locked_tracks:
                    locked_clips.add(clip.clip_id)
                    effect_owners.update({e.effect_id: clip.clip_id for e in clip.effects})
            if track.track_id in locked_tracks or any(c.clip_id in locked_clips for c in track.clips):
                effect_owners.update({e.effect_id: track.track_id for e in track.effects})
    for op in ops:
        if op.kind in ('set_graphics_source', 'remove_graphics_source'):
            if op.document_id in documents and op.document_id not in changed_documents:
                raise ValueError('Change graphics through document objects to preserve editable source')
            if op.document_id in changed_documents:
                continue  # source/object locks were checked by prepare in this transaction
        clip_id = getattr(op, 'clip_id', None)
        target = getattr(op, 'target_id', None)
        if op.kind == 'replace_clip_source' and clip_id in source_clips:
            raise ValueError('A source-backed clip must retain its graphics document')
        if clip_id in locked_clips or target in locked_clips or target in locked_tracks or getattr(op, 'effect_id', None) in effect_owners:
            raise ValueError('Unlock the affected clip or track before editing it')
        if getattr(op, 'track_id', None) in locked_tracks or getattr(op, 'new_track_id', None) in locked_tracks:
            raise ValueError('Unlock the affected track before editing it')


def apply(conn: sqlite3.Connection, changes: list[dict], revision: int, *, direction: str = 'after') -> None:
    """Write state and immutable versions, also used by atomic Undo/Redo."""
    for change in changes:
        data = change[direction]
        key = (change['kind'], change['object_id'])
        raw = json.dumps(data, ensure_ascii=False, allow_nan=False) if data is not None else None
        if data is None:
            conn.execute('DELETE FROM studio_objects WHERE kind = ? AND object_id = ?', key)
        else:
            conn.execute('INSERT INTO studio_objects(kind, object_id, revision, data) VALUES (?, ?, ?, ?) '
                         'ON CONFLICT(kind, object_id) DO UPDATE SET revision=excluded.revision, data=excluded.data',
                         (*key, revision, raw))
        conn.execute('INSERT INTO studio_object_versions(kind, object_id, revision, data) VALUES (?, ?, ?, ?)',
                     (*key, revision, raw))
