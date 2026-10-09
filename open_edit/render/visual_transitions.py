"""Cached visual transitions retain the cut, clip trims, effects and track order.

The centered blend freezes the two boundary frames where the trimmed source has
no handles. Audio retains the original cut and its independently editable fades.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from open_edit.ir.types import Track, VisualTransition
from open_edit.render.layer_effects import materialize_layer
from open_edit.render.pipe_builder import OverlayClip
from open_edit.render.profiles import RenderProfile


def transition_overlay(spec: VisualTransition, paths: dict[str, str], cache: Path,
                       profile: RenderProfile) -> OverlayClip:
    if profile.scale:
        w, h = map(int, profile.scale.split('x'))
        profile = profile.model_copy(update={'width': w, 'height': h, 'scale': None})
    identity = hashlib.sha256(json.dumps({'spec': spec.model_dump(), 'paths': paths,
        'profile': profile.model_dump(), 'version': 1}, sort_keys=True).encode()).hexdigest()
    cache.mkdir(parents=True, exist_ok=True)
    output = cache / f'{identity}.mov'
    if not output.is_file():
        half = spec.duration_sec / 2
        layers = []
        for side, original in [('a', spec.clip_a), ('b', spec.clip_b)]:
            clip = original.model_copy(deep=True, update={'position_sec': 0, 'hidden': False})
            clip.effects = [e for e in clip.effects if not e.effect_type.startswith('transition_')]
            if side == 'a':
                clip.in_point_sec = clip.out_point_sec - half
            else:
                clip.out_point_sec = clip.in_point_sec + half
            layers.append(materialize_layer(Track(track_id=clip.track_id, kind='video', clips=[clip],
                effects=spec.track_effects), half, paths, cache / 'sources', profile))
        duration = spec.duration_sec
        fps = f'{profile.frame_rate_num}/{profile.frame_rate_den}'
        expression = f'if(lte(X,W*T/{duration}),B,A)' if spec.kind == 'wipe' else f'A*(1-min(1,T/{duration}))+B*min(1,T/{duration})'
        filters = (f'[0:v]trim=duration={half},setpts=PTS-STARTPTS,fps={fps},tpad=stop_mode=clone:stop_duration={half},format=gbrap[a];'
            f'[1:v]trim=duration={half},setpts=PTS-STARTPTS,fps={fps},tpad=start_mode=clone:start_duration={half},format=gbrap[b];'
            f"[a][b]blend=all_expr='{expression}':shortest=1,format=argb[out]")
        with tempfile.TemporaryDirectory(prefix='transition-', dir=cache) as tmp:
            rendered = Path(tmp) / 'transition.mov'
            result = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-filter_complex_threads', '1',
                '-i', str(layers[0]), '-i', str(layers[1]), '-filter_complex', filters, '-map', '[out]',
                '-an', '-t', str(duration), '-r', f'{profile.frame_rate_num}/{profile.frame_rate_den}',
                '-c:v', 'qtrle', '-pix_fmt', 'argb', str(rendered)], capture_output=True, timeout=120)
            if result.returncode:
                raise ValueError('Visual transition check failed: ' + result.stderr.decode(errors='replace')[-1500:])
            from open_edit.storage.assets import _probe_media

            info = _probe_media(rendered)
            if (info['width'], info['height']) != (profile.width, profile.height) or not info.get('has_alpha') or abs(info['duration_sec'] - duration) > 2 * profile.frame_rate_den / profile.frame_rate_num:
                raise ValueError(f'Visual transition returned incomplete media: {info}')
            subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(rendered), '-f', 'null', '-'], check=True, capture_output=True, timeout=120)
            os.replace(rendered, output)
    return OverlayClip(position_sec=spec.position_sec, duration_sec=spec.visible_duration_sec,
        media_path=output, label=spec.transition_id, alpha=True, in_point_sec=spec.in_point_sec, z_index=spec.z_index)
