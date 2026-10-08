"""Bounded subprocess execution for trusted scripts on the MCP host."""
from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

from open_edit.agent.exceptions import FreeFormResult
from open_edit.agent.script_runner.bootstrap import render_bootstrap
from open_edit.agent.script_runner.staging import stage_and_collect

_OUTPUT_LIMIT = 64 * 1024


def execute_python(args: list[str], workdir: Path, timeout: int, *, env=None):
    """Drain both streams while retaining at most 64 KiB per stream.

    On POSIX, reap the entire process group on exit or timeout, including
    subprocesses started by a script. Windows uses the normal child lifecycle.
    """
    started = time.monotonic()
    proc = subprocess.Popen(
        [sys.executable, *args], cwd=workdir, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=os.name == "posix",
    )
    outputs: list[deque[bytes]] = [deque(), deque()]

    def drain(stream, chunks):
        size = 0
        with stream:
            while chunk := stream.read(4096):
                chunks.append(chunk)
                size += len(chunk)
                while size > _OUTPUT_LIMIT:
                    size -= len(chunks.popleft())

    readers = [
        threading.Thread(target=drain, args=(stream, chunks), daemon=True)
        for stream, chunks in zip((proc.stdout, proc.stderr), outputs, strict=True)
    ]
    for reader in readers:
        reader.start()
    try:
        proc.wait(timeout=timeout)
    finally:
        if os.name == "posix":
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
        elif proc.poll() is None:
            proc.kill()
        proc.wait()
        for reader in readers:
            reader.join(timeout=2)
    stdout, stderr = (b"".join(chunks).decode("utf-8", errors="replace") for chunks in outputs)
    return subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr), time.monotonic() - started


def run_script(
    *, code: str, workdir: Path, project_id: str, parent_op_id: str,
    timeout: int,
    originating_note_id: str | None,
) -> FreeFormResult:
    """Execute a staged script, then validate its complete edit batch."""
    def execute(scratch, code_path, ops_path, bootstrap_path):
        runner = (
            "g = {'__name__': '__main__'}; "
            f"exec(compile(open({str(bootstrap_path)!r}, encoding='utf-8').read(), '<bootstrap>', 'exec'), g); "
            f"exec(compile(open({str(code_path)!r}, encoding='utf-8').read(), '<script>', 'exec'), g)"
        )
        proc, duration = execute_python(['-c', runner], workdir, timeout)
        if proc.returncode:
            # Last traceback line is useful; the facade strips paths and limits length.
            detail = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else f"exit {proc.returncode}"
            return FreeFormResult.fail('script_failed', detail), duration
        return None, duration

    return stage_and_collect(
        workdir=workdir, code=code,
        render_bootstrap=lambda ops_path: render_bootstrap(
            project_id, parent_op_id, originating_note_id, ops_file=str(ops_path),
        ),
        execute=execute,
    )
