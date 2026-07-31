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
and ``overlay`` (delegate to ``kernel.render_overlay.run_trigger_render``
for the composited HTML-overlay path). The proxy/final branch is
intentionally NOT collapsed into the overlay branch: those paths write
different ``render_id`` shapes and the agent's verification stage reads them
differently (see test_serve_agent.py V4 tests).

v1.7+ polish: ``execute_trigger_render`` is async and uses
``asyncio.create_subprocess_exec`` so the event loop stays responsive
during long renders. This is what makes the Stop button interrupt
a render cleanly: the previous synchronous ``subprocess.run`` blocked
the WS task for the full ``RENDER_TIMEOUT_S`` window.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
from pathlib import Path
from typing import Any

# NOTE: kernel must not import the serve package (layering invariant).
from open_edit.ir.hash import compute_edit_graph_hash
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.storage.paths import ProjectPaths

from open_edit.kernel.schema_validator import validate_or_error
from open_edit.kernel.tool_schemas import TOOL_SCHEMAS

# Tools whose argument schemas come from the registry (TOOL_SCHEMAS).
# These declare no ``project_id`` field, but the agent loop injects it
# into every tool call; it must be stripped before schema validation.
# Derived from TOOL_SCHEMAS so the list can never drift from the registry.
_REGISTRY_TOOL_NAMES = frozenset(t["name"] for t in TOOL_SCHEMAS)

# Every TOOL_SCHEMAS name that is NOT a plain callable in TOOL_TABLE.
# These are handled by kernel branches in this module (or by the
# adjacent ``execute_trigger_render`` virtual-tool path) and must never
# be added to ``open_edit.agent.tools.TOOL_TABLE`` — the completeness
# test (tests/test_tool_registry.py) pins this set against the table.
_KERNEL_HANDLED_TOOLS = frozenset(
    {
        "query_project",      # pillar routing: dispatch_query
        "edit_project",       # pillar routing: dispatch_edit / dispatch_generate
        "get_render_job",     # kernel render-service branch
        "cancel_render_job",  # kernel render-service branch
        "trigger_render",     # virtual tool: execute_trigger_render
    }
)


def _strip_injected_project_id(
    name: str, args: dict[str, Any],
) -> dict[str, Any]:
    """Drop the agent-loop-injected ``project_id`` for registry tools.

    Non-registry tools (the ``TOOL_TABLE`` lookup in ``_run_tool``) keep
    receiving the injected field — their callables may rely on it.
    """
    if name in _REGISTRY_TOOL_NAMES:
        return {k: v for k, v in args.items() if k != "project_id"}
    return args


def _canonicalize_project_id(
    name: str, args: dict[str, Any], project_path: Path,
) -> dict[str, Any]:
    """Use the graph's stable id for project-scoped TOOL_TABLE calls.

    The serve API's public project id is path-derived, but notes and markers
    are stored with ``EditGraphStore.project_id``. Direct agent-loop calls
    currently inject the former, so normalize it at the shared executor
    boundary. Keep the original arguments for uninitialised projects.
    """
    if name in {"search_assets", "query_project", "edit_project"}:
        return args
    if not isinstance(args, dict) or "project_id" not in args:
        return args
    try:
        db_path = ProjectPaths.for_project(project_path).db_path
        if not db_path.exists():
            return args
        canonical_id = EditGraphStore(db_path).project_id
    except Exception:
        return args
    normalized = dict(args)
    normalized["project_id"] = canonical_id
    return normalized


def _payload_hash(args: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(args, sort_keys=True, default=str).encode()
    ).hexdigest()


def _is_error_result(result: Any) -> bool:
    """True for error-shaped results that must never be cached as done.

    Matches the canonical ``{"status": "error"}`` contract plus the
    MCP-parity ``{"ok": False, ...}`` and ``{"error": ...}`` envelopes
    used by the render-job helpers and ``trigger_render`` (an error
    cached as ``done`` would turn a retried failure into a success hit).
    """
    if not isinstance(result, dict):
        return False
    if result.get("status") == "error":
        return True
    if result.get("ok") is False:
        return True
    # ``public_job`` carries ``error: None`` on success, so only a
    # non-None ``error`` value marks a failure.
    return "error" in result and result.get("error") is not None


def _record_done_command(
    store: EditGraphStore | None, project_path: Path, command_id: str,
    name: str, args: dict[str, Any], result: Any,
) -> None:
    """Best-effort idempotency bookkeeping. Never raises. Only records a
    ``done`` command for a normal (non-error) result."""
    if _is_error_result(result):
        return
    try:
        if store is None:
            store = EditGraphStore(ProjectPaths.for_project(project_path).db_path)
        store.record_command(
            command_id, store.project_id, name,
            status="pending", payload_hash=_payload_hash(args),
        )
        store.finish_command(
            command_id, status="done",
            result_json=json.dumps(result, default=str),
        )
        try:
            store.set_edit_graph_hash(compute_edit_graph_hash(store.load_all()))
        except Exception:
            pass
    except Exception:
        pass


def _cached_done_result(
    project_path: Path, command_id: str,
) -> tuple[EditGraphStore | None, Any, bool]:
    """Return ``(store, cached_result, hit)``. ``hit`` is True only for a
    previously SUCCESSFUL (``done``) command with a stored result."""
    try:
        store = EditGraphStore(ProjectPaths.for_project(project_path).db_path)
    except Exception:
        return None, None, False
    try:
        if store.command_exists(command_id):
            if (store.get_command_status(command_id) or "") == "done":
                cached = store.get_command_result(command_id)
                if cached is not None:
                    return store, json.loads(cached), True
    except Exception:
        return None, None, False
    return store, None, False


class ToolNotFound(LookupError):  # noqa: N818
    """Raised by :func:`execute_tool` when the named tool is not
    registered in ``open_edit.agent.tools.TOOL_TABLE``."""


def execute_tool(
    name: str, args: dict[str, Any], project_path: Path,
    command_id: str | None = None,
) -> dict[str, Any]:
    """Run a tool by name, dispatching through
    ``open_edit.agent.tools.TOOL_TABLE`` (plus the kernel branches in
    this module for render-job helpers and pillar routing).

    The tool signature is ``fn(args: dict, project_path: str) -> dict``.
    Raises :class:`ToolNotFound` if the tool module/function is missing
    or not callable.

    When ``command_id`` is given, a re-delivered call that previously
    succeeded is short-circuited to its cached result (idempotency).
    """
    store: EditGraphStore | None = None
    if command_id is not None:
        store, cached, hit = _cached_done_result(project_path, command_id)
        if hit:
            return cached

    result = _run_tool(name, args, project_path)

    # Awaitable results (e.g. ``cancel_render_job`` from an async caller)
    # are not recorded here: recording a coroutine object would pollute
    # the idempotency store, and the awaiting caller owns that result.
    if command_id is not None and not inspect.isawaitable(result):
        _record_done_command(store, project_path, command_id, name, args, result)
    return result


def _run_tool(name: str, args: dict[str, Any], project_path: Path) -> dict[str, Any]:
    args = _strip_injected_project_id(name, args)
    args = _canonicalize_project_id(name, args, project_path)

    err = validate_or_error(name, args)
    if err is not None:
        return err

    # Render-job helpers: same dispatch and envelope shapes as
    # ``mcp/adapters.py`` (which keeps its own branches for MCP callers;
    # this is the kernel-side dispatch for the agent loop and pi_bridge).
    if name == "get_render_job":
        job_id = args.get("job_id")
        if not job_id or not isinstance(job_id, str):
            return {
                "ok": False,
                "error": "job_id is required",
                "expected_keys": ["job_id"],
            }
        from open_edit.kernel.render_jobs import (
            DEFAULT_RENDER_JOB_SERVICE,
            public_job,
        )

        job = DEFAULT_RENDER_JOB_SERVICE.get(project_path, job_id)
        if job is None:
            return {"ok": False, "error": f"render job not found: {job_id}"}
        return {"ok": True, **public_job(job)}

    if name == "cancel_render_job":
        job_id = args.get("job_id")
        if not job_id or not isinstance(job_id, str):
            return {
                "ok": False,
                "error": "job_id is required",
                "expected_keys": ["job_id"],
            }
        from open_edit.kernel.render_jobs import (
            DEFAULT_RENDER_JOB_SERVICE,
            public_job,
        )

        async def _do_cancel() -> dict[str, Any]:
            job = await DEFAULT_RENDER_JOB_SERVICE.cancel(project_path, job_id)
            if job is None:
                return {"ok": False, "error": f"render job not found: {job_id}"}
            return {"ok": True, **public_job(job)}

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # Sync caller (e.g. pi_bridge CLI): no loop to await on.
            return asyncio.run(_do_cancel())
        # Async caller (agent loop): hand back the awaitable; the loop
        # awaits it (see loop.py ``_execute_tool``).
        return _do_cancel()

    # Pillar tool routing (Plan D).
    if name == "query_project":
        from open_edit.kernel.pillar_tools import dispatch_query

        return dispatch_query(args.get("query", ""), args.get("params", {}), project_path)

    if name == "edit_project":
        from open_edit.kernel.pillar_tools import dispatch_edit, dispatch_generate

        generate = args.get("generate")
        if generate:
            return dispatch_generate(generate, args.get("generate_params", {}), project_path)
        return dispatch_edit(args.get("operation", ""), args.get("params", {}), project_path)

    from open_edit.agent.tools import TOOL_TABLE

    fn = TOOL_TABLE.get(name)
    if fn is None:
        raise ToolNotFound(f"tool not found in open_edit.agent.tools: {name!r}")

    return fn(args, str(project_path))

async def execute_trigger_render(
    args: dict[str, Any], project_path: Path, command_id: str | None = None,
) -> dict[str, Any]:
    """Server-side virtual tool: shell out to ``open_edit render``.

    v1.6: ``mode=="overlay"`` is the composited HTML-overlay path. We
    delegate to ``kernel.render_overlay.run_trigger_render`` so the
    in-process agent loop and the TS extension see identical behavior.

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
    store: EditGraphStore | None = None
    if command_id is not None:
        store, cached, hit = _cached_done_result(project_path, command_id)
        if hit:
            return cached

    result = await _run_trigger_render(args, project_path)

    if command_id is not None:
        _record_done_command(store, project_path, command_id, "trigger_render", args, result)
    return result


async def _run_trigger_render(args: dict[str, Any], project_path: Path) -> dict[str, Any]:
    args = _strip_injected_project_id("trigger_render", args)
    err = validate_or_error("trigger_render", args)
    if err is not None:
        return err

    mode = (args.get("mode") or "proxy").lower()
    if mode not in ("proxy", "final", "overlay"):
        return {
            "ok": False,
            "error": f"invalid mode {mode!r}; expected proxy|final|overlay",
            "error_code": "schema_validation_failed",
        }

    encoder = args.get("encoder")
    if encoder is not None and str(encoder).lower() not in ("gpu", "cpu"):
        encoder = None

    quality = args.get("quality")
    if quality is not None and str(quality).lower() not in ("fast", "standard", "high", "archival"):
        return {"ok": False, "error": f"invalid quality {quality!r}", "error_code": "schema_validation_failed"}
    codec = args.get("codec")
    if codec is not None and str(codec).lower() not in ("h264", "hevc", "av1"):
        return {"ok": False, "error": f"invalid codec {codec!r}", "error_code": "schema_validation_failed"}
    params = {k: v for k, v in (
        ("profile", args.get("profile")), ("quality", str(quality).lower() if quality else None),
        ("crf", args.get("crf")), ("vb", args.get("vb")), ("preset", args.get("preset")),
        ("scale", args.get("scale")), ("codec", str(codec).lower() if codec else None),
    ) if v is not None}

    wait = args.get("wait", False)
    if isinstance(wait, str):
        wait = wait.lower() not in ("false", "0", "no")
    # Explicit None / missing → non-blocking for agent token efficiency.
    if args.get("wait") is None and "wait" not in args:
        wait = False


    from open_edit.kernel.render_jobs import DEFAULT_RENDER_JOB_SERVICE, RenderEnqueueError

    # The agent waits for the same durable job REST clients poll. This keeps
    # queueing, timeout, cancellation, output contracts, and audit history
    # identical across both entry points — including overlay.
    try:
        job = DEFAULT_RENDER_JOB_SERVICE.enqueue(
            project_path.name, project_path, mode, encoder_backend=encoder, params=params or None,
        )
    except RenderEnqueueError as exc:
        return {"ok": False, "error": str(exc), "error_code": "render_enqueue_rejected"}
    if not wait:
        return {
            "ok": True,
            "job_id": job.job_id,
            "status": job.status,
            "mode": mode,
            "message": "Render queued. Poll get_render_job with job_id.",
        }
    completed = await DEFAULT_RENDER_JOB_SERVICE.wait(project_path, job.job_id)
    if completed.status != "succeeded" or completed.result is None:
        raise RuntimeError(completed.error or f"render ended as {completed.status}")
    result = dict(completed.result)
    result["render_id"] = completed.job_id
    result["duration_s"] = result.get("duration_sec", 0.0)
    return result
