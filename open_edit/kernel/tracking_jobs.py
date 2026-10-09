"""Durable tracking results; analysis never overwrites concurrent editor work."""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from open_edit.ir.object_tracking import ObjectTrack
from open_edit.kernel.edit_graph_service import open_store
from open_edit.kernel.object_tracking import (
    TrackingRequest,
    prepare_tracking,
    summarize_track,
    track_video,
)
from open_edit.kernel.studio_service import commit_studio

_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='openedit-tracking')
_GUARD = threading.Lock()
_ACTIVE: set[tuple[str, str]] = set()
_TERMINAL = {'succeeded', 'failed', 'cancelled', 'applied'}
_OWNER = uuid.uuid4().hex


def _process_alive(pid: int) -> bool:
    """Read process liveness without sending a Windows termination signal."""
    if pid <= 0:
        return False
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE, read-only wait
        if not handle:
            return ctypes.get_last_error() != 87  # invalid PID; access denied stays alive
        try:
            return kernel.WaitForSingleObject(handle, 0) != 0  # signaled means exited
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def _path(root: Path, job_id: str) -> Path:
    if not isinstance(job_id, str) or len(job_id) != 32 or any(c not in '0123456789abcdef' for c in job_id):
        raise ValueError('Invalid tracking job ID')
    return root / '.open_edit/tracking/jobs' / f'{job_id}.json'


def _write(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f'.{uuid.uuid4().hex}.tmp')
    try:
        temp.write_text(json.dumps(value, allow_nan=False), encoding='utf-8')
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _load(root: Path, job_id: str) -> dict:
    path = _path(root, job_id)
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise ValueError('Tracking job not found') from exc
    if data['status'] not in _TERMINAL and (
            (data['pid'] == os.getpid() and data.get('owner') != _OWNER) or
            (data['pid'] != os.getpid() and not _process_alive(data['pid']))):
        data.update(status='failed', error='Tracking was interrupted. Start it again.', updated_at=time.time())
        _write(path, data)
    return data


def get_tracking_job(root: str | Path, *, job_id: str) -> dict:
    data = _load(Path(root), job_id)
    result = {k: data[k] for k in ('job_id', 'object_id', 'status', 'progress', 'error', 'created_at', 'updated_at', 'expected_revision')}
    if data.get('result'):
        result['track'] = summarize_track(data['result'])
    return {'status': 'ok', 'job': result}


def list_tracking_jobs(root: str | Path) -> dict:
    root = Path(root)
    folder = root / '.open_edit/tracking/jobs'
    paths = sorted(folder.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:30]
    return {'status': 'ok', 'jobs': [get_tracking_job(root, job_id=p.stem)['job'] for p in paths]}


def start_tracking(root: str | Path, *, author='user', **values) -> dict:
    root = Path(root).resolve()
    request = TrackingRequest.model_validate(values)
    prepared = prepare_tracking(root, request)
    job_id = uuid.uuid4().hex
    key = (str(root), job_id)
    with _GUARD:
        if sum(k[0] == str(root) for k in _ACTIVE) >= 2:
            raise ValueError('Two tracking jobs are already active in this project')
        path = _path(root, job_id)
        data = {'job_id': job_id, 'object_id': request.object_id or f'object-{job_id}',
                'pid': os.getpid(), 'owner': _OWNER, 'status': 'queued', 'progress': 0., 'error': None,
                'created_at': time.time(), 'updated_at': time.time(),
                'expected_revision': request.expected_revision, 'request': request.model_dump(mode='json'),
                'prepared': prepared, 'author': author}
        _write(path, data)
        _ACTIVE.add(key)
        try:
            _POOL.submit(_run, root, data, key)
        except Exception:
            _ACTIVE.discard(key)
            raise
    return get_tracking_job(root, job_id=job_id)


def _run(root: Path, data: dict, key):
    path = _path(root, data['job_id'])
    cancel = path.with_suffix('.cancel')
    last = 0.
    def progress(value):
        nonlocal last
        if time.monotonic() - last > .5:
            data.update(progress=value, updated_at=time.time())
            _write(path, data)
            last = time.monotonic()
    try:
        data.update(status='running', updated_at=time.time())
        _write(path, data)
        result = track_video(data['prepared'], TrackingRequest.model_validate(data['request']),
                             cancelled=cancel.exists, progress=progress)
        if cancel.exists():
            raise InterruptedError('Tracking cancelled')
        data.update(status='succeeded', result=result.model_dump(mode='json'), progress=1.)
    except InterruptedError as exc:
        data.update(status='cancelled', error=str(exc))
    except Exception as exc:
        data.update(status='failed', error=str(exc)[:2000])
    finally:
        data['updated_at'] = time.time()
        _write(path, data)
        with _GUARD:
            _ACTIVE.discard(key)


def cancel_tracking(root: str | Path, *, job_id: str) -> dict:
    root = Path(root)
    data = _load(root, job_id)
    if data['status'] not in _TERMINAL:
        _path(root, job_id).with_suffix('.cancel').touch()
    return get_tracking_job(root, job_id=job_id)


def apply_tracking_job(root: str | Path, *, job_id: str, expected_revision: int,
                       author='user', request_id=None) -> dict:
    root = Path(root)
    data = _load(root, job_id)
    if data['status'] != 'succeeded':
        raise ValueError('Only a completed, unapplied tracking job can be applied')
    snapshot = open_store(root).studio_snapshot('object_track')
    current = next((o['data'] for o in snapshot['objects'] if o['object_id'] == data['object_id']), None)
    if current != data['prepared']['before']:
        raise ValueError('This object track changed while tracking. Keep the current edits or start tracking again.')
    track = ObjectTrack.model_validate(data['result'])
    receipt = commit_studio(root, expected_revision=expected_revision, author=author,
        request_id=request_id or data['request'].get('request_id'), label='Track video object',
        changes=[{'kind': 'object_track', 'object_id': data['object_id'], 'data': track.model_dump(mode='json')}])
    data.update(status='applied', updated_at=time.time())
    _write(_path(root, job_id), data)
    return {**receipt, 'object_id': data['object_id']}
