"""Following graphics and regional masks, generated from editable motion source."""
from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from open_edit.ir.object_tracking import ObjectTrack, effect_box, sample_track
from open_edit.ir.types import Timeline
from open_edit.render.pipe_builder import OverlayClip
from open_edit.render.profiles import RenderProfile
from open_edit.storage.assets import AssetStore


def _materialize(root, track, effect, clip, asset, width, height, fps):
    duration = clip.out_point_sec - clip.in_point_sec
    key = hashlib.sha256(json.dumps({'version': 1, 'track': track.model_dump(mode='json', include={'frames'}),
        'label': track.label if effect.kind == 'label' and not effect.text else None,
        'effect': effect.model_dump(mode='json'), 'source_in': clip.in_point_sec, 'duration': duration,
        'size': [width, height], 'source_size': [asset.width, asset.height], 'fps': fps}, sort_keys=True).encode()).hexdigest()
    cache = root / '.open_edit/cache/tracked-effects'
    cache.mkdir(parents=True, exist_ok=True)
    output = cache / f'{key}.mkv'
    if output.is_file():
        return output
    mask = effect.kind in ('blur', 'pixelate')
    handle, pending = tempfile.mkstemp(suffix='.mkv', dir=cache)
    os.close(handle)
    process = None
    try:
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo',
                '-pix_fmt', 'gray' if mask else 'rgba', '-s', f'{width}x{height}', '-r', str(fps),
                '-i', '-', '-an', '-threads', '1', '-c:v', 'ffv1', '-pix_fmt', 'gray' if mask else 'bgra', pending],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors)
            fit = min(width / asset.width, height / asset.height)
            aw, ah = asset.width * fit, asset.height * fit
            ox, oy = (width - aw) / 2, (height - ah) / 2
            font = None
            if effect.kind == 'label':
                from open_edit.render.captions import font_path

                font = ImageFont.truetype(str(font_path(root, None)), max(10, round(effect.strength * effect.scale * height / 360)))
            for index in range(math.ceil(duration * fps - 1e-6)):
                image = Image.new('L' if mask else 'RGBA', (width, height))
                frame = sample_track(track, clip.in_point_sec + index / fps)
                if frame:
                    left, top, right, bottom = effect_box(frame, effect)
                    if right > left and bottom > top:
                        box = (round(ox + left * aw), round(oy + top * ah), round(ox + right * aw), round(oy + bottom * ah))
                        draw = ImageDraw.Draw(image)
                        if mask or effect.kind == 'cover':
                            draw.rectangle(box, fill=255 if mask else effect.color)
                        elif effect.kind == 'highlight':
                            draw.rectangle(box, outline=effect.color, width=max(1, round(effect.strength * height / 1080)))
                        elif effect.kind == 'label':
                            text = effect.text or track.label
                            bounds = draw.textbbox((box[0], box[1]), text, font=font)
                            draw.rectangle((bounds[0]-3, bounds[1]-3, bounds[2]+3, bounds[3]+3), fill='#000000cc')
                            draw.text((box[0], box[1]), text, font=font, fill=effect.color)
                process.stdin.write(image.tobytes())
            process.stdin.close()
            if process.wait(timeout=300):
                errors.seek(0)
                raise ValueError('Tracked effect encoding failed: ' + errors.read().decode(errors='replace')[-1000:])
        os.replace(pending, output)
    finally:
        if process and process.poll() is None:
            process.kill()
            process.wait()
        Path(pending).unlink(missing_ok=True)
    return output


def tracking_overlays(root: Path, timeline: Timeline, store: AssetStore, profile: RenderProfile) -> list[OverlayClip]:
    width, height = map(int, profile.scale.split('x')) if profile.scale else (profile.width, profile.height)
    fps = profile.frame_rate_num / profile.frame_rate_den
    output = []
    for object_id, value in timeline.object_tracks.items():
        track = ObjectTrack.model_validate(value)
        if not track.enabled or not any(e.enabled for e in track.effects):
            continue
        owner, clip = next(((t, c) for t in timeline.tracks for c in t.clips if c.clip_id == track.clip_id), (None, None))
        if clip is None or clip.hidden or owner.hidden or clip.asset_hash != track.asset_hash:
            continue
        if any(e.enabled and e.effect_type in ('affine', 'transform', 'crop', 'rotate', 'zoompan', 'speed', 'speed_ramp') for e in [*owner.effects, *clip.effects]):
            raise ValueError(f'Tracked object {track.label} needs an untransformed source. Disable it or bake changes and retrack.')
        start = max(clip.in_point_sec, track.frames[0].time_sec)
        end = min(clip.out_point_sec, track.frames[-1].time_sec)
        if end <= start:
            continue
        position = clip.position_sec + start - clip.in_point_sec
        visible = clip.model_copy(update={'in_point_sec': start, 'out_point_sec': end})
        asset = store.get(track.asset_hash)
        if asset is None or not asset.width or not asset.height:
            raise ValueError(f'Original source missing for tracked object {object_id}')
        for effect in track.effects:
            if not effect.enabled:
                continue
            media = _materialize(root, track, effect, visible, asset, width, height, fps)
            output.append(OverlayClip(position_sec=position, duration_sec=end-start,
                media_path=media, label=f'tracked:{object_id}:{effect.effect_id}',
                alpha=effect.kind not in ('blur', 'pixelate'), z_index=timeline.tracks.index(owner),
                region_effect=effect.kind if effect.kind in ('blur', 'pixelate') else None,
                region_strength=effect.strength, half_open=True))
    return output
