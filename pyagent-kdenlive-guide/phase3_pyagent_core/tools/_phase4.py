"""Tool defs for the 5 new Phase 4 tools (Task 7).

The actual implementations live in `open_edit/agent/tools/*.py`. The
ToolDef metadata lives here so `all_tools()` can pick them up via the
same import pattern as the other phase3 tools.
"""
from __future__ import annotations

from .project import ToolDef


_RUN_PYTHON = ToolDef(
    name="pyagent_run_python",
    label="Run free-form Python",
    description=(
        "Run free-form Python in a sandboxed subprocess. The code can "
        "import `ir` and call IR methods (`ir.add_clip`, `ir.trim_clip`, "
        "etc.) to emit ops; the ops are persisted atomically. timeout_sec "
        "and mem_mb are hard-capped."
    ),
    op="run_python",
    is_mutating=True,
    parameters_schema={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python source code"},
            "project_id": {"type": "string"},
            "project_path": {"type": "string"},
            "parent_op_id": {"type": "string"},
            "timeout_sec": {"type": "integer", "default": 30},
            "mem_mb": {"type": "integer", "default": 512},
            "originating_note_id": {"type": "string"},
        },
        "required": ["code", "project_id", "project_path"],
        "additionalProperties": False,
    },
)

_GET_STYLE_PROFILE = ToolDef(
    name="pyagent_get_style_profile",
    label="Get style profile",
    description=(
        "Return the tag-gated slice of the global style profile for the "
        "given op_type. Confidence-gated; only categories with confidence "
        ">= 0.2 are included. Token-capped at ~250 tokens."
    ),
    op="get_style_profile",
    is_mutating=False,
    parameters_schema={
        "type": "object",
        "properties": {
            "op_type": {
                "type": "string",
                "enum": [
                    "AddTransition", "AddEffect", "SetKeyframe", "AddClip",
                    "MoveClip", "TrimClip", "RemoveClip", "SetAudioGain",
                    "NormalizeAudio", "GroupEdits", "RawMltXml", "FreeFormCode",
                ],
            },
        },
        "required": ["op_type"],
        "additionalProperties": False,
    },
)

_SET_PINNED_VALUE = ToolDef(
    name="pyagent_set_pinned_value",
    label="Set pinned value",
    description=(
        "Pin a key=value in the global style profile. Pinned values "
        "override aggregate rules (e.g. 'aspect_ratio': '9:16')."
    ),
    op="set_pinned_value",
    is_mutating=True,
    parameters_schema={
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "value": {
                "type": ["string", "number", "boolean", "array", "object", "null"],
            },
        },
        "required": ["key", "value"],
        "additionalProperties": False,
    },
)

_GET_PENDING_NOTES = ToolDef(
    name="pyagent_get_pending_notes",
    label="Get pending notes",
    description=(
        "List pending notes (timestamp / region / op anchors) for the "
        "current project. Use summary_only=True to cap token cost; the "
        "first 10 notes are returned in full, the rest are counted."
    ),
    op="get_pending_notes",
    is_mutating=False,
    parameters_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "project_path": {"type": "string"},
            "summary_only": {"type": "boolean", "default": False},
        },
        "required": ["project_id", "project_path"],
        "additionalProperties": False,
    },
)

_ADD_MARKER = ToolDef(
    name="pyagent_add_marker",
    label="Add marker (agent)",
    description=(
        "Agent-initiated marker / flag / bookmark at a specific timestamp. "
        "Writes to NotesStore with source='agent' (not an IR op)."
    ),
    op="add_marker",
    is_mutating=True,
    parameters_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "project_path": {"type": "string"},
            "t_start": {"type": "number", "minimum": 0},
            "t_end": {"type": "number", "minimum": 0},
            "text": {"type": "string"},
        },
        "required": ["project_id", "project_path", "t_start"],
        "additionalProperties": False,
    },
)


TOOLS = [
    _RUN_PYTHON,
    _GET_STYLE_PROFILE,
    _SET_PINNED_VALUE,
    _GET_PENDING_NOTES,
    _ADD_MARKER,
]
