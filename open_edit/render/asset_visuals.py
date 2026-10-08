"""Bounded filmstrips and peak envelopes cached once per immutable CAS asset."""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path
from threading import Lock, Semaphore

from open_edit.storage.assets import AssetStore

_LOCKS = [Lock() for _ in range(32)]
SCHEMA = 1
_DECODERS = Semaphore(2)


def _run(command, *, timeout):
    with _DECODERS:
        result = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', *command],
                                capture_output=True, timeout=timeout)
    if result.returncode:
        raise ValueError('Cannot generate media visuals: ' + result.stderr.decode(errors='replace')[-1000:])
    return result.stdout.decode(errors='replace')


def asset_visuals(project_path: Path, asset_hash: str) -> dict:
    if not re.fullmatch(r'[a-f0-9]{64}', asset_hash):
        raise ValueError('Invalid asset hash')
    store = AssetStore(project_path / '.open_edit/assets')
    asset, source = store.get(asset_hash), store.path(asset_hash)
    if not asset or not source:
        raise FileNotFoundError('Project media is unavailable')
    cache = project_path / '.open_edit/cache/visuals' / asset_hash
    manifest = cache / 'visuals.json'
    with _LOCKS[int(asset_hash[:2],16) % len(_LOCKS)]:
        if manifest.is_file():
            try:
                data = json.loads(manifest.read_text())
                if data['schema'] == SCHEMA and all((cache / t['file']).is_file() for t in data['thumbnails']):
                    return data
            except (ValueError, KeyError):
                pass
        cache.mkdir(parents=True, exist_ok=True)
        duration = max(0, asset.duration_sec)
        if not math.isfinite(duration):
            raise ValueError('Media duration must be finite')
        data = {'schema': SCHEMA, 'asset_hash': asset_hash, 'duration_sec': duration,
                'thumbnails': [], 'waveform': {'peaks': [], 'step_sec': 0}}
        with tempfile.TemporaryDirectory(prefix='visuals-', dir=cache) as tmp:
            scratch = Path(tmp)
            if asset.type != 'audio':
                count = 1 if asset.type == 'image' else 6
                last = max(0, duration - 1 / (asset.fps or 30))
                for i in range(count):
                    time = last * i / max(1,count-1)
                    filename = f'thumb-{i}.jpg'
                    _run(['-ss',f'{time:.6f}','-i',str(source),'-frames:v','1',
                          '-vf','scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2',
                          '-q:v','4',str(scratch/filename)],timeout=30)
                    if not (scratch/filename).is_file():
                        raise ValueError('Media thumbnail is empty')
                    data['thumbnails'].append({'file':filename,'time_sec':time})
            if asset.has_audio and duration > 0:
                samples = max(1, math.ceil(duration * 8000 / 2048))
                text = _run(['-i',str(source),'-t',str(duration),'-vn','-af',
                    f'aformat=channel_layouts=mono,aresample=8000,asetnsamples=n={samples}:p=1,'
                    'astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.Peak_level:file=-',
                    '-f','null','-'],timeout=300)
                values = re.findall(r'lavfi\.astats\.Overall\.Peak_level=([^\r\n]+)',text)
                if len(values)>2050:
                    raise ValueError('Waveform exceeded its bounded envelope')
                peaks = []
                for value in values:
                    db = float(value)
                    peaks.append(min(1.0,10**(db/20)) if math.isfinite(db) else 0.0)
                data['waveform'] = {'peaks':peaks,'step_sec':samples/8000}
            for thumb in data['thumbnails']:
                os.replace(scratch/thumb['file'],cache/thumb['file'])
            pending = scratch/'visuals.json'
            pending.write_text(json.dumps(data,allow_nan=False),encoding='utf-8')
            os.replace(pending,manifest)
        return data
