"""Shared source-document and annotation interface for HTTP and MCP callers."""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from open_edit.kernel.edit_graph_service import open_store
from open_edit.storage.edit_graph import GraphRevisionConflict
from open_edit.storage.studio import check_layer_locks, validate_changes

Coordinate = Annotated[float, Field(allow_inf_nan=False, ge=-1000000, le=1000000)]
Time = Annotated[float, Field(allow_inf_nan=False, ge=0)]


class EditingRegion(BaseModel):
    """A spatial instruction anchored to a displayed frame, never a render edit."""
    model_config = ConfigDict(extra='forbid')
    left: Time
    top: Time
    right: Time
    bottom: Time
    canvas_width: Annotated[float, Field(allow_inf_nan=False, gt=0, le=1000000)]
    canvas_height: Annotated[float, Field(allow_inf_nan=False, gt=0, le=1000000)]
    playhead_sec: Time
    coordinate_space: Literal['composition'] = 'composition'

    @field_validator('left', 'top', 'right', 'bottom', 'canvas_width', 'canvas_height', 'playhead_sec', mode='before')
    @classmethod
    def numeric_coordinates(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError('Region coordinates must be finite numbers')
        return value

    @model_validator(mode='after')
    def valid_bounds(self):
        if not (self.left < self.right <= self.canvas_width and
                self.top < self.bottom <= self.canvas_height):
            raise ValueError('Region must be a nonempty rectangle inside the displayed canvas')
        return self


class EditingFocus(BaseModel):
    model_config = ConfigDict(extra='forbid')
    selected_ids: list[Annotated[str, Field(min_length=1, max_length=128)]] = Field(default_factory=list, max_length=500)
    annotation_ids: list[Annotated[str, Field(min_length=1, max_length=128)]] = Field(default_factory=list, max_length=500)
    document_id: str | None = Field(default=None, min_length=1, max_length=128)
    playhead_sec: Time = 0
    region: EditingRegion | None = None

    @field_validator('playhead_sec', mode='before')
    @classmethod
    def numeric_time(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError('playhead_sec must be a nonnegative finite number')
        return value


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
        elif change['kind'] == 'font':
            if set(data) - {'label', 'font_id', 'locked'} or not isinstance(data.get('label'), str) or not 1 <= len(data['label']) <= 256 or type(data.get('locked', False)) is not bool:
                raise ValueError('Project fonts require a name and immutable font_id')
            from open_edit.render.captions import font_path

            font_path(Path(project_path), data.get('font_id', ''))
        elif change['kind'] in ('caption', 'style'):
            from open_edit.ir.captions import CaptionCue, CaptionStyle

            if change['kind'] == 'caption':
                change['data'] = CaptionCue.model_validate(data).model_dump(mode='json')
                style = change['data']['style']
            else:
                if set(data) - {'label', 'caption_style', 'locked'} or not isinstance(data.get('label'), str) or not 1 <= len(data['label']) <= 256 or type(data.get('locked', False)) is not bool:
                    raise ValueError('Styles require a name and editable caption_style')
                style = CaptionStyle.model_validate(data.get('caption_style', {})).model_dump(mode='json')
                change['data'] = {**data, 'caption_style': style}
            if style['font_id']:
                from open_edit.render.captions import font_path

                font_path(Path(project_path), style['font_id'])
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
    project_path=Path(project_path)
    from pydantic import TypeAdapter

    from open_edit.ir.types import (
        OperationUnion,
        RemoveCaptionOp,
        RemoveGraphicsSourceOp,
        SetCaptionOp,
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
        if change['kind'] == 'caption' and change['data'] != before.get(('caption', change['object_id'])):
            operations.append(SetCaptionOp(author=author, caption_id=change['object_id'], cue=change['data']) if change['data'] is not None else RemoveCaptionOp(author=author, caption_id=change['object_id']))
            continue
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
        if isinstance(op, (SetCaptionOp, RemoveCaptionOp)):
            raise ValueError('Change captions through caption objects to preserve source and history')
        if op.kind in ('add_effect', 'set_keyframe'):
            from open_edit.ir.studio_ops import validate_effect_edit

            validate_effect_edit(op, derive_timeline(Project(name='effect-validation', edit_graph=[*current_ops, *operations])))
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


def apply_graphics_edits(project_path: str | Path, *, expected_revision: int, document_id: str,
                        edits: list[dict], author: str = 'ai', request_id: str | None = None,
                        label: str | None = None) -> dict:
    """Edit stored literal JSX by stable source IDs without a source round trip."""
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError('expected_revision must be a nonnegative integer')
    if not isinstance(document_id, str) or not document_id or len(document_id) > 128:
        raise ValueError('document_id must be a bounded stable string')
    if not isinstance(edits, list) or not 1 <= len(edits) <= 1000 or any(not isinstance(e, dict) for e in edits):
        raise ValueError('Provide between 1 and 1000 source edits')
    snapshot = get_studio(project_path, kind='document', object_id=document_id, include_source=True)
    if snapshot['graph_revision'] != expected_revision:
        raise GraphRevisionConflict(expected_revision, snapshot['graph_revision'])
    if not snapshot['objects']:
        raise ValueError('Graphics document not found')
    data = snapshot['objects'][0]['data']
    if data.get('locked'):
        raise ValueError('Unlock the document before editing it')
    from open_edit.integrations.diffusion.graphics import compile_editor

    compiled = compile_editor(project_path, source=data['source'], edits=edits, expected_revision=expected_revision)
    # The shared commit enforces layer locks and retains trims/effects/history.
    return commit_studio(project_path, expected_revision=expected_revision,
                         changes=[{'kind': 'document', 'object_id': document_id,
                                   'data': {**data, 'source': compiled['source']}}],
                         author=author, request_id=request_id, label=label or 'Edit graphics layers')


def get_editing_context(project_path: str | Path, *, selected_ids: list[str] | None = None,
                        annotation_ids: list[str] | None = None, playhead_sec: float | None = None,
                        document_id: str | None = None, region: dict | None = None,
                        include_source: bool = False, include_timeline: bool = False,
                        offset: int = 0, limit: int = 20, section: str | None = None) -> dict:
    """Bounded target context. Fetch literal source/full timeline explicitly on demand."""
    import json

    from open_edit.ir.derive import derive_timeline
    from open_edit.ir.types import Project
    from open_edit.kernel.editing_context import build_context
    from open_edit.storage.studio import snapshot

    if type(include_source) is not bool or type(include_timeline) is not bool:
        raise ValueError('include_source and include_timeline must be boolean')
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Context pagination requires offset >= 0 and limit between 1 and 100')
    store = open_store(Path(project_path))
    # Focus, source objects and operations must describe the SAME revision.
    with store._conn() as conn:
        conn.execute('BEGIN')
        revision = store._revision_in(conn)
        if selected_ids is None and annotation_ids is None and document_id is None and region is None:
            row = conn.execute("SELECT value FROM project_meta WHERE key = 'studio_selection'").fetchone()
            saved = json.loads(row['value']) if row else {}
            selected_ids = saved.get('selected_ids', [])
            annotation_ids = saved.get('annotation_ids', [])
            document_id = saved.get('document_id')
            region = saved.get('region')
            if playhead_sec is None:
                playhead_sec = saved.get('playhead_sec', 0)
        focus = EditingFocus(selected_ids=selected_ids if selected_ids is not None else [],
                             annotation_ids=annotation_ids if annotation_ids is not None else [],
                             document_id=document_id, playhead_sec=playhead_sec if playhead_sec is not None else 0,
                             region=region)
        objects = snapshot(conn)
        ops = store._load_all_in(conn)
    timeline = derive_timeline(Project(name=Path(project_path).name, edit_graph=ops))
    return build_context(timeline, objects, revision, focus.model_dump(mode='json'),
                         include_source=include_source, include_timeline=include_timeline,
                         offset=offset, limit=limit, section=section)


def save_editing_selection(project_path: str | Path, *, expected_revision: int, selected_ids: list[str],
                           annotation_ids: list[str], document_id: str | None, playhead_sec: float,
                           region: dict | None = None) -> dict:
    """Workspace focus is shared with external agents, without an edit/Undo step."""
    import json

    # Focus changes must not load/compile source or replay the render graph.
    values = EditingFocus(selected_ids=selected_ids, annotation_ids=annotation_ids,
                          document_id=document_id, playhead_sec=playhead_sec, region=region).model_dump(mode='json')
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError('expected_revision must be a nonnegative integer')
    store = open_store(Path(project_path))
    with store._conn() as conn:
        conn.execute('BEGIN IMMEDIATE')
        revision = store._revision_in(conn)
        if revision != expected_revision:
            raise GraphRevisionConflict(expected_revision, revision)
        conn.execute("INSERT INTO project_meta(key,value) VALUES ('studio_selection',?) "
                     'ON CONFLICT(key) DO UPDATE SET value=excluded.value', (json.dumps(values),))
    return {'status': 'ok', 'graph_revision': revision}
