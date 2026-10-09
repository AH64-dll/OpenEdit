"""Explicit, versioned CAS retiming; legacy speed effects retain their semantics."""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import tempfile
from pathlib import Path

from open_edit.storage.assets import AssetStore, _hash_file, _probe_media, list_assets_from_disk
from open_edit.storage.paths import ProjectPaths

TIMING_PROVIDER = 'openedit-timing-v1'


def timing_provenance(asset) -> dict | None:
    if asset.provider != TIMING_PROVIDER:
        return None
    try:
        data = json.loads(asset.attribution)
    except (ValueError, TypeError) as exc:
        raise ValueError('Retimed asset provenance is invalid') from exc
    if data.get('protocol') != 1 or not isinstance(data.get('segments'), list):
        raise ValueError('Unsupported retimed asset provenance')
    return data


def _atempo(rate: float) -> str:
    factors = []
    while rate < 0.5:
        factors.append(0.5)
        rate /= 0.5
    while rate > 2:
        factors.append(2.0)
        rate /= 2
    factors.append(rate)
    return ','.join(f'atempo={value:.12g}' for value in factors)


def bake_timing(project_path, *, asset_hash, source_in=0.0, source_out=None, playback_rate=1.0, segments=None, fps=30.0) -> dict:
    """Pitch-preserving constant rates or explicit piecewise-constant speed ramps.

    Segment boundaries are source seconds. The lossless output has normalized
    zero-based timestamps, a fixed frame rate and PCM audio; old IR isn't changed.
    """
    paths = ProjectPaths.for_project(project_path)
    assets = {a.asset_hash: a for a in list_assets_from_disk(paths.root)}
    asset = assets.get(asset_hash)
    if asset is None:
        raise ValueError('Timing source must be in the pinned project CAS')
    source = paths.assets_dir / asset_hash[:2] / asset_hash
    if not source.is_file() or _hash_file(source) != asset_hash:
        raise ValueError('Timing source CAS file is missing or corrupt')
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not math.isfinite(fps) or not 1 <= fps <= 60:
        raise ValueError('Timing fps must be finite and between 1 and 60')
    if segments is None:
        segments = [{'source_in': source_in, 'source_out': source_out, 'rate': playback_rate}]
    if not isinstance(segments, list) or not 1 <= len(segments) <= 32:
        raise ValueError('Timing requires 1..32 source segments')
    normalized, total = [], 0.0
    for segment in segments:
        if not isinstance(segment, dict) or segment.keys() != {'source_in', 'source_out', 'rate'}:
            raise ValueError('Each speed segment requires source_in, source_out and rate')
        start, end, rate = (segment[k] for k in ('source_in', 'source_out', 'rate'))
        if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in (start, end, rate)):
            raise ValueError('Speed segment values must be finite numbers')
        if not 0 <= start < end or not 0.125 <= rate <= 8:
            raise ValueError('Timing range must increase and rate must be 0.125..8')
        if asset.type != 'image' and (asset.duration_sec <= 0 or end > asset.duration_sec + 1e-6):
            raise ValueError('Timing source range exceeds source duration')
        total += (end - start) / rate
        normalized.append({'source_in': float(start), 'source_out': float(end), 'rate': float(rate)})
    if total > 60 or math.ceil(total * fps - 1e-8) > 1800:
        raise ValueError('Retimed output is limited to 60 seconds and 1800 frames')
    version = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=10).stdout.splitlines()[0]
    provenance = {'protocol': 1, 'asset_hash': asset_hash, 'source_type': asset.type,
                  'segments': normalized, 'fps': float(fps), 'duration_sec': total, 'ffmpeg': version}
    key = hashlib.sha256(json.dumps(provenance, sort_keys=True).encode()).hexdigest()
    cache = paths.root / '.open_edit/timing'
    cache.mkdir(parents=True, exist_ok=True)
    record_path = cache / f'{key}.json'
    if record_path.is_file():
        record = json.loads(record_path.read_text())
        output_hash = record['asset_hash']
        output = paths.assets_dir / output_hash[:2] / output_hash
        if output.is_file() and _hash_file(output) == output_hash:
            return {**record, 'cache_hit': True}
    has_video = asset.type in {'video', 'image'}
    has_audio = asset.type in {'video', 'audio'} and asset.has_audio
    if asset.type == 'audio':
        has_audio = True
    filters, inputs, labels = [], [], []
    for index, segment in enumerate(normalized):
        start, end, rate = (segment[k] for k in ('source_in', 'source_out', 'rate'))
        duration = (end - start) / rate
        if asset.type == 'image':
            inputs += ['-loop', '1', '-framerate', str(fps)]
        else:
            inputs += ['-ss', f'{start:.12g}']
        inputs += ['-t', f'{end - start:.12g}']
        inputs += ['-i', str(source)]
        if has_video:
            filters.append(f'[{index}:v]trim=duration={end - start:.12g},setpts=(PTS-STARTPTS)/{rate:.12g},fps={fps:.12g},'
                           f'tpad=stop_mode=clone:stop_duration={1 / fps:.12g},trim=duration={duration:.12g},format=bgra[v{index}]')
            labels.append(f'[v{index}]')
        if has_audio:
            filters.append(f'[{index}:a]atrim=duration={end - start:.12g},asetpts=PTS-STARTPTS,{_atempo(rate)},'
                           f'aresample=48000,apad,atrim=duration={duration:.12g}[a{index}]')
            labels.append(f'[a{index}]')
    filters.append(''.join(labels) + f'concat=n={len(normalized)}:v={int(has_video)}:a={int(has_audio)}' +
                   ('[v]' if has_video else '') + ('[a]' if has_audio else ''))
    with tempfile.TemporaryDirectory(prefix='retime-', dir=cache) as directory:
        # NUT preserves PCM sample timestamps; Matroska's millisecond timebase
        # can shift segment boundaries by a fraction of a millisecond.
        output = Path(directory) / ('timing.nut' if has_video else 'timing.wav')
        command = ['ffmpeg', '-y', '-v', 'error', *inputs, '-filter_complex', ';'.join(filters)]
        if has_video:
            command += ['-map', '[v]', '-c:v', 'ffv1', '-level', '3', '-pix_fmt', 'bgra']
        if has_audio:
            command += ['-map', '[a]', '-c:a', 'pcm_s16le']
        command += ['-t', f'{total:.12g}', str(output)]
        rendered = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120)
        if rendered.returncode:
            raise ValueError('Timing materialization failed: ' + rendered.stderr.decode(errors='replace')[-300:])
        info = _probe_media(str(output))
        if abs(info['duration_sec'] - total) > 1 / fps + 0.01 or info['has_audio'] != has_audio:
            raise ValueError('Timing QC failed: duration/audio parity mismatch')
        decoded = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(output), '-f', 'null', '-'],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60)
        if decoded.returncode:
            raise ValueError('Timing QC failed: output cannot be fully decoded')
        result = AssetStore(paths.assets_dir).ingest(str(output), transcribe=False, provider=TIMING_PROVIDER,
                                                   attribution=json.dumps(provenance, sort_keys=True), source_url=f'openedit:timing:{key}')
        record = {'status': 'ok', 'asset_hash': result.asset_hash, 'src': f'asset://{result.asset_hash}',
                  'duration_sec': total, 'content_key': key, 'qc_report': {'passed': True, 'complete': True,
                                                                          'audio': has_audio, 'fps': fps},
                  'provenance': provenance}
        temporary = record_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(record), encoding='utf-8')
        temporary.replace(record_path)
    return {**record, 'cache_hit': False}
