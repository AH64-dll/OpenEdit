"""The Open Edit agent loop.

``run_agent_turn`` is an async generator that:

1. Builds a deterministic system prompt from the current project state.
2. Appends the user's message to the conversation history.
3. Streams the LLM response; for each ``tool_use`` block:
   - emits a ``tool_start`` event
   - executes the tool (via ``open_edit.agent.tools.<name>`` or via the
     server-side ``trigger_render`` virtual tool)
   - emits a ``tool_result`` event (or ``error`` if the tool raised)
4. Appends the assistant message + tool_result messages to the history.
5. Loops until the LLM returns ``end_turn``.

The conversation history is persisted as JSONL at
``<project>/.open_edit/conversations/<conv_id>.jsonl`` (one JSON message
per line).
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import tempfile
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any, Literal, TypedDict

from . import projects as projects_mod
from . import visual_verify
from .llm import _coerce_event, stream_chat
from .llm import _provider as _llm_provider
from .pi_bridge import _probe_duration
from .project_meta import is_verify_disabled
from .serve_env import get_visual_verify_config
from .tool_schemas import (
    IR_MODEL_SUMMARY,
    TOOL_SCHEMAS,
    TOOL_USAGE_GUIDE,
)

# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

class AgentEvent(TypedDict, total=False):
    """One event yielded by ``run_agent_turn``.

    Variants:
    - ``{"type": "text", "text": "..."}``  — assistant text delta
    - ``{"type": "tool_start", "name": "...", "input": {...}}``
    - ``{"type": "tool_result", "name": "...", "result": {...}}``
    - ``{"type": "render", "path": "...", "mode": "proxy"|"final"}``
    - ``{"type": "error", "message": "..."}``
    - ``{"type": "done", "stop_reason": "..."}``  — terminal event
    - ``{"type": "cost_update", "turn_tokens", "turn_cost_usd",
         "session_cost_usd", "source"}``  — v1.4 P1-3, emitted
      AFTER the terminal ``done`` once per turn.
    """
    type: Literal[
        "text", "tool_start", "tool_result", "render",
        "error", "done", "cost_update",
        "verification_started", "verification_result",
    ]


# Source-priority for the cost_update event. When a turn has
# multiple LLM calls with different ``usage.source`` values (e.g.
# a partial provider switch, or a pi call followed by a
# misconfigured anthropic call), we report the highest-priority
# non-"unavailable" source on the cost_update so the UI can show
# the most informative label. Pi is preferred because the user's
# default is pi and pi's numbers are authoritative for that path.
_SOURCE_PRIORITY = {"pi": 0, "computed": 1, "unavailable": 2}


# v1.6 polish: ``MAX_AGENT_ITERATIONS`` is now a module-scope constant so
# operators can tune the runaway-loop safety cap at process start without
# editing source. Override via the ``OPEN_EDIT_AGENT_MAX_ITERATIONS`` env
# var (parsed as an int; non-integer values will raise at import time).
MAX_AGENT_ITERATIONS = int(os.environ.get("OPEN_EDIT_AGENT_MAX_ITERATIONS", "10"))


# v1.6 polish: ``_llm_provider`` is imported at the top of the module so
# it's resolved once at import time. The provider doesn't change between
# iterations of the same turn, and the agent loop reads the resolved value
# at the top of each iteration (see ``run_agent_turn``).


# ---------------------------------------------------------------------------
# Conversation persistence
# ---------------------------------------------------------------------------

def _conversations_dir(project_path: Path) -> Path:
    d = project_path / ".open_edit" / "conversations"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_conversation(project_id: str, conv_id: str) -> list[dict[str, Any]]:
    """Load a conversation from disk. Returns ``[]`` if it doesn't exist."""
    path = _resolve_project_path(project_id)
    if path is None:
        return []
    f = _conversations_dir(path) / f"{conv_id}.jsonl"
    if not f.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def append_to_conversation(project_id: str, conv_id: str, message: dict[str, Any]) -> None:
    """Append one message to the conversation JSONL file."""
    path = _resolve_project_path(project_id)
    if path is None:
        return
    f = _conversations_dir(path) / f"{conv_id}.jsonl"
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(message, sort_keys=True, default=str) + "\n")


def new_conversation_id() -> str:
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# Cost sidecar persistence (v1.4 P1-3)
# ---------------------------------------------------------------------------
# The cumulative session cost is persisted as a sidecar JSON file
# at ``<project>/.open_edit/cost.json``, keyed by ``conv_id``. The
# sidecar is small (one float per conversation) and lazy: we read
# it at turn start and write it via ``asyncio.to_thread`` so the
# disk I/O doesn't block the WS event loop. A separate SQLite
# table alongside ``edit_graph.db`` was an option, but the
# sidecar keeps ``EditGraphStore``'s schema untouched and keeps
# cost data trivially inspectable from the command line.

def _cost_sidecar_path(project_path: Path) -> Path:
    """Path of the per-project cost sidecar JSON."""
    return project_path / ".open_edit" / "cost.json"


def _load_cost_state(project_path: Path) -> dict[str, dict[str, Any]]:
    """Read the cost sidecar for a project.

    Returns a flat dict ``{conv_id: {session_cost_usd, source, last_turn_cost_usd}}``.
    Missing/corrupt files return ``{}`` — we never raise on read
    so a malformed sidecar can't crash the agent loop. The
    operator can ``rm .open_edit/cost.json`` to reset.
    """
    p = _cost_sidecar_path(project_path)
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _write_cost_json_sync(path: Path, state: dict[str, dict[str, Any]]) -> None:
    """Synchronous JSON write — wrapped in ``asyncio.to_thread`` by
    callers so disk I/O doesn't block the event loop. Atomic via
    temp file + ``os.replace`` so a crash mid-write can't leave
    the sidecar in a half-written state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, sort_keys=True, default=str)
    os.replace(tmp, path)


def _save_cost_state(
    project_path: Path, state: dict[str, dict[str, Any]],
) -> None:
    """Synchronous save — tests use this; the agent loop uses
    ``_save_cost_state_async`` for off-loop writes.

    Merges with the existing sidecar so unrelated conv_ids (other
    conversations in the same project) are preserved. The merge
    is in-memory + atomic write: load the existing file, update
    the entries from ``state``, write back. A sidecar with N
    conversations is small (a few KB at most) so re-reading it
    on every save is fine.
    """
    existing = _load_cost_state(project_path)
    existing.update(state)
    _write_cost_json_sync(_cost_sidecar_path(project_path), existing)


async def _save_cost_state_async(
    project_path: Path, state: dict[str, dict[str, Any]],
) -> None:
    """Async save — runs the disk I/O on a thread so the WS loop
    stays responsive. The brief says cost persistence is
    'lazy-loaded; don't block turn completion on disk I/O'; this
    is that."""
    await asyncio.to_thread(
        _write_cost_json_sync, _cost_sidecar_path(project_path), state,
    )


# ---------------------------------------------------------------------------
# System prompt (DETERMINISTIC — see hard requirement #5)
# ---------------------------------------------------------------------------

_SYSTEM_PREAMBLE = """\
You are the Open Edit agent — an AI assistant that drives the Open Edit
video editor through a chat interface. You operate on ONE project at a
time, and the user's intent is to make edits to that project's video.

You have access to a set of tools (passed via the `tools` parameter).
Always prefer calling a dedicated tool over writing Python. Only fall
back to `run_python` when no dedicated tool fits the request, or when
you need to compose multiple ops atomically.

Be concise in your text responses. The user sees your text streamed in
real time, so don't pad with filler. If you're about to call a tool,
a one-line lead-in is enough (e.g. "Let me check the project's assets.").

If a tool call fails, you'll see an `error` event in the tool_result.
Surface the failure to the user briefly and propose a fix or a fallback.
"""


def _build_system_prompt(state: projects_mod.ProjectState) -> str:
    """Build the system prompt.

    Deterministic: the same ``state`` always produces the same prompt,
    so prompt caching works.
    """
    # Project state as sorted/indented JSON — deterministic.
    state_json = json.dumps(
        state.model_dump(),
        sort_keys=True,
        indent=2,
        default=str,
    )

    # Tool name + description summary (full schemas are passed via `tools`).
    tool_lines = []
    for t in TOOL_SCHEMAS:
        tool_lines.append(f"- {t['name']}: {t['description'].splitlines()[0]}")
    tool_summary = "\n".join(tool_lines)

    return "\n\n".join([
        _SYSTEM_PREAMBLE,
        "## Project state\n```json\n" + state_json + "\n```",
        IR_MODEL_SUMMARY,
        "## Available tools\n" + tool_summary,
        TOOL_USAGE_GUIDE,
    ])


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

# Re-exports for backward compatibility (Wave 3.2: moved to tool_executor.py).
# The ``_execute_agent_tool`` and ``_execute_trigger_render`` names are
# the historical in-process entry points; the canonical implementations
# now live in ``tool_executor.py`` so the agent loop and the TS-extension
# bridge cannot drift on tool dispatch. The re-export is placed in this
# section (mid-file) so it sits next to the ``_execute_tool`` dispatcher
# that uses the symbols; the ``noqa: E402`` directive acknowledges that
# ruff prefers top-of-file imports. Symbols are underscore-prefixed
# because the canonical public surface uses these names. ``ToolNotFound``
# is re-exported for callers that previously imported it from this module.
import inspect  # noqa: E402, I001
from .tool_executor import (  # noqa: E402, F401
    ToolNotFound,
    execute_tool as _execute_agent_tool,
    execute_trigger_render as _execute_trigger_render,
)


def _resolve_project_path(project_id: str) -> Path | None:
    """Resolve a project_id to a Path. Returns None if not found."""
    # Re-use the registry's resolver (private but stable).
    return projects_mod._resolve_project_by_id(project_id)


async def _execute_tool(name: str, args: dict[str, Any], project_path: Path) -> dict[str, Any]:
    """Dispatch a tool call. ``trigger_render`` is server-side; the rest
    live in ``open_edit.agent.tools``.
    """
    if name == "trigger_render":
        res = _execute_trigger_render(args, project_path)
        if inspect.isawaitable(res):
            return await res
        return res
    res = _execute_agent_tool(name, args, project_path)
    if inspect.isawaitable(res):
        return await res
    return res


# ---------------------------------------------------------------------------
# Visual verification helpers (v1.5)
# ---------------------------------------------------------------------------

def _render_failure_source(error_msg: str) -> str:
    """Map a render error string to a ``verdict_source`` value."""
    if "render_failed" in error_msg:
        return "render_failed"
    if "no_video_stream" in error_msg:
        return "no_video_stream"
    if "frame_extraction_failed" in error_msg:
        return "frame_extraction_failed"
    if "timeout" in error_msg:
        return "timeout"
    if "empty_render" in error_msg or "render_invalid" in error_msg:
        return "empty_render"
    return "render_failed"


def _build_verification_result(
    *,
    render_id: str,
    render_path: str,
    outcome: str,
    verdict_source: str,
    render_count: int,
    max_renders: int,
) -> dict[str, Any]:
    """Build a single ``verification_result`` AgentEvent."""
    return {
        "type": "verification_result",
        "render_id": render_id,
        "render_path": render_path,
        "outcome": outcome,
        "verdict_source": verdict_source,
        "render_count": render_count,
        "max_renders": max_renders,
    }


async def _maybe_verify_render(
    result: dict[str, Any],
    project_path: Path,
    render_count: int,
    cfg: dict[str, Any],
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any] | None]:
    """Run the verification stage for one ``trigger_render`` result.

    Returns ``(events, augmented_result, pending)``:
    - ``events``: AgentEvents to yield in order.
    - ``augmented_result``: the tool result the LLM sees.
    - ``pending``: state to track across the next LLM response so the
      LLM's verdict can be parsed. ``None`` for terminal paths.
    """
    events: list[dict[str, Any]] = []
    render_id = result.get("render_id", "render_unknown")
    output_path = result.get("output_path", "")
    mode = result.get("mode", "proxy")
    max_renders = cfg["max_renders"]

    if result.get("no_change"):
        events.append(_build_verification_result(
            render_id=render_id,
            render_path=output_path,
            outcome="skipped",
            verdict_source="no_change",
            render_count=render_count,
            max_renders=max_renders,
        ))
        return events, result, None

    if "error" in result:
        events.append(_build_verification_result(
            render_id=render_id,
            render_path=output_path,
            outcome="failed",
            verdict_source=_render_failure_source(result["error"]),
            render_count=render_count,
            max_renders=max_renders,
        ))
        return events, result, None

    mp4_path = Path(output_path)
    if not output_path or not mp4_path.exists() or mp4_path.stat().st_size == 0:
        invalid = visual_verify.build_failure_tool_result(
            "empty_render", render_id=render_id, path=output_path,
        )
        events.append(_build_verification_result(
            render_id=render_id,
            render_path=output_path,
            outcome="failed",
            verdict_source="empty_render",
            render_count=render_count,
            max_renders=max_renders,
        ))
        return events, invalid, None

    try:
        duration_s = await asyncio.to_thread(_probe_duration, mp4_path)
    except Exception:
        invalid = visual_verify.build_failure_tool_result(
            "no_video_stream", render_id=render_id, detail=str(output_path),
        )
        events.append(_build_verification_result(
            render_id=render_id,
            render_path=output_path,
            outcome="failed",
            verdict_source="no_video_stream",
            render_count=render_count,
            max_renders=max_renders,
        ))
        return events, invalid, None

    frames_ts = visual_verify.sample_frames(duration_s, override_count=cfg["frames"])
    model_id = os.environ.get("OPEN_EDIT_LLM_MODEL", "minimax-m3")
    cap = visual_verify.model_capability(model_id)
    supports_images = bool(cap.get("supports_images", False))

    events.append({
        "type": "verification_started",
        "render_id": render_id,
        "render_path": output_path,
        "frame_count": cfg["frames"],
        "stage": "sampling",
    })

    if not supports_images:
        events.append(_build_verification_result(
            render_id=render_id,
            render_path=output_path,
            outcome="skipped",
            verdict_source="text_only_model",
            render_count=render_count,
            max_renders=max_renders,
        ))
        augmented = visual_verify.build_verification_tool_result(
            {"render_id": render_id, "output_path": output_path, "duration_s": duration_s},
            [], cap, mode,
        )
        return events, augmented, None

    events.append({
        "type": "verification_started",
        "render_id": render_id,
        "render_path": output_path,
        "frame_count": len(frames_ts),
        "stage": "encoding",
    })

    tmpdir = Path(tempfile.mkdtemp(prefix="oe_verify_"))
    try:
        frames: list[dict[str, Any]] = []
        for ts in frames_ts:
            if should_cancel and should_cancel():
                events.append(_build_verification_result(
                    render_id=render_id,
                    render_path=output_path,
                    outcome="skipped",
                    verdict_source="user_cancelled",
                    render_count=render_count,
                    max_renders=max_renders,
                ))
                fail = visual_verify.build_failure_tool_result(
                    "frame_extraction_failed",
                    render_id=render_id,
                    detail="cancelled by user",
                )
                return events, fail, None
            frame_path = tmpdir / f"frame_{int(ts * 1000)}.jpg"
            try:
                await asyncio.to_thread(
                    visual_verify.encode_jpeg,
                    mp4_path,
                    frame_path,
                    cfg["max_edge_px"],
                    cfg["jpeg_quality"],
                    cfg["max_image_bytes"],
                )
            except Exception as exc:
                events.append(_build_verification_result(
                    render_id=render_id,
                    render_path=output_path,
                    outcome="failed",
                    verdict_source="frame_extraction_failed",
                    render_count=render_count,
                    max_renders=max_renders,
                ))
                fail = visual_verify.build_failure_tool_result(
                    "frame_extraction_failed", render_id=render_id, detail=str(exc),
                )
                return events, fail, None
            with frame_path.open("rb") as f:
                data = base64.b64encode(f.read()).decode("ascii")
            frames.append({
                "mimeType": "image/jpeg",
                "data": data,
                "t_seconds": ts,
            })

        events.append({
            "type": "verification_started",
            "render_id": render_id,
            "render_path": output_path,
            "frame_count": len(frames),
            "stage": "ready",
        })

        render_output = {
            "render_id": render_id,
            "output_path": output_path,
            "duration_s": duration_s,
        }
        augmented = visual_verify.build_verification_tool_result(
            render_output, frames, cap, mode,
        )
        pending = {
            "render_id": render_id,
            "output_path": output_path,
            "render_count": render_count,
            "max_renders": max_renders,
            "supports_images": supports_images,
            "verdict": "unknown",
            "notes": "",
        }
        return events, augmented, pending
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _build_tool_result_message(
    tu_id: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Build the ``tool_result`` message for the conversation history.

    When the result carries verification frames, the content is a list
    of content blocks (text summary + image blocks) so the LLM can
    actually see the frames.
    """
    verification = result.get("verification") or {}
    frames = verification.get("frames") or []
    if frames:
        text_summary = json.dumps(result, default=str)
        blocks: list[dict[str, Any]] = [{"type": "text", "text": text_summary}]
        for frame in frames:
            blocks.append({
                "type": "image",
                "data": frame["data"],
                "mimeType": frame.get("mimeType", "image/jpeg"),
            })
        content: Any = blocks
    else:
        content = json.dumps(result, default=str)
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": tu_id,
                "content": content,
            }
        ],
    }


def _make_slim_history(
    history: list[dict[str, Any]],
    pending: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Build the slim LLM-facing view of ``history``."""
    if pending is None:
        return visual_verify.prune_images(list(history))
    return visual_verify.prune_images(
        list(history),
        last_verdict=(
            pending["render_id"],
            pending.get("verdict", "unknown"),
            pending.get("supports_images", False),
            pending.get("notes", ""),
        ),
    )


# ---------------------------------------------------------------------------
# The agent loop
# ---------------------------------------------------------------------------

async def run_agent_turn(
    project_id: str,
    user_message: str,
    conversation_history: list[dict[str, Any]],
    conv_id: str | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> AsyncIterator[AgentEvent]:
    """Run one full agent turn (user message -> final assistant text).

    Yields :class:`AgentEvent` dicts as the turn progresses. The caller
    is expected to iterate this generator and forward events to the
    client (e.g. over a WebSocket).

    The ``conversation_history`` list is mutated in place — the user
    message and the assistant's response (including tool calls and tool
    results) are appended. If ``conv_id`` is provided, each new message
    is also appended to ``.open_edit/conversations/<conv_id>.jsonl``.

    ``should_cancel`` is an optional callback used by the verification
    stage to abort in-flight ffmpeg work when the WebSocket disconnects.

    The loop continues until the LLM returns ``end_turn`` or hits a
    safety cap (``MAX_AGENT_ITERATIONS``).
    """
    # Resolve project + state
    try:
        state = await projects_mod.get_project_state(project_id)
    except KeyError as exc:
        yield {"type": "error", "message": str(exc)}
        yield {"type": "done", "stop_reason": "error"}
        return

    project_path = _resolve_project_path(project_id)
    if project_path is None:
        yield {"type": "error", "message": f"project not found: {project_id}"}
        yield {"type": "done", "stop_reason": "error"}
        return

    system_prompt = _build_system_prompt(state)

    # Append the user message to history
    user_msg: dict[str, Any] = {"role": "user", "content": user_message}
    conversation_history.append(user_msg)
    if conv_id:
        append_to_conversation(project_id, conv_id, user_msg)

    # v1.4 P1-3: cost tracking. The previous session cumulative
    # cost is loaded from the sidecar JSON once at turn start.
    # The agent loop aggregates per-call ``usage`` events into a
    # turn total and emits a single ``cost_update`` after the
    # final ``done``. Persistence happens off-loop via
    # ``asyncio.to_thread`` so the WS stays responsive.
    cost_state = _load_cost_state(project_path) if conv_id else {}
    previous_session_cost = 0.0
    if conv_id and conv_id in cost_state:
        try:
            previous_session_cost = float(
                cost_state[conv_id].get("session_cost_usd", 0.0)
            )
        except (TypeError, ValueError):
            previous_session_cost = 0.0
    turn_tokens = 0
    turn_cost_usd = 0.0
    # The source for the cost_update: highest-priority non-"unavailable"
    # source seen in this turn. Defaults to "unavailable" so a turn
    # that yields zero ``usage`` events (rare) still produces a
    # well-formed cost_update.
    best_source_priority = _SOURCE_PRIORITY["unavailable"]
    best_source = "unavailable"

    cfg = get_visual_verify_config()
    verify_active = cfg["enabled"] and not is_verify_disabled(project_path)
    turn_render_count = 0
    pending_verification: dict[str, Any] | None = None

    # v1.6 polish: the LLM provider doesn't change between iterations of
    # the same turn (provider switching mid-turn isn't supported). Resolve
    # it once here so we don't re-read ``OPEN_EDIT_LLM_PROVIDER`` on every
    # loop iteration. The pi path needs this flag because pi's extension
    # has ALREADY executed every tool call by the time we see the
    # ``tool_result`` event; we must NOT re-execute locally.
    provider_does_tool_exec = _llm_provider() == "pi"

    def _is_cancelled() -> bool:
        if should_cancel and should_cancel():
            return True
        try:
            task = asyncio.current_task()
            if task and hasattr(task, "cancelling") and task.cancelling() > 0:
                return True
        except Exception:
            pass
        return False

    # Main loop
    for _ in range(MAX_AGENT_ITERATIONS):
        if _is_cancelled():
            yield {"type": "done", "stop_reason": "cancelled"}
            return

        # Stream the LLM
        current_text_parts: list[str] = []
        tool_use_blocks: list[dict[str, Any]] = []
        tool_results_by_name: dict[str, Any] = {}  # filled by pi provider
        stop_reason = "end_turn"

        try:
            async for raw_event in stream_chat(
                messages=_make_slim_history(conversation_history, pending_verification),
                tools=TOOL_SCHEMAS,
                system=system_prompt,
                session_id=conv_id,
                project_path=str(project_path),
            ):
                if _is_cancelled():
                    yield {"type": "done", "stop_reason": "cancelled"}
                    return
                # Wave 3.3: normalize through the StreamEvent contract so
                # every consumer below can rely on ``event["type"]`` being
                # present and the variant payload fields having safe
                # defaults. ``_coerce_event`` raises on events missing
                # ``type``; everything else is filled in.
                event = _coerce_event(raw_event)
                etype = event["type"]
                if etype == "text_delta":
                    text = event.get("text", "")
                    if text:
                        current_text_parts.append(text)
                        yield {"type": "text", "text": text}
                elif etype == "tool_use":
                    tool_use_blocks.append({
                        "type": "tool_use",
                        "id": event["id"],
                        "name": event["name"],
                        "input": event.get("input", {}),
                    })
                elif etype == "tool_result":
                    # Pi has already executed the tool; we receive the
                    # result directly from the provider. Forward it as a
                    # ``tool_result`` event and stash it for the next
                    # LLM turn. Keyed by tool name since pi's events
                    # don't always carry the tool_use_id forward.
                    tool_results_by_name[event.get("name", "")] = event.get("result", {})
                elif etype == "usage":
                    # v1.4 P1-3: aggregate per-call cost data into
                    # the turn total. The source priority ranking
                    # ensures the cost_update reports the most
                    # informative source when a turn mixes
                    # providers.
                    try:
                        turn_tokens += int(event.get("tokens", 0) or 0)
                        turn_cost_usd += float(event.get("cost_usd", 0.0) or 0.0)
                    except (TypeError, ValueError):
                        pass
                    src = event.get("source", "unavailable")
                    if not isinstance(src, str):
                        src = "unavailable"
                    prio = _SOURCE_PRIORITY.get(src, _SOURCE_PRIORITY["unavailable"])
                    if prio < best_source_priority:
                        best_source_priority = prio
                        best_source = src
                elif etype == "error":
                    yield event
                elif etype == "done":
                    stop_reason = event.get("stop_reason", "end_turn")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # LLM/streaming failure — surface and abort. Emit a
            # cost_update with whatever we've accumulated so the
            # UI doesn't get stuck on a missing event.
            yield {"type": "error", "message": f"LLM stream error: {exc}"}
            yield {"type": "done", "stop_reason": "error"}
            session_cost_usd = previous_session_cost + turn_cost_usd
            yield {
                "type": "cost_update",
                "turn_tokens": turn_tokens,
                "turn_cost_usd": round(turn_cost_usd, 9),
                "session_cost_usd": round(session_cost_usd, 9),
                "source": best_source,
            }
            if conv_id:
                cost_state[conv_id] = {
                    "session_cost_usd": session_cost_usd,
                    "source": best_source,
                    "last_turn_cost_usd": turn_cost_usd,
                }
                asyncio.create_task(
                    _save_cost_state_async(project_path, dict(cost_state))
                )
            return

        if pending_verification is not None:
            verdict = visual_verify.parse_verdict("".join(current_text_parts))
            if tool_use_blocks:
                outcome = "iterate"
            elif verdict["verdict"] == "pass":
                outcome = "pass"
            else:
                outcome = "uncertain"
            yield _build_verification_result(
                render_id=pending_verification["render_id"],
                render_path=pending_verification["output_path"],
                outcome=outcome,
                verdict_source=verdict["source"],
                render_count=pending_verification["render_count"],
                max_renders=pending_verification["max_renders"],
            )
            pending_verification = None

        # Build the assistant message
        assistant_content: list[dict[str, Any]] = []
        if current_text_parts:
            assistant_content.append({
                "type": "text",
                "text": "".join(current_text_parts),
            })
        assistant_content.extend(tool_use_blocks)

        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": assistant_content,
        }
        conversation_history.append(assistant_msg)
        if conv_id:
            append_to_conversation(project_id, conv_id, assistant_msg)

        # No tool calls -> turn is done. Emit the cost_update
        # AFTER ``done`` (per the brief) and persist the new
        # session cumulative to the sidecar JSON (off-loop).
        if not tool_use_blocks:
            yield {"type": "done", "stop_reason": stop_reason}
            session_cost_usd = previous_session_cost + turn_cost_usd
            yield {
                "type": "cost_update",
                "turn_tokens": turn_tokens,
                "turn_cost_usd": round(turn_cost_usd, 9),
                "session_cost_usd": round(session_cost_usd, 9),
                "source": best_source,
            }
            if conv_id:
                cost_state[conv_id] = {
                    "session_cost_usd": session_cost_usd,
                    "source": best_source,
                    "last_turn_cost_usd": turn_cost_usd,
                }
                # Fire-and-forget write; the cost_update has
                # already been yielded so the user sees the
                # number immediately. If the write fails the
                # next turn will reconcile from the in-memory
                # state we just stashed here.
                asyncio.create_task(
                    _save_cost_state_async(project_path, dict(cost_state))
                )
            return

        # Execute tool calls. v1.5: reorder so mutations run before
        # ``trigger_render``, and only the last ``trigger_render`` in a
        # batch is executed (pi may emit several in one turn; the
        # first ones are short-circuited).
        tool_result_messages: list[dict[str, Any]] = []
        mutations = [tu for tu in tool_use_blocks if tu["name"] != "trigger_render"]
        trigger_renders = [tu for tu in tool_use_blocks if tu["name"] == "trigger_render"]

        for tu in mutations:
            if _is_cancelled():
                yield {"type": "done", "stop_reason": "cancelled"}
                return
            tool_name = tu["name"]
            tool_input = dict(tu.get("input", {}))
            if "project_id" not in tool_input and tool_name != "search_assets":
                tool_input["project_id"] = project_id
            yield {"type": "tool_start", "name": tool_name, "input": tool_input}
            try:
                # Mutations are dispatched locally regardless of provider
                # — the pi extension only pre-executes the slow
                # ``trigger_render``; mutation tools (add_clip etc.) are
                # quick edit-graph updates that the agent loop runs itself.
                res = _execute_tool(tool_name, tool_input, project_path)
                if inspect.isawaitable(res):
                    result = await res
                else:
                    result = res
                yield {"type": "tool_result", "name": tool_name, "result": result}
                tool_result_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tu["id"],
                            "content": json.dumps(result, default=str),
                        }
                    ],
                })
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                err_msg = f"tool '{tool_name}' failed: {exc}"
                yield {"type": "error", "message": err_msg}
                tool_result_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tu["id"],
                            "content": json.dumps({"error": err_msg}),
                        }
                    ],
                })

        if trigger_renders:
            if _is_cancelled():
                yield {"type": "done", "stop_reason": "cancelled"}
                return
            tu = trigger_renders[-1]
            tool_name = tu["name"]
            tool_input = dict(tu.get("input", {}))
            if "project_id" not in tool_input and tool_name != "search_assets":
                tool_input["project_id"] = project_id
            yield {"type": "tool_start", "name": tool_name, "input": tool_input}
            try:
                if provider_does_tool_exec:
                    result = tool_results_by_name.get(tool_name, {"status": "ok"})
                else:
                    res = _execute_tool(tool_name, tool_input, project_path)
                    if inspect.isawaitable(res):
                        result = await res
                    else:
                        result = res
                yield {"type": "tool_result", "name": tool_name, "result": result}
                if isinstance(result, dict):
                    output_path = result.get("output_path", "")
                    mode = result.get("mode", "proxy")
                    if output_path:
                        yield {"type": "render", "path": output_path, "mode": mode}

                if verify_active:
                    turn_render_count += 1
                    if turn_render_count > cfg["max_renders"]:
                        capped = visual_verify.build_failure_tool_result(
                            "render_capped",
                            render_id=result.get("render_id", "render_unknown"),
                            cap=cfg["max_renders"],
                            render_count=turn_render_count,
                        )
                        yield _build_verification_result(
                            render_id=result.get("render_id", "render_unknown"),
                            render_path=output_path,
                            outcome="capped",
                            verdict_source="cap_reached",
                            render_count=turn_render_count,
                            max_renders=cfg["max_renders"],
                        )
                        tool_result_messages.append(
                            _build_tool_result_message(tu["id"], capped)
                        )
                    else:
                        try:
                            v_events, augmented_result, vstate = await _maybe_verify_render(
                                result, project_path, turn_render_count, cfg, should_cancel,
                            )
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:
                            v_events = [_build_verification_result(
                                render_id=result.get("render_id", "render_unknown"),
                                render_path=output_path,
                                outcome="failed",
                                verdict_source="frame_extraction_failed",
                                render_count=turn_render_count,
                                max_renders=cfg["max_renders"],
                            )]
                            augmented_result = visual_verify.build_failure_tool_result(
                                "frame_extraction_failed",
                                render_id=result.get("render_id", "render_unknown"),
                                detail=str(exc),
                            )
                            vstate = None
                        for ev in v_events:
                            yield ev
                        if vstate is not None:
                            pending_verification = vstate
                        tool_result_messages.append(
                            _build_tool_result_message(tu["id"], augmented_result)
                        )
                else:
                    tool_result_messages.append(
                        _build_tool_result_message(tu["id"], result)
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                err_msg = f"tool '{tool_name}' failed: {exc}"
                yield {"type": "error", "message": err_msg}
                tool_result_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tu["id"],
                            "content": json.dumps({"error": err_msg}),
                        }
                    ],
                })

        # Append all tool_result messages in order
        for trm in tool_result_messages:
            conversation_history.append(trm)
            if conv_id:
                append_to_conversation(project_id, conv_id, trm)

        # Loop back: LLM will be called again with the tool results.

    # Hit the iteration cap — surface a soft error and stop.
    # Also emit the cost_update so the user sees how much this
    # runaway turn cost; persist the cumulative as usual.
    yield {
        "type": "error",
        "message": f"agent hit the {MAX_AGENT_ITERATIONS}-iteration cap without finishing.",
    }
    yield {"type": "done", "stop_reason": "max_iterations"}
    session_cost_usd = previous_session_cost + turn_cost_usd
    yield {
        "type": "cost_update",
        "turn_tokens": turn_tokens,
        "turn_cost_usd": round(turn_cost_usd, 9),
        "session_cost_usd": round(session_cost_usd, 9),
        "source": best_source,
    }
    if conv_id:
        cost_state[conv_id] = {
            "session_cost_usd": session_cost_usd,
            "source": best_source,
            "last_turn_cost_usd": turn_cost_usd,
        }
        asyncio.create_task(
            _save_cost_state_async(project_path, dict(cost_state))
        )
