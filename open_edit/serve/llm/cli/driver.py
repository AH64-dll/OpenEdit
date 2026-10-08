"""Subprocess streaming for optional CLI chat providers."""
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path
from typing import Any

from ...cli_adapter import CLIAdapter
from ..dispatcher import _message_plain_text, _serialize_cli_conversation

# ---------------------------------------------------------------------------
# Generic CLI subprocess driver
# ---------------------------------------------------------------------------

async def _stream_cli(
    adapter: CLIAdapter,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system: str,
    session_id: str | None,
    project_path: str | None,
) -> AsyncIterator[dict]:
    """Generic subprocess driver for any CLIAdapter.

    Builds the prompt according to the provider's ``context_strategy``:
    session-backed adapters receive only the latest user turn; others
    receive a role-separated conversation transcript.

    Enforces ``adapter.default_timeout_s`` on the subprocess lifetime
    (R4 fix). On timeout, kills the process, yields an ``error`` event
    with a clear message, then a ``done`` event with stop_reason=error.
    """
    from ...providers import PROVIDERS

    strategy = "full_history"
    spec = PROVIDERS.get(adapter.name)
    if spec is not None:
        strategy = spec.context_strategy

    user_text = ""
    if strategy in ("native_session", "stateless"):
        for m in reversed(messages):
            if m.get("role") == "user":
                user_text = _message_plain_text(m)
                break
    else:
        user_text = _serialize_cli_conversation(messages)

    if not user_text:
        yield {"type": "error", "message": f"{adapter.name} provider: no user message found"}
        yield {"type": "done", "stop_reason": "error"}
        return

    sid = session_id or f"oe-{os.getpid()}"

    cmd = adapter.build_command(
        model=model,
        user_text=user_text,
        session_id=sid,
        system_prompt=system,
        project_path=project_path,
    )

    env = dict(os.environ)
    import open_edit
    pkg_root = str(Path(open_edit.__file__).resolve().parents[1])
    env["PYTHONPATH"] = (
        pkg_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    )
    if project_path:
        env["OPEN_EDIT_PROJECT"] = str(project_path)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            limit=65536,
        )
    except FileNotFoundError as exc:
        yield {"type": "error", "message": f"{adapter.name} binary not found: {exc}"}
        yield {"type": "done", "stop_reason": "error"}
        return

    loop = asyncio.get_running_loop()
    deadline = loop.time() + adapter.default_timeout_s
    stderr_tail = bytearray()

    async def drain_stderr() -> None:
        if proc.stderr is None:
            return
        while chunk := await proc.stderr.read(65536):
            stderr_tail.extend(chunk)
            del stderr_tail[:-65536]

    stderr_task = asyncio.create_task(drain_stderr())

    async def read_lines() -> AsyncIterator[bytes]:
        assert proc.stdout is not None
        buf = bytearray()
        max_line_bytes = 1_048_576
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError
            chunk = await asyncio.wait_for(proc.stdout.read(65536), timeout=remaining)
            if not chunk:
                if buf:
                    yield bytes(buf)
                return
            buf.extend(chunk)
            while (newline := buf.find(b"\n")) != -1:
                if newline > max_line_bytes:
                    raise ValueError("CLI output line exceeds the 1 MiB limit")
                yield bytes(buf[:newline + 1])
                del buf[:newline + 1]
            if len(buf) > max_line_bytes:
                raise ValueError("CLI output line exceeds the 1 MiB limit")

    saw_text = False
    stop_reason = "end_turn"
    try:
        async for ev in adapter.stream_events(read_lines()):
            if ev.get("type") == "text_delta":
                saw_text = True
            if ev.get("type") == "done":
                stop_reason = ev.get("stop_reason", "end_turn")
                continue
            yield ev
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError
        await asyncio.wait_for(proc.wait(), timeout=remaining)
        await asyncio.wait_for(asyncio.shield(stderr_task), timeout=max(0.01, deadline - loop.time()))
        if adapter.check_exit_status and proc.returncode != 0 and not saw_text:
            yield {
                "type": "error",
                "message": stderr_tail.decode("utf-8", errors="replace").strip()
                or f"{adapter.name} exited {proc.returncode}",
            }
            stop_reason = "error"
    except TimeoutError:
        yield {
            "type": "error",
            "message": f"{adapter.name} timeout: timed out after {adapter.default_timeout_s}s",
        }
        stop_reason = "error"
    except ValueError as exc:
        yield {"type": "error", "message": str(exc)}
        stop_reason = "error"
    finally:
        if proc.returncode is None:
            with suppress(ProcessLookupError):
                proc.kill()
        stderr_task.cancel()
        with suppress(asyncio.CancelledError):
            await stderr_task
        # Drain both pipes after killing; otherwise Process.wait can hang on
        # buffered stdout during cancellation or an oversized output line.
        with suppress(TimeoutError):
            await asyncio.wait_for(proc.communicate(), timeout=5)
    yield {"type": "done", "stop_reason": stop_reason}
