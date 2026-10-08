"""Optional, bounded Node compiler/source-writeback process."""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path

MAX_SOURCE_BYTES = 512 * 1024
WORKER_TIMEOUT_SEC = 20


class CompilerError(ValueError):
    """JSX could not be represented or compiled by the authoring worker."""


def worker_directory() -> Path:
    return Path(os.environ.get('OPEN_EDIT_DIFFUSION_WORKER_DIR') or Path(__file__).with_name('worker')).resolve()


def worker_ready() -> bool:
    directory = worker_directory()
    return bool(shutil.which('node') and (directory / 'worker.cjs').is_file() and (directory / 'node_modules' / 'ts-morph').is_dir())


def parse_and_compile(source: str, *, edits: list | None = None) -> dict:
    if not isinstance(source, str) or len(source.encode('utf-8')) > MAX_SOURCE_BYTES:
        raise CompilerError('JSX source must be a string of at most 512 KiB')
    if not worker_ready():
        raise CompilerError('Diffusion worker is not installed. Run python -m open_edit.integrations.diffusion.setup to install its pinned Node dependencies.')
    request = {'source': source}
    if edits is not None:
        request['edits'] = edits
    payload = json.dumps(request, ensure_ascii=True, allow_nan=False).encode()
    if len(payload) > 2 * MAX_SOURCE_BYTES:
        raise CompilerError('Authoring request exceeds 1 MiB')
    with tempfile.TemporaryDirectory(prefix='openedit-authoring-') as scratch:
        proc = subprocess.Popen(
            [shutil.which('node'), str(worker_directory() / 'worker.cjs')],
            cwd=scratch, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=os.name == 'posix',
        )
        try:
            stdout, _ = proc.communicate(payload, timeout=WORKER_TIMEOUT_SEC)
        except subprocess.TimeoutExpired as exc:
            raise CompilerError('Diffusion compilation timed out; the graph was not changed') from exc
        finally:
            if os.name == 'posix':
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(proc.pid, signal.SIGKILL)
            elif proc.poll() is None:
                proc.kill()
            proc.communicate()
        if len(stdout) > 2 * MAX_SOURCE_BYTES:
            raise CompilerError('Diffusion worker response exceeds 1 MiB')
        try:
            result = json.loads(stdout)
        except (ValueError, UnicodeError) as exc:
            raise CompilerError('Diffusion worker returned an invalid response') from exc
        if not isinstance(result, dict):
            raise CompilerError('Diffusion worker returned an invalid response')
        if proc.returncode or result.get('ok') is not True:
            raise CompilerError(str(result.get('error') or 'Diffusion worker failed')[:300])
        if result.get('protocol') != 1 or not isinstance(result.get('document'), dict):
            raise CompilerError('Unsupported Diffusion worker protocol')
        digest = result.get('compiled_hash')
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise CompilerError('Diffusion worker returned an invalid compilation hash')
        return result
