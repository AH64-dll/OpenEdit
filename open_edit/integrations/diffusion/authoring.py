"""Revision-checked media JSX view over the canonical OpenEdit graph."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote, unquote

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, ValidationError

from open_edit.integrations.diffusion.compiler import (
    MAX_SOURCE_BYTES,
    parse_and_compile,
    worker_ready,
)
from open_edit.ir.derive import derive_timeline
from open_edit.ir.types import (
    AddClipOp,
    MoveClipOp,
    Project,
    RemoveClipOp,
    ReplaceClipSourceOp,
    SetAudioGainOp,
    TrimClipOp,
)
from open_edit.storage.assets import list_assets_from_disk
from open_edit.storage.edit_graph import EditGraphStore, GraphRevisionConflict
from open_edit.storage.paths import ProjectPaths

FORMAT = 'diffusion-jsx-v1'
MAX_CLIPS = 2000
Seconds = Annotated[StrictFloat, Field(ge=0)]
Volume = Annotated[StrictFloat, Field(ge=-120, le=24)]


class _LiteralModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class _Clip(_LiteralModel):
    id: str
    tag: Literal['video', 'audio', 'image']
    src: str
    start: Seconds
    source_in: Seconds = Field(alias="sourceIn")
    source_out: Seconds = Field(alias="sourceOut")
    playback_rate: StrictFloat = Field(default=1.0, alias="playbackRate", ge=0.125, le=8)
    volume: Volume = 0.0


class _Track(_LiteralModel):
    id: str
    clips: list[_Clip]


class _Document(_LiteralModel):
    stage: dict
    scene: dict
    tracks: list[_Track]


def element_id(kind: str, value: str) -> str:
    return f'{kind}-{quote(value, safe="-._~")}'


def _identity(kind: str, value: str) -> str:
    if not value.startswith(f'{kind}-'):
        raise ValueError(f'Expected a {kind}- prefixed stable element id')
    decoded = unquote(value[2:], errors='strict')
    if not decoded or len(decoded) > 256 or element_id(kind, decoded) != value:
        raise ValueError('Invalid or noncanonical element id')
    return decoded


def _gain_db(clip) -> float:
    gain = 0.0
    for effect in clip.effects:
        if effect.effect_type == 'speed' and effect.params.get('rate', 1) != 1:
            raise ValueError(f'Clip {clip.clip_id}: playback-rate parity is not yet supported by authoring')
        if effect.effect_type == 'speed_ramp':
            raise ValueError(f'Clip {clip.clip_id}: speed ramps are not supported by authoring')
        if effect.effect_type != 'volume':
            continue
        if effect.keyframes or effect.params.get('normalize') or set(effect.params) != {'gain'}:
            raise ValueError(f'Clip {clip.clip_id}: dynamic/normalized gain cannot be represented as constant volume')
        value = effect.params['gain']
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError('Nonpositive or nonfinite volume cannot be represented')
        gain += 20 * math.log10(value)
    return gain


def _snapshot(project_path):
    paths = ProjectPaths.for_project(project_path)
    if not paths.db_path.is_file():
        raise ValueError('Edit graph not found')
    store = EditGraphStore(paths.db_path)
    project_id = store.project_id
    revision, ops = store.read_snapshot()
    assets = {asset.asset_hash: asset for asset in list_assets_from_disk(paths.root)}
    timeline = derive_timeline(Project(project_id=project_id, name=paths.root.name, workdir=paths.root, assets=assets, edit_graph=ops))
    return store, revision, timeline, assets


def _document(timeline, assets) -> _Document:
    from open_edit.integrations.diffusion.timing import timing_provenance

    tracks = []
    clip_ids = set()
    for track in timeline.tracks:
        clips = []
        for clip in sorted(track.clips, key=lambda c: (c.position_sec, c.clip_id)):
            if clip.document_id is not None:
                # Source-backed graphics have their own editable documents;
                # a media-JSX save must preserve them, not flatten/delete them.
                continue
            if clip.clip_id in clip_ids:
                raise ValueError('The timeline contains duplicate clip identities')
            clip_ids.add(clip.clip_id)
            asset = assets.get(clip.asset_hash)
            if asset is None:
                raise ValueError(f'Clip {clip.clip_id}: asset metadata not found')
            tag = 'audio' if track.kind == 'audio' else asset.type
            source_hash = clip.asset_hash
            source_in, source_out, playback_rate = clip.in_point_sec, clip.out_point_sec, 1.0
            provenance = timing_provenance(asset)
            if provenance and len(provenance['segments']) == 1:
                segment = provenance['segments'][0]
                original = assets.get(provenance['asset_hash'])
                if original is None:
                    raise ValueError('Retimed clip original CAS asset is missing')
                source_hash = original.asset_hash
                playback_rate = segment['rate']
                source_in = segment['source_in'] + clip.in_point_sec * playback_rate
                source_out = segment['source_in'] + clip.out_point_sec * playback_rate
                tag = 'audio' if track.kind == 'audio' else original.type
            if (track.kind == 'audio' and asset.type == 'image') or (track.kind == 'video' and tag == 'audio'):
                raise ValueError('Media kind does not match its track')
            clips.append(_Clip(
                id=element_id('c', clip.clip_id), tag=tag, src=f'asset://{quote(source_hash, safe="-._~")}',
                start=clip.position_sec, sourceIn=source_in, sourceOut=source_out,
                volume=_gain_db(clip), playbackRate=playback_rate,
            ))
        tracks.append(_Track(id=element_id('t', track.track_id), clips=clips))
    if len(clip_ids) > MAX_CLIPS:
        raise ValueError(f'Authoring supports at most {MAX_CLIPS} media clips')
    document = _Document(stage={'id': 'openedit'}, scene={'id': 'main', 'width': 1920, 'height': 1080, 'active': True}, tracks=tracks)
    # Do not offer a source view that cannot round-trip unchanged. Legacy
    # projects with unresolved ranges or overlaps can still use the ordinary
    # timeline tools; the media adapter needs explicit valid ranges.
    _validate_target(document, document, timeline, assets)
    return document


def _source(document: _Document) -> str:
    lines = ['export default function OpenEditProject() {', '  return (', '    <stage id="openedit">', '      <scene id="main" width={1920} height={1080} active>']
    for track in document.tracks:
        lines.append(f'        <group id="{track.id}">')
        for clip in track.clips:
            props = ' '.join(f'{key}={{{json.dumps(value, ensure_ascii=True, allow_nan=False)}}}' for key, value in clip.model_dump(by_alias=True).items() if key not in {'id', 'tag'})
            lines.append(f'          <{clip.tag} id="{clip.id}" {props} />')
        lines.append('        </group>')
    lines.extend(['      </scene>', '    </stage>', '  );', '}', ''])
    source = '\n'.join(lines)
    if len(source.encode()) > MAX_SOURCE_BYTES:
        raise ValueError('Authoring document exceeds 512 KiB; use structured timeline tools')
    return source


def get_authoring_view(project_path: str | Path, *, include_source: bool = False) -> dict:
    if type(include_source) is not bool:
        raise ValueError('include_source must be a boolean')
    store, revision, timeline, assets = _snapshot(project_path)
    document = _document(timeline, assets)
    out = {
        'status': 'ok', 'format': FORMAT, 'project_id': store.project_id,
        'graph_revision': revision, 'clip_count': sum(len(t.clips) for t in document.tracks),
        'track_count': len(timeline.tracks),
        'tracks': [{'track_id': t.track_id, 'kind': t.kind, 'source_id': f'index.tsx:{element_id("t", t.track_id)}'} for t in timeline.tracks[:50]],
        'tracks_truncated': len(timeline.tracks) > 50,
        'worker_ready': worker_ready(),
        'supported': ['add', 'remove', 'move', 'trim', 'replace_source', 'constant_volume_db', 'playback_rate_CAS'],
        'preserved': {'html_overlays': len(timeline.overlays), 'remotion_compositions': len(timeline.remotion_compositions), 'effects': sum(len(t.effects) + sum(len(c.effects) for c in t.clips) for t in timeline.tracks)},
        'limitations': ['literal media JSX only', 'non-unity rates materialize checked CAS media first', 'legacy speed effects remain on the legacy path', 'track order is fixed', 'existing effects and overlays stay in the graph', 'canvas size is authoring metadata; rendering uses the existing profile'],
    }
    if include_source:
        out['source'] = store.load_authoring_source(FORMAT, revision) or _source(document)
        elements = [
            {'source_id': f'index.tsx:{clip.id}', 'track_id': track.id, **clip.model_dump(by_alias=True)}
            for track in document.tracks for clip in track.clips
        ]
        out['elements'] = elements[:50]
        out['elements_truncated'] = len(elements) > 50
    return out


def _validate_target(target: _Document, before: _Document, timeline, assets):
    if target.stage != before.stage or target.scene != before.scene or any(type(target.scene.get(k)) is not type(v) for k, v in before.scene.items()):
        raise ValueError('Stage and scene settings cannot be changed by the media adapter')
    old_track_ids = [t.id for t in before.tracks]
    if [t.id for t in target.tracks][:len(old_track_ids)] != old_track_ids:
        raise ValueError('Existing tracks must keep their IDs and order; new tracks may be appended')
    known_kinds = {t.track_id: t.kind for t in timeline.tracks}
    track_ids, clip_ids = set(), set()
    records = {}
    asset_urls = {f'asset://{quote(hash_, safe="-._~")}': hash_ for hash_ in assets}
    for track in target.tracks:
        track_id = _identity('t', track.id)
        if track_id in track_ids:
            raise ValueError('Duplicate track identity')
        track_ids.add(track_id)
        kind = known_kinds.get(track_id)
        if kind is None:
            if not track.clips:
                raise ValueError('New tracks must contain at least one clip')
            kind = 'audio' if track.clips[0].tag == 'audio' else 'video'
        prior_end = -1.0
        for clip in sorted(track.clips, key=lambda c: (c.start, c.id)):
            clip_id = _identity('c', clip.id)
            if clip_id in clip_ids:
                raise ValueError('Duplicate clip identity')
            clip_ids.add(clip_id)
            if clip.source_out <= clip.source_in:
                raise ValueError('sourceOut must be greater than sourceIn')
            if clip.start < prior_end - 1e-9:
                raise ValueError('Media clips must not overlap on the same track')
            prior_end = clip.start + (clip.source_out - clip.source_in) / clip.playback_rate
            asset_hash = asset_urls.get(clip.src)
            if asset_hash is None:
                raise ValueError('src must identify an asset in the pinned project CAS')
            asset = assets[asset_hash]
            if (kind == 'audio' and clip.tag != 'audio') or (kind == 'video' and clip.tag not in {'video', 'image'}):
                raise ValueError('Clip tag does not match track kind')
            if (clip.tag == 'image' and asset.type != 'image') or (clip.tag == 'video' and asset.type != 'video') or (clip.tag == 'audio' and asset.type not in {'video', 'audio'}):
                raise ValueError('Clip tag does not match asset kind')
            if asset.type != 'image' and (asset.duration_sec <= 0 or clip.source_out > asset.duration_sec + 1e-6):
                raise ValueError('Source range exceeds asset duration')
            if clip.tag == 'image' and not math.isclose(clip.volume, 0, abs_tol=1e-8):
                raise ValueError('Still images do not carry audio volume')
            records[clip_id] = (clip, track_id, kind, asset_hash)
    if len(clip_ids) > MAX_CLIPS:
        raise ValueError(f'Authoring supports at most {MAX_CLIPS} media clips')
    return records


def apply_authoring_edit(project_path, *, expected_revision, source=None, edits=None, author='ai') -> dict:
    if author not in {'ai', 'user'}:
        raise ValueError('author must be ai or user')
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError('expected_revision must be a nonnegative integer')
    if (source is None) == (edits is None):
        raise ValueError('Provide exactly one of source or edits')
    store, revision, timeline, assets = _snapshot(project_path)
    if revision != expected_revision:
        raise GraphRevisionConflict(expected_revision, revision)
    before = _document(timeline, assets)
    base_source = store.load_authoring_source(FORMAT, revision) or _source(before)
    compiled = parse_and_compile(source if source is not None else base_source, edits=edits)
    try:
        target = _Document.model_validate(compiled['document'])
    except ValidationError as exc:
        error = exc.errors()[0]
        raise ValueError(f'Invalid authoring field {error["loc"]}: {error["msg"]}') from exc
    records = _validate_target(target, before, timeline, assets)
    old = {c.clip_id: c for t in timeline.tracks for c in t.clips if c.document_id is None}
    # Versioned CAS retiming leaves the legacy speed-op replay untouched. The
    # graph receives ordinary zero-based media only after frame/audio QC.
    from open_edit.integrations.diffusion.timing import bake_timing

    old_literals = {_identity('c', c.id): c for t in before.tracks for c in t.clips}
    changed_rates = [id_ for id_, (c, _, _, _) in records.items() if c.playback_rate != 1 and
                     (id_ not in old_literals or any(getattr(c, k) != getattr(old_literals[id_], k)
                                                    for k in ('src', 'source_in', 'source_out', 'playback_rate')))]
    if len(changed_rates) > 20:
        raise ValueError('Retiming is limited to 20 changed clips per authoring transaction')
    for clip_id, (clip, track_id, kind, asset_hash) in list(records.items()):
        if clip.playback_rate == 1:
            continue
        original = old.get(clip_id)
        prior = old_literals.get(clip_id)
        same_source = prior is not None and prior.src == clip.src and all(
            math.isclose(getattr(prior, key), getattr(clip, key), abs_tol=1e-8)
            for key in ('source_in', 'source_out', 'playback_rate'))
        if same_source and original:
            physical_hash = original.asset_hash
            physical_in, physical_out = original.in_point_sec, original.out_point_sec
        else:
            materialized = bake_timing(project_path, asset_hash=asset_hash, source_in=clip.source_in,
                                       source_out=clip.source_out, playback_rate=clip.playback_rate)
            physical_hash, physical_in, physical_out = materialized['asset_hash'], 0.0, materialized['duration_sec']
        physical = clip.model_copy(update={'source_in': physical_in, 'source_out': physical_out, 'playback_rate': 1.0})
        records[clip_id] = (physical, track_id, kind, physical_hash)
    ops = [RemoveClipOp(author=author, clip_id=id_) for id_ in old if id_ not in records]
    for clip_id, (clip, track_id, kind, asset_hash) in records.items():
        original = old.get(clip_id)
        if original is None:
            ops.append(AddClipOp(author=author, clip_id=clip_id, asset_hash=asset_hash, track_id=track_id, track_kind=kind, position_sec=clip.start, in_point_sec=clip.source_in, out_point_sec=clip.source_out))
            old_gain = 0.0
        else:
            if original.track_kind != kind:
                raise ValueError('Moving a clip between audio and video tracks is unsupported')
            if original.asset_hash != asset_hash:
                ops.append(ReplaceClipSourceOp(author=author, clip_id=clip_id, new_asset_hash=asset_hash))
            if original.position_sec != clip.start or original.track_id != track_id:
                ops.append(MoveClipOp(author=author, clip_id=clip_id, new_track_id=track_id, new_position_sec=clip.start))
            if original.in_point_sec != clip.source_in or original.out_point_sec != clip.source_out:
                ops.append(TrimClipOp(author=author, clip_id=clip_id, new_in_point_sec=clip.source_in, new_out_point_sec=clip.source_out))
            old_gain = _gain_db(original)
        if not math.isclose(clip.volume, old_gain, rel_tol=1e-10, abs_tol=1e-8):
            ops.append(SetAudioGainOp(author=author, clip_id=clip_id, gain_db=clip.volume - old_gain))
    store.append_many(
        ops, expected_revision=expected_revision,
        authoring_view=(FORMAT, compiled['source']),
    )
    changed = list(dict.fromkeys(op.clip_id for op in ops))
    return {
        'status': 'ok', 'format': FORMAT, 'graph_revision': expected_revision + len(ops),
        'ops_appended': len(ops), 'changed_clip_ids': changed[:50], 'changed_clip_count': len(changed),
        'changed_clip_ids_truncated': len(changed) > 50,
        'compiled_hash': compiled['compiled_hash'],
    }
