"""Optional graphics materialization. Only checked, complete CAS outputs enter IR."""
from __future__ import annotations

import contextlib
import functools
import hashlib
import json
import math
import mimetypes
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from open_edit.ir.types import AddClipOp, ReplaceClipSourceOp, TrimClipOp
from open_edit.storage.assets import AssetStore, _hash_file, _probe_media, list_assets_from_disk
from open_edit.storage.edit_graph import GraphRevisionConflict
from open_edit.storage.paths import ProjectPaths

UPSTREAM = 'fefcde9df7198466bd7cc9f3a9d7eae1575b5b12'
GRAPHICS_FORMAT = 'diffusion-graphics-v1'
MAX_FRAMES = 1800
# HTTP source rewrites may run concurrently; cleanup belongs to its own thread.
_ACTIVE = threading.local()


def browser_directory() -> Path:
    return Path(os.environ.get('OPEN_EDIT_DIFFUSION_BROWSER_DIR') or Path(__file__).with_name('browser')).resolve()


def graphics_ready() -> bool:
    directory = browser_directory()
    if not (shutil.which('node') and (directory / 'node_modules/playwright-core').is_dir()):
        return False
    # The pinned runtime needs the upstream koota Or-across-generations fix
    # (browser/patches/koota+0.6.6.patch). An npm ci that skipped it leaves a
    # worker that renders empty frames, so 'ready' requires the marker.
    dist = directory / 'node_modules/koota/dist'
    return dist.is_dir() and any(
        'staticOrMatched' in path.read_text(errors='replace')
        for path in dist.glob('*.js') if path.stat().st_size < 8 * 1024 * 1024)


def validate_params(params: dict) -> dict:
    if not isinstance(params, dict) or params.keys() - {'source', 'duration_sec', 'fps'}:
        raise ValueError('Graphics requires source, duration_sec and optional fps')
    source = params.get('source')
    if not isinstance(source, str) or not source.strip() or len(source.encode()) > 512 * 1024:
        raise ValueError('Graphics source must be nonempty and at most 512 KiB')
    duration = params.get('duration_sec', 3.0)
    fps = params.get('fps', 30)
    if isinstance(duration, bool) or not isinstance(duration, (float, int)) or not math.isfinite(duration) or not 0 < duration <= 60:
        raise ValueError('Graphics duration_sec must be between 0 and 60')
    if type(fps) is not int or not 1 <= fps <= 60 or math.ceil(duration * fps - 1e-8) > MAX_FRAMES:
        raise ValueError('Graphics fps must be 1..60 with at most 1800 frames')
    frames = math.ceil(duration * fps - 1e-8)
    return {'source': source, 'duration_sec': frames / fps, 'fps': fps}


def stop_worker() -> None:
    """Also called by the standalone worker's SIGTERM handler."""
    proc = getattr(_ACTIVE, 'process', None)
    if proc is None or proc.poll() is not None:
        # A reaped PID no longer identifies our process group. Normal worker
        # completion already closes Chromium; signalling that PID afterwards
        # can target a reused group or raise EPERM on macOS.
        return
    if os.name == 'posix':
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
    elif proc.poll() is None:
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        proc.kill()


def _worker(request: dict, scratch: Path, *, timeout: int = 180) -> dict:
    if not graphics_ready():
        raise ValueError('Graphics worker missing. Run python -m open_edit.integrations.diffusion.setup --graphics --chromium')
    request_path = scratch / 'request.json'
    request_path.write_text(json.dumps({**request, 'scratch': str(scratch)}), encoding='utf-8')
    with tempfile.TemporaryFile() as output:
        _ACTIVE.process = subprocess.Popen([shutil.which('node'), str(browser_directory() / 'render.cjs'), str(request_path)],
                                   stdout=output, stderr=subprocess.DEVNULL, start_new_session=os.name == 'posix')
        proc = _ACTIVE.process
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise ValueError('Graphics worker timed out; last good preview retained') from exc
        finally:
            stop_worker()
            proc.wait()
            _ACTIVE.process = None
        output.seek(0)
        raw = output.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError('Graphics worker response exceeds 8 MiB')
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise ValueError('Graphics worker exited without a valid response') from exc
        if not isinstance(result, dict) or not result.get('ok') or proc.returncode:
            raise ValueError(str(result.get('error', 'Graphics worker failed'))[:500] if isinstance(result, dict) else 'Graphics worker failed')
        return result


def inspect_source(source: str) -> dict:
    with tempfile.TemporaryDirectory(prefix='openedit-graphics-') as directory:
        return _worker({'source': source, 'validate_only': True}, Path(directory), timeout=20)['document']


@functools.lru_cache(maxsize=1)
def editor_bundle() -> bytes:
    """Build the fixed trusted editor host, independently of project source."""
    if not graphics_ready():
        raise ValueError('Install the optional graphics compiler to use the live canvas')
    result = subprocess.run([shutil.which('node'), str(browser_directory() / 'bundle-editor.cjs')],
                            capture_output=True, timeout=30)
    if result.returncode or not result.stdout or len(result.stdout) > 8 * 1024 * 1024:
        raise ValueError('The interactive graphics runtime could not be built')
    return result.stdout


def compile_editor(project_path, *, source: str, expected_revision: int, edits: list | None = None) -> dict:
    """Return only code produced by the literal compiler; never evaluate caller JS."""
    from open_edit.kernel.edit_graph_service import open_store

    store = open_store(Path(project_path))
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError('expected_revision must be a nonnegative integer')
    actual = store.graph_revision()
    if actual != expected_revision:
        raise GraphRevisionConflict(expected_revision, actual)
    validate_params({'source': source})
    with tempfile.TemporaryDirectory(prefix='openedit-editor-') as directory:
        result = _worker({'source': source, 'edits': edits or [], 'validate_only': True,
                          'include_code': True}, Path(directory), timeout=20)
    assets = graphics_asset_manifest(project_path, result['document']['assets'])
    # A stale compilation cannot authorize a subsequent visual edit.
    store.append_many([], expected_revision=expected_revision)
    return {'status': 'ok', 'graph_revision': expected_revision, 'source': result['source'],
            'code': result['code'], **result['document'],
            'asset_manifest': [{k: v for k, v in asset.items() if k != 'file'} for asset in assets]}


def _encode(command: list[str], *, timeout: int, scratch: Path | None = None) -> subprocess.CompletedProcess:
    """Track FFmpeg like Chromium so cancellation also reaches a separate session."""
    with tempfile.TemporaryFile() as errors:
        proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=errors,
                                start_new_session=os.name == 'posix')
        _ACTIVE.process = proc
        try:
            if scratch is not None:
                record = scratch / 'encoder-process.json'
                record.write_text(json.dumps({'encoder': proc.pid}))
            proc.wait(timeout=timeout)
        finally:
            stop_worker()
            proc.wait()
            _ACTIVE.process = None
        errors.seek(0, os.SEEK_END)
        errors.seek(max(0, errors.tell() - 300))
        return subprocess.CompletedProcess(command, proc.returncode, stderr=errors.read())


def rewrite_graphics_source(project_path, *, source, edits, expected_revision) -> dict:
    from open_edit.integrations.diffusion.authoring import _snapshot

    store, revision, _, _ = _snapshot(project_path)
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError('expected_revision must be a nonnegative integer')
    if revision != expected_revision:
        raise GraphRevisionConflict(expected_revision, revision)
    with tempfile.TemporaryDirectory(prefix='openedit-graphics-edit-') as directory:
        result = _worker({'source': source, 'edits': edits, 'validate_only': True}, Path(directory), timeout=20)
    # A concurrent graph write during source rewriting must also fail.
    store.append_many([], expected_revision=expected_revision)
    return {'status': 'ok', 'graph_revision': revision, 'source': result['source'], **result['document']}


def _runtime_digest() -> str:
    digest = hashlib.sha256()
    root = browser_directory()
    for path in sorted(root.rglob('*')):
        if path.is_file() and 'node_modules' not in path.parts:
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
    registry = root / 'node_modules/playwright-core/browsers.json'
    if registry.is_file():
        digest.update(registry.read_bytes())
    custom_browser = os.environ.get('OPEN_EDIT_CHROMIUM')
    if custom_browser:
        version = subprocess.run([custom_browser, '--version'], capture_output=True, timeout=10, check=True)
        digest.update(custom_browser.encode())
        digest.update(version.stdout)
    return digest.hexdigest()


def _sweep_stale_captures(cache: Path, max_age_sec: float = 3600) -> None:
    """Remove scratch directories left behind by earlier locked cleanups."""
    cutoff = time.time() - max_age_sec
    for stale in cache.glob('capture-*'):
        with contextlib.suppress(OSError):
            if stale.is_dir() and stale.stat().st_mtime < cutoff:
                shutil.rmtree(stale, ignore_errors=True)


def _publish_last_good(cache: Path, key: str) -> None:
    temporary = cache / 'last-good.tmp'
    temporary.write_text(json.dumps({'content_key': key}))
    temporary.replace(cache / 'last-good.json')


def _quality_check(path: Path, *, width: int, height: int, duration: float, fps: int) -> dict:
    info = _probe_media(str(path))
    if info['type'] != 'video' or (info['width'], info['height']) != (width, height) or not info['has_alpha'] or info['has_audio']:
        raise ValueError('Graphics QC failed: expected silent RGBA video with the scene dimensions')
    if abs(info['duration_sec'] - duration) > 1 / fps + 1e-6:
        raise ValueError('Graphics QC failed: output duration differs from requested frames')
    check = _encode(['ffmpeg', '-v', 'error', '-i', str(path), '-f', 'null', '-'], timeout=60)
    if check.returncode:
        raise ValueError('Graphics QC failed: output cannot be fully decoded')
    return {'passed': True, 'complete': True, 'alpha': True, 'audio': 'silent', 'width': width, 'height': height,
            'duration_sec': info['duration_sec'], 'fps': fps}


def graphics_asset_manifest(project_path: str | Path, hashes: list[str]) -> list[dict]:
    """Use identical image validation for the interactive host and export."""
    paths = ProjectPaths.for_project(project_path)
    assets = {a.asset_hash: a for a in list_assets_from_disk(paths.root)}
    manifest = []
    total_bytes, total_pixels = 0, 0
    for hash_ in hashes:
        asset = assets.get(hash_)
        if asset is None or asset.type != 'image':
            raise ValueError('Graphics image must reference an image in the pinned project CAS')
        cas_path = paths.assets_dir / hash_[:2] / hash_
        size = cas_path.stat().st_size if cas_path.is_file() else 0
        if not size or size > 32 * 1024 * 1024 or _hash_file(cas_path) != hash_:
            raise ValueError('Graphics CAS asset is missing, too large, or has a content hash mismatch')
        if not (asset.width and asset.height):
            raise ValueError('Graphics CAS image lacks probed pixel dimensions')
        total_bytes += size
        total_pixels += asset.width * asset.height
        if total_bytes > 64 * 1024 * 1024 or total_pixels > 32_000_000 or len(manifest) >= 64:
            raise ValueError('Graphics assets exceed the 64 MiB, 32 megapixel or 64 image budget')
        manifest.append({'id': hash_, 'type': 'IMAGE', 'path': hash_, 'source': hash_, 'createdAt': '',
                         'mimeType': mimetypes.guess_type(asset.original_path)[0] or 'image/png',
                         'width': asset.width, 'height': asset.height, 'file': str(cas_path)})
    return manifest


def materialize(project_path: str | Path, params: dict) -> dict:
    """Render without mutating the graph; cache keys include source, assets and runtime."""
    params = validate_params(params)
    paths = ProjectPaths.for_project(project_path)
    document = inspect_source(params['source'])
    manifest = graphics_asset_manifest(project_path, document['assets'])
    version = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=10).stdout.splitlines()[0]
    key = hashlib.sha256(json.dumps({'protocol': 1, **params, 'runtime': _runtime_digest(),
                                    'assets': document['assets'], 'ffmpeg': version}, sort_keys=True).encode()).hexdigest()
    cache = paths.root / '.open_edit/graphics'
    cache.mkdir(parents=True, exist_ok=True)
    record_path = cache / f'{key}.json'
    if record_path.is_file():
        record = json.loads(record_path.read_text())
        # Projects can move. Preview paths always resolve in this project.
        record['poster_path'] = str(cache / f'{key}.png')
        record['preview_path'] = str(cache / f'{key}.webm')
        hash_ = record['asset_hash']
        cas_path = paths.assets_dir / hash_[:2] / hash_
        if (cas_path.is_file() and _hash_file(cas_path) == hash_ and
                Path(record.get('poster_path', '')).is_file() and Path(record.get('preview_path', '')).is_file()):
            _publish_last_good(cache, key)
            return {**record, 'ok': True, 'cache_hit': True, 'output_path': str(cas_path)}
    _sweep_stale_captures(cache)
    # On Windows a reaped Chromium can hold its profile LOG open briefly; a
    # locked scratch file must not fail a render that already succeeded.
    with tempfile.TemporaryDirectory(prefix='capture-', dir=cache, ignore_cleanup_errors=True) as directory:
        scratch = Path(directory)
        rendered = _worker({**params, 'assets': manifest, 'frames': round(params['duration_sec'] * params['fps'])}, scratch)
        output = scratch / 'graphics.mov'
        ffmpeg = _encode(['ffmpeg', '-y', '-v', 'error', '-framerate', str(params['fps']),
                                 '-i', str(scratch / 'frame-%06d.png'), '-an', '-c:v', 'qtrle',
                         '-pix_fmt', 'argb', str(output)], timeout=90, scratch=scratch)
        if ffmpeg.returncode:
            raise ValueError('Graphics encoding failed: ' + ffmpeg.stderr.decode(errors='replace')[-300:])
        scene = document['scene']
        qc = _quality_check(output, width=scene['width'], height=scene['height'],
                            duration=params['duration_sec'], fps=params['fps'])
        asset = AssetStore(paths.assets_dir).ingest(str(output), transcribe=False, provider='diffusion',
                                                  attribution=f'OpenEdit graphics; Diffusion {UPSTREAM}; content key {key}',
                                                  source_url=f'openedit:graphics:{key}')
        preview = cache / f'{key}.webm'
        preview_temp = scratch / 'preview.webm'
        encoded = _encode(['ffmpeg', '-y', '-v', 'error', '-i', str(output), '-an',
                                  '-c:v', 'libvpx-vp9', '-b:v', '1M', '-deadline', 'realtime',
                                  '-cpu-used', '6', '-pix_fmt', 'yuva420p', str(preview_temp)],
                          timeout=90, scratch=scratch)
        if encoded.returncode:
            raise ValueError('Browser preview encoding failed; last good preview retained')
        preview_temp.replace(preview)
        poster = cache / f'{key}.png'
        shutil.copyfile(scratch / 'frame-000000.png', poster)
        record = {'asset_hash': asset.asset_hash, 'content_key': key, 'duration_sec': params['duration_sec'],
                  'fps': params['fps'], 'scene': scene, 'elements': document['elements'][:500],
                  'upstream': UPSTREAM, 'browser_version': rendered['browser_version'], 'qc_report': qc,
                  'source': params['source'], 'poster_path': str(poster)}
        record['preview_path'] = str(preview)
        temporary = record_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(record), encoding='utf-8')
        temporary.replace(record_path)
        # This pointer changes only after complete output, QC and CAS ingestion.
        _publish_last_good(cache, key)
    return {**record, 'ok': True, 'cache_hit': False, 'output_path': asset.stored_path}


def commit_graphics(project_path, *, job_id, expected_revision, clip_id='graphics', track_id='graphics', position_sec=0.0, author='ai') -> dict:
    from open_edit.integrations.diffusion.authoring import _snapshot
    from open_edit.kernel.render_jobs import DEFAULT_RENDER_JOB_SERVICE

    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError('expected_revision must be a nonnegative integer')
    if not all(isinstance(v, str) and 0 < len(v) <= 128 for v in (clip_id, track_id, job_id)):
        raise ValueError('job_id, clip_id and track_id must be bounded nonempty strings')
    if isinstance(position_sec, bool) or not isinstance(position_sec, (float, int)) or not math.isfinite(position_sec) or position_sec < 0:
        raise ValueError('position_sec must be a nonnegative finite number')
    store, revision, timeline, assets = _snapshot(project_path)
    if expected_revision != revision:
        raise GraphRevisionConflict(expected_revision, revision)
    job = DEFAULT_RENDER_JOB_SERVICE.get(Path(project_path), job_id)
    if job is None or job.mode != 'graphics' or job.status != 'succeeded' or job.graph_revision != expected_revision:
        raise ValueError('Use a succeeded graphics job rendered at the current expected_revision')
    result = job.result or {}
    if not result.get('qc_report', {}).get('passed') or not result.get('content_key'):
        raise ValueError('Graphics output has no passing quality check')
    asset = assets.get(result.get('asset_hash'))
    paths = ProjectPaths.for_project(project_path)
    if asset is None or _hash_file(paths.assets_dir / asset.asset_hash[:2] / asset.asset_hash) != asset.asset_hash:
        raise ValueError('Graphics CAS output is missing or corrupt')
    existing = next((c for t in timeline.tracks for c in t.clips if c.clip_id == clip_id), None)
    duration = result['duration_sec']
    if existing:
        if existing.asset_hash not in assets or assets[existing.asset_hash].provider != 'diffusion':
            raise ValueError('Cannot replace a non-graphics clip through the graphics adapter')
        old_asset = assets[existing.asset_hash]
        full_window = existing.in_point_sec == 0 and abs(existing.out_point_sec - old_asset.duration_sec) <= 1 / (old_asset.fps or 30) + 1e-6
        new_in, new_out = (0.0, duration) if full_window else (existing.in_point_sec, existing.out_point_sec)
        if new_out > duration + 1e-6:
            raise ValueError('New graphics is shorter than the existing trim; adjust the trim explicitly first')
        track = next(t for t in timeline.tracks if t.track_id == existing.track_id)
        if any(c.clip_id != clip_id and existing.position_sec < c.position_sec + c.out_point_sec - c.in_point_sec and
               existing.position_sec + new_out - new_in > c.position_sec for c in track.clips):
            raise ValueError('Updated graphics would overlap another clip on the same track')
        ops = []
        if existing.asset_hash != asset.asset_hash:
            ops.append(ReplaceClipSourceOp(author=author, clip_id=clip_id, new_asset_hash=asset.asset_hash))
        if existing.in_point_sec != new_in or existing.out_point_sec != new_out:
            ops.append(TrimClipOp(author=author, clip_id=clip_id, new_in_point_sec=new_in, new_out_point_sec=new_out))
    else:
        track = next((t for t in timeline.tracks if t.track_id == track_id), None)
        if track is not None and track.kind != 'video':
            raise ValueError('Graphics needs a video track')
        if track and any(position_sec < c.position_sec + c.out_point_sec - c.in_point_sec and position_sec + duration > c.position_sec for c in track.clips):
            raise ValueError('Graphics clips cannot overlap on the same track')
        ops = [AddClipOp(author=author, clip_id=clip_id, track_id=track_id, track_kind='video', asset_hash=asset.asset_hash,
                         position_sec=position_sec, in_point_sec=0, out_point_sec=duration)]
    store.append_many(ops, expected_revision=expected_revision,
                      authoring_view=(f'{GRAPHICS_FORMAT}:{clip_id}', result['source']))
    return {'status': 'ok', 'graph_revision': store.graph_revision(), 'clip_id': clip_id, 'asset_hash': asset.asset_hash,
            'content_key': result['content_key']}


DEFAULT_SOURCE = '''export default function Graphics() {
  return <stage id="graphics-stage">
    <scene id="graphics-scene" width={960} height={540} active>
      <rect id="panel" x={60} y={320} width={840} height={160} fill="#15354d" cornerRadius={20} end={3} />
      <text id="title" x={100} y={360} width={760} height={80} fontFamily="OpenEdit Sans" fontSize={48} color="#ffffff" end={3}>Your title</text>
    </scene>
  </stage>;
}
'''


def get_graphics_view(project_path, *, clip_id='graphics', include_source=False) -> dict:
    from open_edit.integrations.diffusion.authoring import _snapshot
    from open_edit.kernel.render_jobs import DEFAULT_RENDER_JOB_SERVICE

    if type(include_source) is not bool or not isinstance(clip_id, str) or not 0 < len(clip_id) <= 128:
        raise ValueError('Use a bounded clip_id and boolean include_source')

    store, revision, timeline, assets = _snapshot(project_path)
    clip = next((c for t in timeline.tracks for c in t.clips if c.clip_id == clip_id), None)
    source = DEFAULT_SOURCE
    if clip and clip.document_id is not None:
        document = timeline.graphics_documents.get(clip.document_id)
        if document is None:
            raise ValueError('Graphics document is missing')
        source = document['source']
    elif clip:
        asset = assets.get(clip.asset_hash)
        if asset is None or asset.provider != 'diffusion':
            raise ValueError('Selected clip is not a Diffusion graphics clip')
        key = asset.source_url.removeprefix('openedit:graphics:')
        if len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('Graphics provenance is missing')
        record = Path(project_path) / '.open_edit/graphics' / f'{key}.json'
        if not record.is_file():
            raise ValueError('Graphics source record is missing; restore the project graphics directory')
        source = store.load_authoring_source(f'{GRAPHICS_FORMAT}:{clip_id}', revision) or json.loads(record.read_text())['source']
    out = {'status': 'ok', 'format': GRAPHICS_FORMAT, 'graph_revision': revision, 'clip_id': clip_id,
           'worker_ready': graphics_ready(), 'existing': clip is not None}
    last_good = DEFAULT_RENDER_JOB_SERVICE.latest_succeeded(Path(project_path), 'graphics')
    if last_good:
        out['last_good_job_id'] = last_good.job_id
    if include_source:
        out['source'] = source
    return out
