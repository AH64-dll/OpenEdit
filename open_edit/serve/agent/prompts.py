"""System prompt construction (DETERMINISTIC — see hard requirement #5)."""
from __future__ import annotations

import json
import os

from open_edit.kernel.tool_schemas import (
    IR_MODEL_SUMMARY,
    TOOL_SCHEMAS,
    TOOL_USAGE_GUIDE,
)

from .. import projects as projects_mod

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
NEVER retry an identical failing call with identical arguments — read the
error, change something, or stop and explain. A circuit breaker aborts
the turn after repeated identical failures.
"""


_TEXT_ONLY_PREAMBLE = """\
You are the Open Edit assistant — an AI helper for the Open Edit video editor.
You operate on ONE project at a time. The user's intent is to make edits or ask questions about their project's media.

Answer the user's questions clearly, concisely, and directly. Provide advice on video editing, timeline structure, asset usage, and creative decisions.
Do NOT attempt to invoke function calls or JSON tool schemas.
"""


def _build_state_summary(state: projects_mod.ProjectState) -> str:
    """Return a brief summary of the project state (under 1KB)."""
    name = getattr(state, "name", "untitled")
    assets = getattr(state, "assets", []) or []
    timeline = getattr(state, "timeline", None)
    num_tracks = timeline.num_tracks if timeline and hasattr(timeline, "num_tracks") else 0
    notes = getattr(state, "notes", []) or []
    lines = [
        f"Project: {name}",
        f"Asset count: {len(assets)}",
        f"Track count: {num_tracks}",
        f"Pending notes: {len(notes)}",
    ]
    if notes:
        last = notes[-1]
        if isinstance(last, dict):
            lines.append(f"Last pending note: {last.get('text', '')[:80]}")
        else:
            lines.append(f"Last pending note: {str(last)[:80]}")
    return "\n".join(lines)


def _build_system_prompt(state: projects_mod.ProjectState, supports_tools: bool = True, state_summary_only: bool = False) -> str:
    """Build the system prompt.

    Deterministic: the same ``state`` always produces the same prompt,
    so prompt caching works.
    """
    if state_summary_only:
        state_json = _build_state_summary(state)
    else:
        # Project state as sorted/indented JSON — deterministic.
        state_json = json.dumps(
            state.model_dump(),
            sort_keys=True,
            indent=2,
            default=str,
        )

        max_state_chars = int(os.environ.get("OPEN_EDIT_CONTEXT_MAX_STATE_CHARS", "10000"))
        if len(state_json) > max_state_chars:
            state_json = state_json[:max_state_chars] + "\n... [state truncated]"

    state_block = "## Project state\n```\n" + state_json + "\n```"
    if not state_summary_only:
        state_block = "## Project state\n```json\n" + state_json + "\n```"

    if not supports_tools:
        return "\n\n".join([
            _TEXT_ONLY_PREAMBLE,
            state_block,
            IR_MODEL_SUMMARY,
        ])

    # Tool name + description summary (full schemas are passed via `tools`).
    tool_lines = []
    for t in TOOL_SCHEMAS:
        tool_lines.append(f"- {t['name']}: {t['description'].splitlines()[0]}")
    tool_summary = "\n".join(tool_lines)

    return "\n\n".join([
        _SYSTEM_PREAMBLE,
        state_block,
        IR_MODEL_SUMMARY,
        "## Available tools\n" + tool_summary,
        TOOL_USAGE_GUIDE,
    ])
