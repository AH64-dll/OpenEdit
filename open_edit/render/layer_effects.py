"""Checked, cached MLT passes for effects on upper video layers.

The main pipe composites these alpha-preserving layers in track order. Their
audio remains in the independent mix, so an upper clip never loses its sound.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from open_edit.ir.types import Timeline, Track
from open_edit.render.emitter import EmitterConfig, emit_timeline
from open_edit.render.profiles import RenderProfile


def materialize_layer(track: Track, duration: float, asset_paths: dict[str, str],
                      cache_dir: Path, profile: RenderProfile) -> Path:
    """Never publish a partial or unprobed cache file; keep project source intact."""
    from open_edit.storage.assets import _probe_media as probe_file

    melt = shutil.which('melt')
    if not melt:
        raise ValueError('MLT is required to check effects on video layers')
    if profile.scale:
        width, height = map(int, profile.scale.split('x'))
        profile = profile.model_copy(update={'width': width, 'height': height, 'scale': None})
    config = EmitterConfig(profile={k: getattr(profile, k) for k in
                                   ('width', 'height', 'frame_rate_num', 'frame_rate_den')})
    layer = track.model_copy(deep=True, update={'muted': True, 'hidden': False, 'solo': False})
    xml = emit_timeline(Timeline(tracks=[layer], duration_sec=duration), config, asset_paths)
    identity = hashlib.sha256((xml + '\nlayer-effects-v1').encode()).hexdigest()
    cache_dir.mkdir(parents=True, exist_ok=True)
    output = cache_dir / f'{identity}.mov'
    if output.is_file():
        info = probe_file(output)
        if info.get('width') == profile.width and info.get('height') == profile.height and info.get('duration_sec', 0) >= duration - 1 / (profile.frame_rate_num / profile.frame_rate_den):
            return output
        output.unlink()
    with tempfile.TemporaryDirectory(prefix='layer-', dir=cache_dir) as tmp:
        xml_path, rendered = Path(tmp) / 'layer.mlt', Path(tmp) / 'layer.mov'
        xml_path.write_text(xml, encoding='utf-8')
        env = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}
        result = subprocess.run([melt, str(xml_path), '-consumer', f'avformat:{rendered}',
                                 'f=mov', 'vcodec=qtrle', 'pix_fmt=argb', 'audio_off=1', 'real_time=-1',
                                 f's={profile.width}x{profile.height}',
                                 f'frame_rate_num={profile.frame_rate_num}', f'frame_rate_den={profile.frame_rate_den}'],
                                capture_output=True, timeout=max(60, min(3600, duration * 20)), env=env)
        if result.returncode or not rendered.is_file():
            raise ValueError('The video layer effect check failed: ' + result.stderr.decode(errors='replace')[-1500:])
        info = probe_file(rendered)
        if (info.get('width') != profile.width or info.get('height') != profile.height or
                info.get('duration_sec', 0) < duration - 1 / (profile.frame_rate_num / profile.frame_rate_den) or
                not info.get('has_alpha')):
            raise ValueError('The video layer effect check returned incomplete or opaque media')
        os.replace(rendered, output)
    return output
