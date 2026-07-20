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

import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Literal, TypedDict

from . import projects as projects_mod
from .llm import stream_chat
from .tool_schemas import (
    IR_MODEL_SUMMARY,
    TOOL_SCHEMAS,
    TOOL_USAGE_GUIDE,
)


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

class AgentEvent(TypedDict):
    """One event yielded by ``run_agent_turn``.

    Variants:
    - ``{"type": "text", "text": "..."}``  — assistant text delta
    - ``{"type": "tool_start", "name": "...", "input": {...}}``
    - ``{"type": "tool_result", "name": "...", "result": {...}}``
    - ``{"type": "render", "path": "...", "mode": "proxy"|"final"}`
    - ``{"type": "error", "message": "..."}`
    - ``{"type": "done", "stop_reason": "..."}``  — final event of the turn
    """
    type: Literal["text", "tool_start", "tool_result", "render", "error", "done"]


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

def _resolve_project_path(project_id: str) -> Path | None:
    """Resolve a project_id to a Path. Returns None if not found."""
    # Re-use the registry's resolver (private but stable).
    return projects_mod._resolve_project_by_id(project_id)


def _execute_agent_tool(name: str, args: dict[str, Any], project_path: Path) -> dict[str, Any]:
    """Execute one of the 12 tools in ``open_edit.agent.tools``.

    Returns the tool's dict result. Raises if the tool module/function is
    missing or if the tool itself raises.
    """
    import open_edit.agent.tools as tools_mod  # type: ignore

    fn = getattr(tools_mod, name, None)
    if fn is None or not callable(fn):
        raise RuntimeError(f"tool not found in open_edit.agent.tools: {name}")

    return fn(args, str(project_path))


def _execute_trigger_render(args: dict[str, Any], project_path: Path) -> dict[str, Any]:
    """Server-side virtual tool: shell out to ``open_edit render``."""
    mode = (args.get("mode") or "proxy").lower()
    if mode not in ("proxy", "final"):
        mode = "proxy"

    try:
        proc = subprocess.run(
            ["open_edit", "render", "--mode", mode],
            cwd=str(project_path),
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("`open_edit` CLI not found on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"`open_edit render --mode {mode}` failed (exit {exc.returncode}): "
            f"{exc.stderr.strip() or exc.stdout.strip()}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"render timed out after {exc.timeout}s") from exc

    # The CLI prints the output path on the last non-empty line of stdout.
    last_line = ""
    for line in reversed(proc.stdout.splitlines()):
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

    return {
        "mode": mode,
        "output_path": output_path,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _execute_tool(name: str, args: dict[str, Any], project_path: Path) -> dict[str, Any]:
    """Dispatch a tool call. ``trigger_render`` is server-side; the rest
    live in ``open_edit.agent.tools``.
    """
    if name == "trigger_render":
        return _execute_trigger_render(args, project_path)
    return _execute_agent_tool(name, args, project_path)


# ---------------------------------------------------------------------------
# The agent loop
# ---------------------------------------------------------------------------

async def run_agent_turn(
    project_id: str,
    user_message: str,
    conversation_history: list[dict[str, Any]],
    conv_id: str | None = None,
) -> AsyncIterator[AgentEvent]:
    """Run one full agent turn (user message -> final assistant text).

    Yields :class:`AgentEvent` dicts as the turn progresses. The caller
    is expected to iterate this generator and forward events to the
    client (e.g. over a WebSocket).

    The ``conversation_history`` list is mutated in place — the user
    message and the assistant's response (including tool calls and tool
    results) are appended. If ``conv_id`` is provided, each new message
    is also appended to ``.open_edit/conversations/<conv_id>.jsonl``.

    The loop continues until the LLM returns ``end_turn`` or hits a
    safety cap (``MAX_AGENT_ITERATIONS``).
    """
    MAX_AGENT_ITERATIONS = 10  # hard cap to prevent runaway loops

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

    # Main loop
    for _ in range(MAX_AGENT_ITERATIONS):
        # Stream the LLM
        assistant_blocks: list[dict[str, Any]] = []
        current_text_parts: list[str] = []
        tool_use_blocks: list[dict[str, Any]] = []
        tool_results_by_name: dict[str, Any] = {}  # filled by pi provider
        stop_reason = "end_turn"

        # Detect if the LLM provider is the ``pi`` subprocess driver. In that
        # case the pi extension has ALREADY executed every tool call (via
        # ``pi_bridge.py``) and streamed the results back to us as
        # ``tool_result`` events. We must NOT re-execute locally.
        from .llm import _provider as _llm_provider
        provider_does_tool_exec = _llm_provider() == "pi"

        try:
            async for event in stream_chat(
                messages=conversation_history,
                tools=TOOL_SCHEMAS,
                system=system_prompt,
                session_id=conv_id,
                project_path=str(project_path),
            ):
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
                elif etype == "done":
                    stop_reason = event.get("stop_reason", "end_turn")
        except Exception as exc:
            # LLM/streaming failure — surface and abort.
            yield {"type": "error", "message": f"LLM stream error: {exc}"}
            yield {"type": "done", "stop_reason": "error"}
            return

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

        # No tool calls -> turn is done
        if not tool_use_blocks:
            yield {"type": "done", "stop_reason": stop_reason}
            return

        # Execute each tool call and emit events. If the provider is
        # ``pi``, the tool has already been run by the extension and we
        # just forward the result we captured in ``tool_results_by_name``.
        tool_result_messages: list[dict[str, Any]] = []
        for tu in tool_use_blocks:
            tool_name = tu["name"]
            tool_input = tu.get("input", {})
            yield {"type": "tool_start", "name": tool_name, "input": tool_input}

            if provider_does_tool_exec:
                # Use the result that pi's extension already produced.
                result = tool_results_by_name.get(tool_name, {"status": "ok"})
                yield {"type": "tool_result", "name": tool_name, "result": result}

                # Special-case render: also emit a top-level render event
                # so the client can immediately react to it.
                if tool_name == "trigger_render" and isinstance(result, dict):
                    output_path = result.get("output_path", "")
                    mode = result.get("mode", "proxy")
                    if output_path:
                        yield {"type": "render", "path": output_path, "mode": mode}

                tool_result_content = json.dumps(result, default=str)
            else:
                try:
                    result = _execute_tool(tool_name, tool_input, project_path)
                    yield {"type": "tool_result", "name": tool_name, "result": result}

                    if tool_name == "trigger_render" and isinstance(result, dict):
                        output_path = result.get("output_path", "")
                        mode = result.get("mode", "proxy")
                        if output_path:
                            yield {"type": "render", "path": output_path, "mode": mode}

                    tool_result_content = json.dumps(result, default=str)
                except Exception as exc:
                    err_msg = f"tool '{tool_name}' failed: {exc}"
                    yield {"type": "error", "message": err_msg}
                    tool_result_content = json.dumps({"error": err_msg})

            tool_result_messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tu["id"],
                        "content": tool_result_content,
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
    yield {
        "type": "error",
        "message": f"agent hit the {MAX_AGENT_ITERATIONS}-iteration cap without finishing.",
    }
    yield {"type": "done", "stop_reason": "max_iterations"}
