"""Shared tool execution (Wave 3.2).

The agent loop (``agent.py``) and the TS-extension shim
(``pi_bridge.py``) both need to run tools on the server side. Before
this module existed, ``agent.py`` had its own ``_execute_agent_tool``
and ``_execute_trigger_render`` functions, and ``pi_bridge.py`` had a
parallel copy of the trigger-render logic. The two could drift
(``agent.py`` accepts a ``mode`` field, ``pi_bridge.py`` rejected it,
etc.), and the bug was a latent source of "the agent sees different
behavior than the TS extension" reports.

This module owns the canonical implementations. Both callers import
from here. If the behavior needs to change, it changes in one place.

v1.6 note: ``execute_trigger_render`` preserves the three-way split
between ``proxy``, ``final`` (shell out to ``open_edit render`` CLI)
and ``overlay`` (delegate to ``pi_bridge._run_trigger_render`` for the
composited HTML-overlay path). The proxy/final branch is intentionally
NOT collapsed into the overlay branch: those paths write different
``render_id`` shapes and the agent's verification stage reads them
differently (see test_serve_agent.py V4 tests).

v1.7+ polish: ``execute_trigger_render`` is async and uses
``asyncio.create_subprocess_exec`` so the event loop stays responsive
during long renders. This is what makes the Stop button interrupt
a render cleanly: the previous synchronous ``subprocess.run`` blocked
the WS task for the full ``RENDER_TIMEOUT_S`` window.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from .pi_bridge import _probe_duration
from .serve_env import RENDER_TIMEOUT_S


class ToolNotFound(LookupError):  # noqa: N818
    """Raised by :func:`execute_tool` when the named tool is not
    registered in ``open_edit.agent.tools``."""


def execute_tool(name: str, args: dict[str, Any], project_path: Path) -> dict[str, Any]:
    """Run a tool from ``open_edit.agent.tools.<name>``.

    The tool signature is ``fn(args: dict, project_path: str) -> dict``.
    Raises :class:`ToolNotFound` if the tool module/function is missing
    or not callable.
    """
    import open_edit.agent.tools as tools_mod  # type: ignore

    fn = getattr(tools_mod, name, None)
    if fn is None or not callable(fn):
        raise ToolNotFound(f"tool not found in open_edit.agent.tools: {name!r}")

    return fn(args, str(project_path))


async def execute_trigger_render(args: dict[str, Any], project_path: Path) -> dict[str, Any]:
    """Server-side virtual tool: shell out to ``open_edit render``.

    v1.6: ``mode=="overlay"`` is the composited HTML-overlay path. We
    delegate to ``pi_bridge._run_trigger_render`` so the in-process
    agent loop and the TS extension see identical behavior.

    v1.6 V4: the returned dict must use the same structured shape as
    the pi subprocess path (``{output_path, mode, duration_s, render_id}``)
    so the verification stage's ``result.get("render_id", ...)`` always
    sees a real render id (not "render_unknown") regardless of which
    path was taken.

    v1.7: async + ``asyncio.create_subprocess_exec`` so the event loop
    stays responsive. The function is now an awaitable; callers must
    ``await`` it. Cancellation propagates via ``asyncio.CancelledError``
    and the subprocess is killed before re-raising.
    """
    mode = (args.get("mode") or "proxy").lower()
    if mode == "overlay":
        from .pi_bridge import _run_trigger_render as _bridge_trigger_render
        # _run_trigger_render is sync; run it in a thread to keep the
        # event loop responsive (the overlay path spawns ffmpeg + may
        # run the html-overlay pipeline).
        result = await asyncio.to_thread(_bridge_trigger_render, args, project_path)
        return result
    if mode not in ("proxy", "final"):
        mode = "proxy"

    render_id = f"render_{os.urandom(6).hex()}"

    proc: asyncio.subprocess.Process | None = None
    try:
        proc = await asyncio.create_subprocess_exec(
            "open_edit", "render", "--mode", mode,
            cwd=str(project_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("`open_edit` CLI not found on PATH.") from exc

    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(),
            timeout=RENDER_TIMEOUT_S,
        )
    except asyncio.TimeoutError as exc:
        proc.kill()
        try:
            await proc.wait()
        except Exception:
            pass
        raise RuntimeError(f"render timed out after {RENDER_TIMEOUT_S}s") from exc
    except asyncio.CancelledError:
        # Cancellation (e.g. user clicked Stop): kill the subprocess
        # and re-raise so the agent loop unwinds.
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        raise
    except Exception:
        # Unknown transport error — try to clean up the process.
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        raise

    if proc.returncode != 0:
        stderr_text = stderr_b.decode("utf-8", errors="replace").strip()
        stdout_text = stdout_b.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"`open_edit render --mode {mode}` failed (exit {proc.returncode}): "
            f"{stderr_text or stdout_text}"
        )

    stdout_text = stdout_b.decode("utf-8", errors="replace")
    stderr_text = stderr_b.decode("utf-8", errors="replace")

    # The CLI prints the output path on the last non-empty line of stdout.
    last_line = ""
    for line in reversed(stdout_text.splitlines()):
        if line.strip():
            last_line = line.strip()
            break

    # If the last line looks like a path, use it; otherwise scan the renders dir.
    output_path = last_line if (last_line and ("/" in last_line or "\\" in last_line)) else ""
    if not output_path:
        renders_dir = project_path / ".open_edit" / "renders"
        if renders_dir.exists():
            mp4s = sorted(renders_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
            if mp4s:
                output_path = str(mp4s[0])

    # Probe duration if we have a real file; 0.0 on missing/invalid.
    duration_s = 0.0
    if output_path:
        mp4_path = Path(output_path)
        if mp4_path.exists() and mp4_path.stat().st_size > 0:
            try:
                # Run probe in a thread (ffprobe is a subprocess).
                duration_s = await asyncio.to_thread(_probe_duration, mp4_path)
            except RuntimeError:
                duration_s = 0.0

    return {
        "mode": mode,
        "output_path": output_path,
        "duration_s": duration_s,
        "render_id": render_id,
        "stdout": stdout_text,
        "stderr": stderr_text,
    }
