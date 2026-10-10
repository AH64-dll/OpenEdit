"""Optional, bounded Node compiler/source-writeback process."""
from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import tempfile
from pathlib import Path

from open_edit.integrations.binaries import node_bin

MAX_SOURCE_BYTES = 512 * 1024
WORKER_TIMEOUT_SEC = 20


class CompilerError(ValueError):
    """JSX could not be represented or compiled by the authoring worker."""


def worker_directory() -> Path:
    return Path(os.environ.get('OPEN_EDIT_DIFFUSION_WORKER_DIR') or Path(__file__).with_name('worker')).resolve()


def worker_problem() -> str | None:
    """Why the authoring worker cannot run, with the exact fix; None when ready."""
    if not node_bin():
        return ('Node.js 24+ not found (checked OPEN_EDIT_NODE_BIN, PATH, nvm/fnm/asdf/volta). '
                'Install Node 24 or set OPEN_EDIT_NODE_BIN; query_project get_readiness shows details.')
    directory = worker_directory()
    if not ((directory / 'worker.cjs').is_file() and (directory / 'node_modules' / 'ts-morph').is_dir()):
        return 'Diffusion authoring worker dependencies are not installed. Run: open_edit setup media'
    return None


def worker_ready() -> bool:
    return worker_problem() is None


def parse_and_compile(source: str, *, edits: list | None = None) -> dict:
    if not isinstance(source, str) or len(source.encode('utf-8')) > MAX_SOURCE_BYTES:
        raise CompilerError('JSX source must be a string of at most 512 KiB')
    if not worker_ready():
        raise CompilerError(worker_problem() or 'Diffusion worker is not ready')
    request = {'source': source}
    if edits is not None:
        request['edits'] = edits
    payload = json.dumps(request, ensure_ascii=True, allow_nan=False).encode()
    if len(payload) > 2 * MAX_SOURCE_BYTES:
        raise CompilerError('Authoring request exceeds 1 MiB')
    with tempfile.TemporaryDirectory(prefix='openedit-authoring-') as scratch, tempfile.TemporaryFile() as output:
        proc = subprocess.Popen(
            [node_bin(), str(worker_directory() / 'worker.cjs')],
            cwd=scratch, stdin=subprocess.PIPE, stdout=output, stderr=subprocess.DEVNULL,
            start_new_session=os.name == 'posix',
        )
        try:
            proc.communicate(payload, timeout=WORKER_TIMEOUT_SEC)
        except subprocess.TimeoutExpired as exc:
            raise CompilerError('Diffusion compilation timed out; the graph was not changed') from exc
        finally:
            if os.name == 'posix':
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(proc.pid, signal.SIGKILL)
            elif proc.poll() is None:
                # npm/esbuild can spawn descendants on Windows as well.
                with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                    subprocess.run(
                        ['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
                    )
                proc.kill()
            proc.communicate()
        output.seek(0)
        stdout = output.read(2 * MAX_SOURCE_BYTES + 1)
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
        rewritten = result.get('source')
        if not isinstance(rewritten, str) or len(rewritten.encode('utf-8')) > MAX_SOURCE_BYTES:
            raise CompilerError('Diffusion worker returned invalid source')
        digest = result.get('compiled_hash')
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise CompilerError('Diffusion worker returned an invalid compilation hash')
        return result
