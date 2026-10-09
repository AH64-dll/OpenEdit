"""Selective request inverse with three-way source merge and dependency checks."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from open_edit.kernel.edit_graph_service import open_store
from open_edit.kernel.studio_service import commit_studio
from open_edit.storage.edit_graph import GraphRevisionConflict
from open_edit.storage.studio import snapshot

_MISSING = object()


def _track_inverse(before: dict, after: dict, current: dict, path: str, conflicts: list[dict]) -> dict:
    """Merge motion/effects by stable identity, preserving unrelated manual work."""
    def indexed(data):
        return {**data,
                'effects': {e['effect_id']: e for e in data['effects']},
                'frames': {str(float(f['time_sec'])): f for f in data['frames']}}
    merged = _inverse(indexed(before), indexed(after), indexed(current), path, conflicts)
    return {**merged, 'effects': list(merged['effects'].values()),
            'frames': sorted(merged['frames'].values(), key=lambda f: f['time_sec'])}


def _inverse(before, after, current, path: str, conflicts: list[dict]):
    if before == after or current == before:
        return current
    if isinstance(before, dict) and isinstance(after, dict) and isinstance(current, dict):
        result = dict(current)
        for key in before.keys() | after.keys():
            value = _inverse(before.get(key, _MISSING), after.get(key, _MISSING), current.get(key, _MISSING),
                             path + '.' + key, conflicts)
            if value is _MISSING:
                result.pop(key, None)
            else:
                result[key] = value
        return result
    if current == after:
        return before
    conflicts.append({'field': path, 'reason': 'Later work changed the same property'})
    return current


def revert_request(project_path: str | Path, *, request_id: str, expected_revision: int,
                   preview: bool = False) -> dict:
    if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
        raise ValueError('A bounded request_id is required')
    if type(expected_revision) is not int or expected_revision < 0 or type(preview) is not bool:
        raise ValueError('Use a nonnegative expected_revision and boolean preview')
    store = open_store(Path(project_path))
    with store._conn() as conn:
        conn.execute('BEGIN')
        revision = store._revision_in(conn)
        if revision != expected_revision:
            raise GraphRevisionConflict(expected_revision, revision)
        targets = conn.execute("SELECT * FROM edit_actions WHERE request_id=? AND author='ai' AND state='applied' AND reverted_by IS NULL ORDER BY sequence DESC", (request_id,)).fetchall()
        objects = {(o['kind'], o['object_id']): o['data'] for o in snapshot(conn)}
        operations = store._load_all_in(conn)
        later = conn.execute("SELECT action_id,label,sequence FROM edit_actions WHERE state='applied' AND reverted_by IS NULL ORDER BY sequence DESC").fetchall()
    if not targets:
        raise ValueError('No applied AI actions exist for this request')
    original = dict(objects)
    conflicts, statuses = [], {}
    for row in targets:
        for edit_id, status in json.loads(row['operations']).items():
            op = next((o for o in operations if o.edit_id == edit_id), None)
            if op is None or op.status != status:
                conflicts.append({'field': edit_id, 'reason': 'Request operation was changed'})
            elif op.kind not in ('set_graphics_source', 'remove_graphics_source', 'set_caption', 'remove_caption'):
                statuses[edit_id] = {'before': status, 'after': 'reverted'}
        for change in reversed(json.loads(row['object_changes'])):
            key = change['kind'], change['object_id']
            before, after, current = change['before'], change['after'], objects.get(key)
            # Compiler indexes are derived, not independently merged edits.
            def clean(data, kind=key[0]):
                return {k: v for k, v in data.items() if k not in ('elements', 'scene', 'assets')} if isinstance(data, dict) and kind == 'document' else data
            before, after, current = clean(before), clean(after), clean(current)
            if key[0] == 'document' and all(isinstance(v, dict) for v in (before, after, current)):
                from open_edit.integrations.diffusion.graphics import _worker

                with tempfile.TemporaryDirectory(prefix='openedit-source-revert-') as directory:
                    result = _worker({'source': current['source'], 'inverse': {'before': before['source'], 'after': after['source']}}, Path(directory), timeout=30)
                conflicts.extend({**c, 'document_id': key[1]} for c in result['conflicts'])
                merged = _inverse({k: v for k, v in before.items() if k != 'source'},
                                  {k: v for k, v in after.items() if k != 'source'},
                                  {k: v for k, v in current.items() if k != 'source'}, key[1], conflicts)
                objects[key] = {**merged, 'source': result['source']}
            elif key[0] == 'object_track' and all(isinstance(v, dict) for v in (before, after, current)):
                objects[key] = _track_inverse(before, after, current, key[1], conflicts)
            else:
                objects[key] = _inverse(before, after, current, key[1], conflicts)
    changes = [{'kind': key[0], 'object_id': key[1], 'data': data} for key, data in objects.items() if data != original.get(key)]
    # Validate on a scratch read-only derivation before any status is touched.
    from types import SimpleNamespace

    from open_edit.ir.apply_common import ApplyError
    from open_edit.ir.derive import derive_timeline
    from open_edit.ir.types import Project
    from open_edit.ir.validate import validate_op_for_append

    candidate = [o.model_copy(update={'status': statuses[o.edit_id]['after']}) if o.edit_id in statuses else o for o in operations]
    affected = set(statuses)
    for op in operations:
        if op.status == 'applied' and op.edit_id not in affected and op.parent_id in affected:
            conflicts.append({'field': op.edit_id, 'reason': 'A later action depends on this request as its parent'})
    prefix = []
    view = SimpleNamespace(db_path=store.db_path, project_id=store.project_id, load_all=lambda: prefix)
    for op in candidate:
        if op.status == 'applied':
            for error in validate_op_for_append(op, view):
                conflicts.append({'field': op.edit_id, 'reason': error})
        prefix.append(op)
    removed_documents = {c['object_id'] for c in changes if c['kind'] == 'document' and c['data'] is None}
    for change in changes:
        if change['kind'] != 'document':
            continue
        old = original.get(('document', change['object_id'])) or {}
        if change['data']:
            from open_edit.integrations.diffusion.graphics import inspect_source

            remaining = {e['id'] for e in inspect_source(change['data']['source'])['elements']}
        else:
            remaining = set()
        removed_ids = {e['id'] for e in old.get('elements', [])} - remaining
        for (kind, object_id), data in objects.items():
            if kind != 'annotation' or not data or data.get('document_id') != change['object_id']:
                continue
            if data.get('anchor_id') in removed_ids or removed_ids.intersection(data.get('target_ids', [])) or not change['data']:
                conflicts.append({'field': object_id, 'reason': 'An AI mark depends on an object created by this request'})
    if removed_documents:
        timeline = derive_timeline(Project(name='request-dependencies', edit_graph=operations))
        removed_clips = {c.clip_id for t in timeline.tracks for c in t.clips if c.document_id in removed_documents}
        target_ops = {key for row in targets for key in json.loads(row['operations'])}
        for op in operations:
            values = op.model_dump(mode='json')
            if (op.status == 'applied' and op.edit_id not in target_ops and
                    any(values.get(k) in removed_clips for k in ('clip_id', 'target_id', 'from_clip_id', 'to_clip_id'))):
                conflicts.append({'field': op.edit_id, 'reason': 'Later work depends on a composition created by this request'})
    try:
        derive_timeline(Project(name='request-inverse', edit_graph=candidate), strict=True)
    except (ValueError, ApplyError) as exc:
        conflicts.append({'field': 'timeline', 'reason': str(exc)})
    if store.graph_revision() != revision:
        raise GraphRevisionConflict(revision, store.graph_revision())
    result = {'graph_revision': revision, 'request_id': request_id, 'conflicts': conflicts,
              'dependencies': [dict(r) for r in later if r['sequence'] > min(t['sequence'] for t in targets)],
              'changed_object_ids': [c['object_id'] for c in changes], 'operation_count': len(statuses),
              'can_revert': not conflicts, 'changed': False}
    if conflicts:
        return result
    try:
        committed = commit_studio(project_path, expected_revision=revision, changes=changes,
                                  label='Revert AI request: ' + targets[-1]['label'],
                                  _status_changes=statuses, _reverted_targets=[t['action_id'] for t in targets], _preview=preview)
    except (ValueError, ApplyError) as exc:
        # Locks and full source/trim validation can reveal a final dependency.
        return {**result, 'can_revert': False, 'conflicts': [{'field': 'project', 'reason': str(exc)}]}
    if preview:
        return result
    return {**result, **committed, **store.history()}
