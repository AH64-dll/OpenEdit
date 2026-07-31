"""Generic subprocess driver for CLI providers (pi, opencode, antigravity,
jcode) + the pi cost-extraction wrapper.

The driver is adapter-generic: it builds the prompt per the provider's
``context_strategy``, spawns the binary, and feeds the raw stdout line
stream to ``adapter.stream_events()`` (which by default loops
``adapter.normalize_event(line)``).  Adapter behaviour differences that
used to be per-provider name branches in the driver are now adapter
attributes/methods:

- ``defers_done``     — the adapter's caller (pi cost wrapper) owns the
                        trailing ``done``; the driver must not emit one.
- ``check_exit_status`` — surface non-zero exit + stderr as an error when
                        the adapter didn't already own terminal semantics.
- ``extension_path()`` — adapter-specific TS extension path (pi only).
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path
from typing import Any

from ... import cost as cost_mod
from ...cli_adapter import CLIAdapter, get_adapter
from ..dispatcher import _message_plain_text, _serialize_cli_conversation
from ..keys import _model

_LOG = logging.getLogger("open_edit.serve.llm")


# ---------------------------------------------------------------------------
# Pi implementation
# ---------------------------------------------------------------------------

async def _stream_pi(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system: str,
    session_id: str | None,
    project_path: str | None = None,
    model: str | None = None,
) -> AsyncIterator[dict]:
    """Pi provider — delegates to _stream_cli with the PiAdapter.

    After _stream_cli finishes, we read the pi session JSONL delta to
    extract the per-call cost (v1.4 P1-3). The opencode provider does
    not need this — it reports cost directly in step_finish events.

    Event order: text_deltas → tool_use → tool_result → ``usage`` →
    ``done``. _stream_cli deliberately does NOT emit a trailing
    ``done`` for the pi branch — the cost-extraction-and-done
    responsibility is owned by this wrapper, so the agent loop sees
    a single ``done`` at the very end, after the ``usage`` event.
    """
    sid = session_id or f"oe-{os.getpid()}"

    # Pi stores sessions in ~/.pi/agent/sessions/<encoded-cwd>/<timestamp>_<sid>.jsonl.
    # Capture its current byte position before the call so the usage event is
    # strictly this turn's delta rather than a cumulative session total.
    sessions_dir = cost_mod.default_pi_sessions_dir()
    pre_turn_session = cost_mod.find_pi_session_file(sid, sessions_dir)
    baseline_size = 0
    if pre_turn_session is not None:
        try:
            baseline_size = pre_turn_session.stat().st_size
        except OSError:
            # A concurrent rotation is handled by the parser's reset logic.
            baseline_size = 0

    adapter = get_adapter("pi")
    async for ev in _stream_cli(
        adapter, model or _model(), messages, tools, system, session_id, project_path,
    ):
        yield ev

    # Cost extraction (v1.4 P1-3). _stream_cli did NOT emit a trailing
    # ``done`` for the pi branch — we own it here so the final order is
    # usage → done. Pi cost is read from the session JSONL delta.
    session_path = cost_mod.find_pi_session_file(sid, sessions_dir)
    if session_path is None or not session_path.exists():
        yield {
            "type": "usage", "source": "unavailable",
            "tokens": 0, "cost_usd": 0.0, "usage": {},
        }
    else:
        delta = cost_mod.parse_pi_session_usage_delta(session_path, last_size=baseline_size)
        yield {
            "type": "usage", "source": "pi",
            "tokens": delta["tokens"], "cost_usd": delta["cost_usd"], "usage": {},
        }

    yield {"type": "done", "stop_reason": "end_turn"}


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
    """Generic subprocess driver for any CLIAdapter (pi, opencode, ...).

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
    extension_path = adapter.extension_path()

    cmd = adapter.build_command(
        model=model,
        user_text=user_text,
        session_id=sid,
        extension_path=extension_path,
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
            limit=16 * 1024 * 1024,
        )
    except FileNotFoundError as exc:
        yield {"type": "error", "message": f"{adapter.name} binary not found: {exc}"}
        yield {"type": "done", "stop_reason": "error"}
        return

    async def _read_with_timeout() -> AsyncIterator[bytes]:
        assert proc.stdout is not None
        buf = b""
        max_line_bytes = 1_048_576  # 1 MB
        while True:
            try:
                chunk = await asyncio.wait_for(proc.stdout.read(65536), timeout=adapter.default_timeout_s)
            except TimeoutError:
                with suppress(ProcessLookupError):
                    proc.kill()
                raise
            if not chunk:
                if buf:
                    yield buf
                return
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if len(line) > max_line_bytes:
                    _LOG.warning("oversized CLI line (%d bytes), truncating", len(line))
                    line = line[:max_line_bytes] + b"... [truncated]"
                yield line + b"\n"

    saw_text = False
    saw_done = False
    try:
        async for ev in adapter.stream_events(_read_with_timeout()):
            if ev.get("type") == "text_delta":
                saw_text = True
            if ev.get("type") == "done":
                saw_done = True
            yield ev
    except TimeoutError:
        with suppress(ProcessLookupError):
            proc.kill()
        yield {
            "type": "error",
            "message": f"{adapter.name} timeout: timed out after {adapter.default_timeout_s}s",
        }
        yield {"type": "done", "stop_reason": "error"}
        return
    except asyncio.CancelledError:
        with suppress(Exception):
            proc.kill()
        raise

    try:
        await asyncio.wait_for(proc.wait(), timeout=5.0)
    except TimeoutError:
        proc.kill()

    if adapter.check_exit_status and proc.returncode != 0 and not saw_text:
        stderr_data = b""
        if proc.stderr is not None:
            with suppress(Exception):
                stderr_data = await proc.stderr.read()
        stderr_text = stderr_data.decode("utf-8", errors="replace").strip()
        yield {
            "type": "error",
            "message": stderr_text or f"{adapter.name} exited {proc.returncode}",
        }
        yield {"type": "done", "stop_reason": "error"}
        return

    # Exactly one trailing ``done`` unless the adapter's normalizer
    # already emitted one (opencode step_finish) or the adapter defers
    # it to its caller (pi cost wrapper).
    if not saw_done and not adapter.defers_done:
        yield {"type": "done", "stop_reason": "end_turn"}
