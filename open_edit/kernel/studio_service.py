"""Shared source-document and annotation interface for HTTP and MCP callers."""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from open_edit.kernel.edit_graph_service import open_store
from open_edit.storage.edit_graph import GraphRevisionConflict
from open_edit.storage.studio import check_layer_locks, validate_changes

Coordinate = Annotated[float, Field(allow_inf_nan=False, ge=-1000000, le=1000000)]
Time = Annotated[float, Field(allow_inf_nan=False, ge=0)]


class Annotation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    tool: Literal['arrow', 'rectangle', 'freehand', 'note', 'pin']
    points: list[tuple[Coordinate, Coordinate]] = Field(min_length=1, max_length=1024)
    text: str = Field(default='', max_length=10000)
    target_ids: list[str] = Field(default_factory=list, max_length=500)
    anchor_sec: Time = 0
    end_sec: Time | None = None
    scope: Literal['frame', 'range', 'object'] = 'frame'
    document_id: str | None = Field(default=None, max_length=128)
    color: str = Field(default='#ffcc55', pattern=r'^#[a-fA-F0-9]{6}$')
    hidden: StrictBool = False
    locked: StrictBool = False
    coordinate_space: Literal['composition', 'object'] = 'composition'
    anchor_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode='after')
    def valid_anchor(self):
        if self.tool in ('arrow', 'rectangle') and len(self.points) != 2:
            raise ValueError('Arrows and rectangles require two points')
        if self.tool == 'freehand' and len(self.points) < 2:
            raise ValueError('Freehand marks require at least two points')
        if self.end_sec is not None and self.end_sec <= self.anchor_sec:
            raise ValueError('Annotation end must be after its anchor time')
        if self.scope == 'range' and self.end_sec is None:
            raise ValueError('Range annotations require an end time')
        if self.scope == 'object' and not self.target_ids:
            raise ValueError('Object annotations require a target')
        if self.coordinate_space == 'object' and (not self.anchor_id or not self.document_id):
            raise ValueError('Object coordinates require a document and anchor ID')
        if any(not isinstance(id, str) or not id or len(id) > 128 for id in self.target_ids):
            raise ValueError('Annotation targets must be bounded stable IDs')
        return self


class GraphicsDocument(BaseModel):
    model_config = ConfigDict(extra='forbid')
    format: Literal['diffusion-graphics-v1'] = 'diffusion-graphics-v1'
    source: str = Field(min_length=1, max_length=512 * 1024)
    duration_sec: Annotated[float, Field(allow_inf_nan=False, gt=0, le=60)] = 3
    fps: StrictInt = Field(default=30, ge=1, le=60)
    clip_id: str = Field(min_length=1, max_length=128)
    track_id: str = Field(default='graphics', min_length=1, max_length=128)
    position_sec: Time = 0
    enabled: StrictBool = True
    locked: StrictBool = False
    locked_ids: list[str] = Field(default_factory=list, max_length=500)
    label: str = Field(default='Graphics', max_length=256)


def _prepare_changes(changes: list[dict], project_path: str | Path) -> list[dict]:
    out = validate_changes(changes)
    for change in out:
        data = change['data']
        if data is None:
            continue
        if change['kind'] == 'annotation':
            change['data'] = Annotation.model_validate(data).model_dump(mode='json')
        elif change['kind'] == 'document':
            from open_edit.integrations.diffusion.graphics import (
                graphics_asset_manifest,
                inspect_source,
                validate_params,
            )

            # Elements are compiler output, never trusted input from a caller.
            values = GraphicsDocument.model_validate({k: v for k, v in data.items()
                                                     if k not in ('elements', 'scene', 'assets')}).model_dump(mode='json')
            normalized = validate_params({k: values[k] for k in ('source', 'duration_sec', 'fps')})
            values.update(normalized)
            values.update(inspect_source(values['source']))
            ids = {e['id'] for e in values['elements']}
            if len(set(values['locked_ids'])) != len(values['locked_ids']) or any(id not in ids for id in values['locked_ids']):
                raise ValueError('Layer locks require unique existing object IDs')
            graphics_asset_manifest(project_path, values['assets'])
            change['data'] = values
    return out


def get_studio(project_path: str | Path, *, kind: str | None = None,
               object_id: str | None = None, include_source: bool = False) -> dict:
    if type(include_source) is not bool:
        raise ValueError('include_source must be boolean')
    result = open_store(Path(project_path)).studio_snapshot(kind)
    objects = result['objects']
    if object_id is not None:
        objects = [obj for obj in objects if obj['object_id'] == object_id]
    if not include_source:
        for obj in objects:
            if obj['kind'] == 'document':
                obj['data'] = {k: v for k, v in obj['data'].items() if k not in ('source', 'elements')}
    return {'status': 'ok', **result, 'objects': objects}


def commit_studio(project_path: str | Path, *, expected_revision: int, changes: list[dict],
                  ops: list[dict] | None = None, author: str = 'user',
                  request_id: str | None = None, label: str | None = None,
                  _status_changes: dict | None = None, _reverted_targets: list[str] | None = None,
                  _preview: bool = False) -> dict:
    from pydantic import TypeAdapter

    from open_edit.ir.types import (
        OperationUnion,
        RemoveGraphicsSourceOp,
        SetGraphicsSourceOp,
    )

    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError('expected_revision must be a nonnegative integer')
    if label is not None and (not isinstance(label, str) or not label or len(label) > 256):
        raise ValueError('Action label must be a nonempty string of at most 256 characters')
    store = open_store(Path(project_path))
    actual = store.graph_revision()
    if actual != expected_revision:
        raise GraphRevisionConflict(expected_revision, actual)
    prepared = _prepare_changes(changes, project_path)
    if ops is not None and (not isinstance(ops, list) or len(ops) > 1000):
        raise ValueError('An editing batch supports at most 1000 operations')
    adapter = TypeAdapter(OperationUnion)
    operations = []
    before = {(o['kind'], o['object_id']): o['data'] for o in store.studio_snapshot()['objects']}
    from open_edit.ir.apply_common import ApplyError
    from open_edit.ir.derive import derive_timeline
    from open_edit.ir.types import Project
    current_ops = store.load_all()
    if _status_changes:
        current_ops = [op.model_copy(update={'status': _status_changes[op.edit_id]['after']})
                       if op.edit_id in _status_changes else op for op in current_ops]
    current_timeline = derive_timeline(Project(name='studio-validation', edit_graph=current_ops), strict=True)
    for change in prepared:
        if change['kind'] != 'document' or change['data'] == before.get(('document', change['object_id'])):
            continue
        data = change['data']
        previous = before.get(('document', change['object_id']))
        if previous and previous.get('locked_ids'):
            check_layer_locks(previous, data)
        if data is None:
            operations.append(RemoveGraphicsSourceOp(author=author, document_id=change['object_id']))
        else:
            if previous and previous['clip_id'] != data['clip_id']:
                raise ValueError('A document must retain its stable clip ID')
            existing = next((c for t in current_timeline.tracks for c in t.clips if c.clip_id == data['clip_id']), None)
            adopt = False
            if existing and not existing.document_id and not previous:
                from open_edit.storage.assets import list_assets_from_disk

                assets = {a.asset_hash: a for a in list_assets_from_disk(project_path)}
                adopt = existing.asset_hash in assets and assets[existing.asset_hash].provider == 'diffusion'
            operations.append(SetGraphicsSourceOp(author=author, document_id=change['object_id'],
                adopt_clip=adopt,
                **{k: data[k] for k in ('source', 'duration_sec', 'fps', 'clip_id', 'track_id',
                                       'position_sec', 'enabled', 'label')}))
    for raw in ops or []:
        if not isinstance(raw, dict):
            raise ValueError('Editing operations must be objects')
        op = adapter.validate_python({**raw, 'author': author})
        if isinstance(op, (SetGraphicsSourceOp, RemoveGraphicsSourceOp)):
            raise ValueError('Change graphics through document objects to preserve source and history')
        operations.append(op)
    # Reject source updates that invalidate explicit trims, IDs or track layout.
    if operations:
        try:
            resulting = derive_timeline(Project(name='studio-validation', edit_graph=[*current_ops, *operations]), strict=True)
        except ApplyError as exc:
            raise ValueError(str(exc)) from exc
        from open_edit.storage.assets import list_assets_from_disk

        assets = {a.asset_hash: a for a in list_assets_from_disk(project_path)}
        for track in resulting.tracks:
            for clip in track.clips:
                if clip.position_sec < 0 or clip.in_point_sec < 0:
                    raise ValueError('Clip positions and source in-points must be nonnegative')
                source_duration = (resulting.graphics_documents[clip.document_id]['duration_sec'] if clip.document_id
                                   else assets[clip.asset_hash].duration_sec if clip.asset_hash in assets else None)
                if source_duration and clip.out_point_sec > source_duration + 1e-6:
                    raise ValueError('A trim cannot extend past the end of its source')
                if clip.track_kind != track.kind:
                    raise ValueError('Move clips to a compatible video or audio track')
    receipt = {}
    if _preview:
        from open_edit.storage.studio import check_operations, prepare

        with store._conn() as conn:
            conn.execute('BEGIN')
            actual = store._revision_in(conn)
            if actual != expected_revision:
                raise GraphRevisionConflict(expected_revision, actual)
            object_changes = prepare(conn, prepared)
            check_operations(conn, operations, current_ops, object_changes)
            if _status_changes:
                check_operations(conn, [op for op in current_ops if op.edit_id in _status_changes], current_ops, object_changes)
        return {'status': 'ok', 'graph_revision': actual, 'changed': False}
    store.append_many(operations, expected_revision=expected_revision, studio_changes=prepared,
                      author=author, request_id=request_id, action_label=label, receipt=receipt,
                      status_changes=_status_changes, reverted_targets=_reverted_targets)
    return {'status': 'ok', **receipt, 'request_id': request_id}


def get_editing_context(project_path: str | Path, *, selected_ids: list[str] | None = None,
                        annotation_ids: list[str] | None = None, playhead_sec: float | None = None,
                        document_id: str | None = None) -> dict:
    """Source/object context, rather than a screenshot per video frame."""
    store = open_store(Path(project_path))
    if selected_ids is None and annotation_ids is None and document_id is None:
        import json

        with store._conn() as conn:
            row = conn.execute("SELECT value FROM project_meta WHERE key = 'studio_selection'").fetchone()
        saved = json.loads(row['value']) if row else {}
        selected_ids = saved.get('selected_ids', [])
        annotation_ids = saved.get('annotation_ids', [])
        document_id = saved.get('document_id')
        if playhead_sec is None:
            playhead_sec = saved.get('playhead_sec', 0)
    if playhead_sec is None:
        playhead_sec = 0
    if not isinstance(selected_ids, (list, type(None))) or len(selected_ids or []) > 500:
        raise ValueError('Selection supports at most 500 stable IDs')
    if not isinstance(annotation_ids, (list, type(None))) or len(annotation_ids or []) > 500:
        raise ValueError('Context supports at most 500 annotation IDs')
    from math import isfinite

    if isinstance(playhead_sec, bool) or not isinstance(playhead_sec, (float, int)) or not isfinite(playhead_sec) or playhead_sec < 0:
        raise ValueError('playhead_sec must be a nonnegative finite number')
    if any(not isinstance(id, str) or not id or len(id) > 128 for id in [*(selected_ids or []), *(annotation_ids or [])]):
        raise ValueError('Context IDs must be bounded stable strings')
    if document_id is not None and (not isinstance(document_id, str) or not document_id or len(document_id) > 128):
        raise ValueError('Context document_id must be a bounded stable string')
    snapshot = get_studio(project_path, include_source=True)
    from open_edit.ir.derive import derive_timeline
    from open_edit.ir.types import Project
    revision, ops = store.read_snapshot()
    if revision != snapshot['graph_revision']:
        raise GraphRevisionConflict(snapshot['graph_revision'], revision)
    timeline = derive_timeline(Project(name=Path(project_path).name, edit_graph=ops))
    selected = set(selected_ids or [])
    notes = set(annotation_ids or [])
    selected_clips = [c.model_dump(mode='json') for t in timeline.tracks for c in t.clips if c.clip_id in selected]
    selected_docs = {c['document_id'] for c in selected_clips if c['document_id']}
    return {'status': 'ok', 'graph_revision': snapshot['graph_revision'],
            'playhead_sec': playhead_sec, 'selected_ids': selected_ids or [], 'document_id': document_id,
            'selected_clips': selected_clips,
            'timeline': timeline.model_dump(mode='json', exclude={'graphics_documents'}),
            'documents': [o for o in snapshot['objects'] if o['kind'] == 'document' and
                          (document_id is None or o['object_id'] == document_id or o['object_id'] in selected_docs) and
                          (not selected or o['object_id'] in selected or o['object_id'] in selected_docs or
                           any(e['id'] in selected for e in o['data'].get('elements', [])))],
            'annotations': [o for o in snapshot['objects'] if o['kind'] == 'annotation' and
                            (document_id is None or o['data'].get('document_id') in (None, document_id) or o['object_id'] in notes) and
                            not o['data'].get('hidden') and (not notes or o['object_id'] in notes)]}


def save_editing_selection(project_path: str | Path, *, expected_revision: int, selected_ids: list[str],
                           annotation_ids: list[str], document_id: str | None, playhead_sec: float) -> dict:
    """Workspace focus is shared with external agents, without an edit/Undo step."""
    import json

    # Reuse the public context contract for validation and stable document scope.
    context = get_editing_context(project_path, selected_ids=selected_ids, annotation_ids=annotation_ids,
                                  document_id=document_id, playhead_sec=playhead_sec)
    store = open_store(Path(project_path))
    with store._conn() as conn:
        conn.execute('BEGIN IMMEDIATE')
        revision = store._revision_in(conn)
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError('expected_revision must be a nonnegative integer')
        if revision != expected_revision:
            raise GraphRevisionConflict(expected_revision, revision)
        values = {k: context[k] for k in ('selected_ids', 'document_id', 'playhead_sec')}
        values['annotation_ids'] = annotation_ids
        conn.execute("INSERT INTO project_meta(key,value) VALUES ('studio_selection',?) "
                     'ON CONFLICT(key) DO UPDATE SET value=excluded.value', (json.dumps(values),))
    return {'status': 'ok', 'graph_revision': revision}
