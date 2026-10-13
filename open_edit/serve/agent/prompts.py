"""System prompt construction (DETERMINISTIC — see hard requirement #5)."""
from __future__ import annotations

import json
import os

from open_edit.kernel.tool_schemas import TOOL_SCHEMAS
from open_edit.mcp.skills import mcp_instructions

from .. import projects as projects_mod

_SYSTEM_PREAMBLE = (
    "You edit the selected video project. Follow the user's creative direction; "
    "choose your own editing strategy and keep responses concise. "
    "Use list_assets to discover media. " + mcp_instructions()
)


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
        f"Pending notes: {getattr(state, 'pending_notes_count', len(notes))}",
        f"Timeline status: {getattr(state, 'timeline_status', 'valid')}",
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
    if state_summary_only or supports_tools:
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
        ])

    # Schemas already travel in the tools parameter; never duplicate them.
    return "\n\n".join([
        _SYSTEM_PREAMBLE,
        state_block,
        "## Available tools\n" + ", ".join(t['name'] for t in TOOL_SCHEMAS),
    ])
