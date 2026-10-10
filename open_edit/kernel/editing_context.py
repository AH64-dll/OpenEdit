"""Compact, explicitly paginated views for agents; original objects stay intact."""
from __future__ import annotations

import json
from copy import deepcopy

MAX_CONTEXT_BYTES = 32 * 1024


def build_context(timeline, objects, revision, focus, *, include_source, include_timeline, offset, limit, section=None):
    selected = set(focus['selected_ids'])
    notes = set(focus['annotation_ids'])
    document_id = focus['document_id']
    region = focus['region']
    anchor = region['playhead_sec'] if region else focus['playhead_sec']
    clips = [c for t in timeline.tracks for c in t.clips]
    tracked_clip_ids = {o['data']['clip_id'] for o in objects if o['kind'] == 'object_track' and o['object_id'] in selected}
    chosen = [c for c in clips if c.clip_id in selected or c.clip_id in tracked_clip_ids]
    region_clips = [c for t in timeline.tracks if t.kind == 'video' and not t.hidden
                    for c in t.clips if not c.hidden and
                    c.position_sec <= anchor < c.position_sec + c.out_point_sec - c.in_point_sec] if region else []
    documents = {c.document_id for c in [*chosen, *region_clips] if c.document_id}

    def clip_view(c):
        return {**c.model_dump(mode='json'),
                'source_time_sec': c.in_point_sec + anchor - c.position_sec if
                c.position_sec <= anchor < c.position_sec + c.out_point_sec - c.in_point_sec else None}

    def document_matches(o):
        return (o['object_id'] == document_id or o['object_id'] in selected or o['object_id'] in documents or
                any(e['id'] in selected for e in o['data'].get('elements', []) if
                    document_id is None or o['object_id'] == document_id) or
                (not selected and document_id is None and not region))

    def annotation_matches(o):
        d = o['data']
        if d.get('hidden'):
            return False
        if notes:
            return o['object_id'] in notes
        if document_id is not None and d.get('document_id') not in (None, document_id):
            return False
        if selected and d.get('target_ids') and not selected.intersection(d['target_ids']):
            return False
        return (d['scope'] == 'object' or (d['anchor_sec'] <= anchor < d['end_sec'] if d['scope'] == 'range'
                                         else abs(anchor - d['anchor_sec']) <= 1 / 60))

    groups = {
        'selected_ids': focus['selected_ids'], 'annotation_ids': focus['annotation_ids'],
        'selected_clips': [clip_view(c) for c in chosen],
        'region_clips': [clip_view(c) for c in region_clips],
        'object_tracks': [o for o in objects if o['kind'] == 'object_track' and
                          (o['object_id'] in selected or o['data']['clip_id'] in {c.clip_id for c in [*chosen, *region_clips]} or not selected)],
        'selected_tracks': [t.model_dump(mode='json', exclude={'clips'}) for t in timeline.tracks if
                            any(c.track_id == t.track_id for c in [*chosen, *region_clips])],
        'annotations': [o for o in objects if o['kind'] == 'annotation' and annotation_matches(o)],
        'documents': [o for o in objects if o['kind'] == 'document' and document_matches(o)],
        'captions': [o for o in objects if o['kind'] == 'caption' and
                     (o['object_id'] in selected or (not selected and o['data']['start_sec'] <= anchor < o['data']['end_sec']))],
        'styles': [o for o in objects if o['kind'] == 'style'],
        'fonts': [o for o in objects if o['kind'] == 'font'],
    }
    if section is not None:
        if not isinstance(section, str) or section not in groups:
            raise ValueError('Unknown editing context section')
        groups = {section: groups[section]}
    result = {'status': 'ok', 'graph_revision': revision, 'playhead_sec': focus['playhead_sec'],
              'document_id': document_id, 'region': region,
              'timeline': {'duration_sec': timeline.duration_sec, 'track_count': len(timeline.tracks),
                           'clip_count': len(clips), 'caption_count': len(timeline.captions),
                           'overlay_count': len(timeline.overlays), 'transition_count': len(timeline.visual_transitions)},
              'context_limits': {'offset': offset, 'limit': limit, 'section': section, 'max_bytes': MAX_CONTEXT_BYTES,
                                 'compact': not include_source and not include_timeline, 'collections': {},
                                 'omitted_fields': []},
              'detail_query': 'query_project(get_studio, {kind, object_id, include_source:true}) for complete objects; '
                              'get_editing_context({section, offset, limit}) pages one collection without competing for space; '
                              'include_source/include_timeline explicitly expand details. '
                              'Compact objects are summaries: fetch the original before replacing it.'}
    if region:
        result['region_instruction'] = ('Coordinates use canvas_width/height at region.playhead_sec. region_clips are visible '
                                       'candidates, not detected pixel objects. Keep referenced media and use timed editable changes.')
    omitted = result['context_limits']['omitted_fields']

    def record(path):
        if len(omitted) < 20:
            path = path[:128]
            while len(json.dumps(path)) > 192:
                path = path[:-1]
            omitted.append(path)
        else:
            result['context_limits']['additional_omissions'] = True

    def compact(value, path, depth=0):
        if isinstance(value, str) and len(value) > 1000:
            record(path)
            return value[:1000]
        if isinstance(value, (dict, list)) and depth >= 8:
            record(path)
            return {} if isinstance(value, dict) else []
        if isinstance(value, dict):
            if len(value) > 40:
                record(path)
            fields = {}
            for k, v in list(value.items())[:40]:
                if len(k) > 256:
                    record(f'{path}.[oversized key]')
                    continue
                fields[k] = compact(v, f'{path}.{k}', depth + 1)
            return fields
        if isinstance(value, list):
            if len(value) > limit:
                record(path)
            return [compact(v, f'{path}[{i}]', depth + 1) for i, v in enumerate(value[:limit])]
        return value

    # Leave headroom for pagination and omission metadata. Expansions are opt-in.
    remaining = MAX_CONTEXT_BYTES - 8192
    for name, entries in groups.items():
        page = []
        for entry in entries[offset:offset + limit]:
            value = deepcopy(entry)
            path = f'{name}.{value.get("object_id", value.get("clip_id", len(page)))}' if isinstance(value, dict) else name
            if name == 'documents' and not include_source:
                data = value['data']
                data.pop('source', None)
                data.pop('assets', None)
                elements = data.get('elements', [])
                data['element_count'] = len(elements)
                if selected:
                    by_id = {e['id']: e for e in elements}
                    wanted = selected.intersection(by_id)
                    if wanted:
                        for id in list(wanted):
                            parent = by_id[id].get('parent_id')
                            while parent and parent not in wanted:
                                wanted.add(parent)
                                parent = by_id.get(parent, {}).get('parent_id')
                        elements = [e for e in elements if e['id'] in wanted]
                data['elements'] = [{**e, 'source_ref': f'index.tsx:{e["id"]}'} for e in elements]
                record(f'{path}.data.source')
            if name == 'annotations' and not include_source:
                points = value['data']['points']
                value['data']['points_count'] = len(points)
                value['data']['bounds'] = {'left': min(p[0] for p in points), 'top': min(p[1] for p in points),
                                         'right': max(p[0] for p in points), 'bottom': max(p[1] for p in points)}
            if name == 'object_tracks' and not include_source:
                from open_edit.kernel.object_tracking import summarize_track

                clip = next((c for c in clips if c.clip_id == value['data']['clip_id']), None)
                available = clip is not None and clip.asset_hash == value['data']['asset_hash']
                source_time = clip.in_point_sec + anchor - clip.position_sec if available else None
                value['data'] = summarize_track(value['data'], source_time)
                value['data']['target_status'] = 'ready' if available else 'source_changed' if clip else 'clip_missing'
                record(f'{path}.data.frames')
            if not include_source:
                value = compact(value, path)
            # MCP's JSON serializer escapes Unicode; budget that larger wire form.
            size = len(json.dumps(value).encode('utf-8'))
            if not (include_source or include_timeline) and size > remaining:
                # Return the identity of an oversized first object, so callers can fetch it.
                if not page and isinstance(value, dict):
                    identity = {k: value[k] for k in ('kind', 'object_id', 'clip_id', 'revision') if k in value}
                    identity['details_omitted'] = True
                    identity_size = len(json.dumps(identity).encode('utf-8'))
                    if len(identity) > 1 and identity_size <= remaining:
                        page.append(identity)
                        remaining -= identity_size
                record(path)
                break
            page.append(value)
            remaining -= size
        result[name] = page
        end = offset + len(page)
        result['context_limits']['collections'][name] = {
            'total': len(entries), 'returned': len(page), 'section': name,
            'next_offset': end if end < len(entries) else None}
    if include_timeline:
        full = timeline.model_dump(mode='json', exclude={'graphics_documents'})
        # include_source asks for every field; otherwise list IDs/timing only.
        result['timeline'] = full if include_source else _timeline_index(full)
    return result


def _scalars(value: dict) -> dict:
    """Scalar fields of one object; nested lists/objects become ``<key>_count``."""
    out = {}
    for key, item in value.items():
        if isinstance(item, (list, dict)):
            if item:
                out[f'{key}_count'] = len(item)
        elif item is not None:
            out[key] = item
    return out


def _timeline_index(full: dict) -> dict:
    """Compact clip/track index: enough to address any clip without the full model."""
    index = _scalars({k: v for k, v in full.items() if k != 'tracks'})
    index['tracks'] = [{**_scalars({k: v for k, v in track.items() if k != 'clips'}),
                        'clips': [_scalars(clip) for clip in track.get('clips', [])]}
                       for track in full.get('tracks', [])]
    index['detail'] = 'compact index; pass include_source=true for every field'
    return index
