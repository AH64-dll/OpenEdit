"""Local, bounded object tracking and small agent edits over durable tracks."""
from __future__ import annotations

import math
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from open_edit.ir.object_tracking import ObjectTrack, Time, TrackedEffect, TrackFrame, sample_track
from open_edit.kernel.edit_graph_service import open_store
from open_edit.kernel.studio_service import EditingRegion, commit_studio
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import GraphRevisionConflict


class TrackingRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    expected_revision: StrictInt = Field(ge=0)
    clip_id: str = Field(min_length=1, max_length=128)
    region: EditingRegion
    start_sec: Time | None = None
    end_sec: Time | None = Field(default=None, gt=0)
    direction: Literal['forward', 'backward', 'both'] = 'both'
    target_mode: Literal['foreground', 'region'] = 'foreground'
    sample_fps: StrictInt = Field(default=15, ge=1, le=30)
    label: str = Field(default='Tracked object', min_length=1, max_length=256)
    object_id: str | None = Field(default=None, min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_.:-]+$')
    request_id: str | None = Field(default=None, min_length=1, max_length=128)


def prepare_tracking(root: Path, request: TrackingRequest):
    from open_edit.ir.derive import derive_timeline
    from open_edit.ir.types import Project

    store = open_store(root)
    revision, ops = store.read_snapshot()
    if revision != request.expected_revision:
        raise GraphRevisionConflict(request.expected_revision, revision)
    timeline = derive_timeline(Project(name='tracking', edit_graph=ops), strict=True)
    track, clip = next(((t, c) for t in timeline.tracks for c in t.clips if c.clip_id == request.clip_id), (None, None))
    if clip is None or clip.track_kind != 'video' or clip.document_id or clip.hidden or track.hidden:
        raise ValueError('Select a visible imported video clip to track')
    if clip.locked or track.locked:
        raise ValueError('Unlock the clip and track before tracking')
    # A source box cannot silently represent footage after a spatial transform.
    if any(e.enabled and e.effect_type in ('affine', 'transform', 'crop', 'rotate', 'zoompan', 'speed', 'speed_ramp') for e in [*track.effects, *clip.effects]):
        raise ValueError('Track an untransformed clip; bake speed or spatial changes to a new source first')
    assets = AssetStore(root / '.open_edit/assets')
    asset, path = assets.get(clip.asset_hash), assets.path(clip.asset_hash)
    if asset is None or path is None or asset.type != 'video' or not asset.width or not asset.height:
        raise ValueError('The original video asset is unavailable')
    anchor = request.region.playhead_sec
    end = clip.position_sec + clip.out_point_sec - clip.in_point_sec
    start = clip.position_sec if request.start_sec is None else request.start_sec
    stop = end if request.end_sec is None else request.end_sec
    if not clip.position_sec <= start <= anchor < stop <= end + 1e-6:
        raise ValueError('Tracking range and selected frame must lie inside the clip')
    if stop - start > 300:
        raise ValueError('Choose a tracking range of at most 300 seconds; long clips can use multiple tracks')
    r = request.region
    scale = min(r.canvas_width / asset.width, r.canvas_height / asset.height)
    ox, oy = (r.canvas_width - asset.width * scale) / 2, (r.canvas_height - asset.height * scale) / 2
    box = ((r.left - ox) / (asset.width * scale), (r.top - oy) / (asset.height * scale),
           (r.right - r.left) / (asset.width * scale), (r.bottom - r.top) / (asset.height * scale))
    initial = TrackFrame(time_sec=clip.in_point_sec + anchor - clip.position_sec,
                         x=box[0], y=box[1], width=box[2], height=box[3], manual=True)
    if min(initial.width * asset.width, initial.height * asset.height) < 8:
        raise ValueError('Select a target at least 8 source pixels wide and high, within the video image')
    before = None
    if request.object_id:
        before = next((o['data'] for o in store.studio_snapshot('object_track')['objects'] if o['object_id'] == request.object_id), None)
        if before is None or before['locked'] or before['clip_id'] != clip.clip_id or before['asset_hash'] != clip.asset_hash:
            raise ValueError('Choose an existing unlocked track belonging to this clip')
    return {'path': str(path), 'asset_hash': clip.asset_hash, 'clip_id': clip.clip_id,
            'width': asset.width, 'height': asset.height, 'initial': initial.model_dump(mode='json'),
            'start': clip.in_point_sec + start - clip.position_sec,
            'end': clip.in_point_sec + stop - clip.position_sec,
            'fps': min(request.sample_fps, asset.fps or 30), 'before': before}


def _decode(path, start, duration, fps, width, height):
    """Two-second blocks bound memory and make decode cancellation responsive."""
    import numpy as np

    result = subprocess.run(['ffmpeg', '-v', 'error', '-threads', '1', '-ss', str(max(0, start)),
        '-i', str(path), '-t', str(duration), '-an', '-vf', f'fps={fps},scale={width}:{height}',
        '-threads', '1', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'], capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError('Video decoding failed: ' + result.stderr.decode(errors='replace')[-1000:])
    size = width * height * 3
    if not result.stdout or len(result.stdout) % size:
        raise ValueError('Video decoder returned incomplete frames')
    return np.frombuffer(result.stdout, dtype=np.uint8).reshape((-1, height, width, 3))


def track_video(prepared: dict, request: TrackingRequest, *, cancelled=lambda: False, progress=lambda _: None) -> ObjectTrack:
    """CSRT finds target features locally. Loss is explicit, never extrapolated."""
    import cv2
    import numpy as np

    if cancelled():
        raise InterruptedError('Tracking cancelled')
    factor = min(1, 960 / prepared['width'], 540 / prepared['height'])
    width, height = max(16, round(prepared['width'] * factor)), max(16, round(prepared['height'] * factor))
    fps = prepared['fps']
    initial = TrackFrame.model_validate(prepared['initial'])
    anchor = initial.time_sec
    seed = _decode(prepared['path'], anchor, 1 / fps + .01, fps, width, height)[0]
    bbox = tuple(round(v) for v in (initial.x * width, initial.y * height, initial.width * width, initial.height * height))
    bbox = (bbox[0], bbox[1], min(bbox[2], width - bbox[0]), min(bbox[3], height - bbox[1]))
    if min(bbox[2:]) < 4:
        raise ValueError('The selected target is too small at tracking resolution')
    refined = False
    if request.target_mode == 'foreground':
        # Identify a foreground component inside the user's seed, then track
        # its appearance. This is visual identification, not a semantic label.
        mask = np.zeros((height, width), np.uint8)
        try:
            cv2.grabCut(seed, mask, bbox, np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64), 3, cv2.GC_INIT_WITH_RECT)
            foreground = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
            count, _, stats, centers = cv2.connectedComponentsWithStats(foreground)
            candidates = [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= bbox[2]*bbox[3]*.08]
            if candidates:
                center = (bbox[0]+bbox[2]/2, bbox[1]+bbox[3]/2)
                component = min(candidates, key=lambda i: (centers[i][0]-center[0])**2 + (centers[i][1]-center[1])**2)
                x, y, w, h = map(int, stats[component, :4])
                if min(w, h) >= 4:
                    bbox = (x, y, w, h)
                    initial = initial.model_copy(update={'x': x/width, 'y': y/height, 'width': w/width, 'height': h/height})
                    refined = True
        except cv2.error:
            pass  # Uniform/full-image seeds retain the explicitly selected region.
    seed_patch = cv2.resize(seed[bbox[1]:bbox[1] + bbox[3], bbox[0]:bbox[0] + bbox[2]], (32, 32))
    frames = [initial]
    total = max(1, math.ceil((prepared['end'] - prepared['start']) * fps))
    done = 0
    for direction in (1, -1):
        if (direction == 1 and request.direction == 'backward') or (direction == -1 and request.direction == 'forward'):
            continue
        params = cv2.TrackerCSRT_Params()
        params.psr_threshold = .06
        tracker = cv2.TrackerCSRT_create(params)
        tracker.init(seed, bbox)
        cursor = anchor + 1 / fps if direction == 1 else anchor
        last = initial
        lost = False
        while cursor < prepared['end'] - 1e-6 if direction == 1 else cursor > prepared['start'] + 1e-6:
            if cancelled():
                raise InterruptedError('Tracking cancelled')
            block_start = cursor if direction == 1 else max(prepared['start'], cursor - 2)
            block_end = min(prepared['end'], cursor + 2) if direction == 1 else cursor
            block = _decode(prepared['path'], block_start, block_end - block_start, fps, width, height)
            indices = range(len(block)) if direction == 1 else range(len(block) - 1, -1, -1)
            for i in indices:
                if cancelled():
                    raise InterruptedError('Tracking cancelled')
                t = block_start + i / fps
                if t >= prepared['end'] or abs(t - anchor) < 1e-6:
                    continue
                ok, rect = tracker.update(block[i]) if not lost else (False, bbox)
                confidence = 0.
                if ok:
                    x, y, w, h = map(int, rect)
                    x, y = max(0, x), max(0, y)
                    w, h = min(w, width - x), min(h, height - y)
                    ok = w >= 4 and h >= 4
                    if ok:
                        patch = cv2.resize(block[i, y:y+h, x:x+w], (32, 32))
                        # Appearance score is a diagnostic, not a probability.
                        error = float(np.mean(np.abs(patch.astype(np.float32) - seed_patch.astype(np.float32)))) / 255
                        confidence = max(0., 1 - error * 2)
                        ok = confidence >= .35
                if ok:
                    last = TrackFrame(time_sec=t, x=x/width, y=y/height, width=w/width, height=h/height, confidence=confidence)
                else:
                    lost = True
                    last = last.model_copy(update={'time_sec': t, 'valid': False, 'confidence': 0., 'manual': False})
                frames.append(last)
                done += 1
                progress(min(.99, done / total))
            cursor = block_end if direction == 1 else block_start
    unique = {round(f.time_sec, 6): f for f in frames}
    ordered = [unique[t] for t in sorted(unique)]
    # Preserve the final frame's visibility until the requested exclusive end.
    if request.direction != 'backward' and ordered[-1].time_sec < prepared['end']:
        ordered.append(ordered[-1].model_copy(update={'time_sec': prepared['end'], 'manual': False}))
    before = prepared['before']
    if before:
        kept = [TrackFrame.model_validate(f) for f in before['frames'] if f['time_sec'] < ordered[0].time_sec or f['time_sec'] > ordered[-1].time_sec]
        ordered = sorted([*kept, *ordered], key=lambda f: f.time_sec)
    return ObjectTrack(clip_id=prepared['clip_id'], asset_hash=prepared['asset_hash'], label=request.label,
        algorithm=f'OpenCV {cv2.__version__} {"GrabCut foreground + " if refined else "selected region + "}CSRT; appearance score', frames=ordered,
        effects=before['effects'] if before else [])


def summarize_track(data: dict, source_time: float | None = None) -> dict:
    track = ObjectTrack.model_validate(data)
    frames = track.frames
    sampled = [frames[i].model_dump(mode='json') for i in sorted({0, len(frames)//2, len(frames)-1})]
    current = sample_track(track, source_time) if source_time is not None else None
    lost_ranges, lost_start = [], None
    for frame in frames:
        if not frame.valid and lost_start is None:
            lost_start = frame.time_sec
        elif frame.valid and lost_start is not None:
            lost_ranges.append([lost_start, frame.time_sec])
            lost_start = None
    if lost_start is not None:
        lost_ranges.append([lost_start, frames[-1].time_sec])
    return track.model_dump(mode='json', exclude={'frames'}) | {
        'frame_count': len(frames), 'source_range': [frames[0].time_sec, frames[-1].time_sec],
        'lost_frame_count': sum(not f.valid for f in frames), 'sample_frames': sampled,
        'lost_ranges': lost_ranges[:10], 'lost_range_count': len(lost_ranges),
        'current_frame': current.model_dump(mode='json') if current else None}


def edit_object_track(root: str | Path, *, expected_revision: int, object_id: str, edits: list[dict],
                      author='ai', request_id=None, label='Edit tracked object'):
    """Small edits retain all motion samples and share locks, Undo and revisions."""
    from copy import deepcopy

    snapshot = open_store(Path(root)).studio_snapshot('object_track')
    if snapshot['graph_revision'] != expected_revision:
        raise GraphRevisionConflict(expected_revision, snapshot['graph_revision'])
    data = next((deepcopy(o['data']) for o in snapshot['objects'] if o['object_id'] == object_id), None)
    if data is None:
        raise ValueError('Object track not found')
    if not isinstance(edits, list) or not 1 <= len(edits) <= 100:
        raise ValueError('Provide 1 to 100 track edits')
    for edit in edits:
        if not isinstance(edit, dict):
            raise ValueError('Track edits must be objects')
        action = edit.get('action')
        if action == 'properties' and set(edit) <= {'action', 'values'}:
            if not isinstance(edit.get('values'), dict) or edit['values'].keys() - {'label', 'locked', 'enabled'}:
                raise ValueError('Track properties support label, locked and enabled')
            data.update(edit['values'])
        elif action == 'set_frame' and set(edit) == {'action', 'frame'}:
            if not isinstance(edit['frame'], dict):
                raise ValueError('A frame must be an object')
            frame = TrackFrame.model_validate({**edit['frame'], 'manual': True}).model_dump(mode='json')
            data['frames'] = sorted([f for f in data['frames'] if abs(f['time_sec'] - frame['time_sec']) > 1e-6] + [frame], key=lambda f: f['time_sec'])
        elif action == 'remove_frame' and set(edit) == {'action', 'time_sec'}:
            if type(edit['time_sec']) not in (int, float) or not math.isfinite(edit['time_sec']) or edit['time_sec'] < 0:
                raise ValueError('Frame time must be a finite nonnegative source time')
            data['frames'] = [f for f in data['frames'] if abs(f['time_sec'] - edit['time_sec']) > 1e-6]
        elif action == 'add_effect' and set(edit) == {'action', 'effect'}:
            data['effects'].append(TrackedEffect.model_validate(edit['effect']).model_dump(mode='json'))
        elif action in ('update_effect', 'remove_effect'):
            allowed = {'action', 'effect_id', 'values'} if action == 'update_effect' else {'action', 'effect_id'}
            if set(edit) != allowed:
                raise ValueError('Unsupported tracked effect edit fields')
            effect = next((e for e in data['effects'] if e['effect_id'] == edit['effect_id']), None)
            if effect is None:
                raise ValueError('Tracked effect not found')
            if action == 'remove_effect':
                data['effects'].remove(effect)
            else:
                if not isinstance(edit['values'], dict) or 'effect_id' in edit['values']:
                    raise ValueError('Retain the stable effect ID')
                effect.update(edit['values'])
        else:
            raise ValueError('Unsupported object track edit action')
    return commit_studio(root, expected_revision=expected_revision,
        changes=[{'kind': 'object_track', 'object_id': object_id, 'data': data}],
        author=author, request_id=request_id, label=label)
