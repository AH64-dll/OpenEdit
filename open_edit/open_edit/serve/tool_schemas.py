"""Hand-written function-calling schemas for the Open Edit agent tools.

These schemas are NOT auto-generated. Each one is a hand-tuned JSON Schema
matching the actual ``args: dict`` shape that the corresponding function in
``open_edit.agent.tools`` expects. Keep them in sync with the tool
docstrings when the underlying tools change.

The 14 individual tools from v1.x have been consolidated into **4 pillar
tools** (Plan D, pillar-tool-consolidation):

- ``query_project`` — 5 read-only queries
- ``edit_project`` — all mutations + creative generation
- ``run_script`` — sandboxed Python (renamed from ``run_python``)
- ``trigger_render`` — server-side render (unchanged)

Each schema follows the Anthropic tools shape::

    {
        "name": str,
        "description": str,
        "input_schema": { JSON Schema }
    }
"""
from __future__ import annotations

from typing import Any

from open_edit.serve import tool_registry
from open_edit.serve.tool_registry import (
    TOOL_REGISTRY,
    build_tool_schemas,
    validate_tool_args,
)

# ---------------------------------------------------------------------------
# Pillar tool schemas (generated from the Pydantic registry)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = build_tool_schemas()


# Convenience lookup
TOOL_BY_NAME: dict[str, dict[str, Any]] = {t["name"]: t for t in TOOL_SCHEMAS}


def get_tool_schema(name: str) -> dict[str, Any] | None:
    """Return the schema for a tool by name, or None if unknown."""
    return TOOL_BY_NAME.get(name)


# ---------------------------------------------------------------------------
# "When to use each tool" guide — embedded in the system prompt
# ---------------------------------------------------------------------------

TOOL_USAGE_GUIDE = """\
# Tool usage guide

You have 4 tools available. Use them in this order of priority:

## 1. query_project (preferred first)
Use this for ALL read-only queries about the project:
- "list_assets" → list all assets
- "get_pending_notes" → get pending review notes
- "get_style_profile" → get the project's style profile
- "analyze_narrative" → analyze narrative structure of assets
- "search_assets" → search external asset libraries

## 2. edit_project (preferred for mutations)
Use this for ALL project edits:
- Operations are APPLIED IMMEDIATELY
- For creative suggestions (SFX, music, visuals, silence cuts), use the "generate" parameter
- Generated ops are returned for review; commit them with operation="apply_generated_ops"

## 3. run_script (only when edit_project can't do it)
Write Python that calls the ir module. The sandbox header is auto-injected.
For complex multi-step edits that can't be expressed as a single edit_project operation.

## 4. trigger_render (when you need to see the result)
Render the current timeline to a video file for preview or verification.
"""


# ---------------------------------------------------------------------------
# IR op model summary — also embedded in the system prompt
# ---------------------------------------------------------------------------

IR_MODEL_SUMMARY = """\
## Open Edit IR (intermediate representation) summary

The edit graph is an **append-only log of ops** stored in
``edit_graph.db`` (table ``edits``). Every op has these base fields:
``edit_id, parent_id, kind, author, timestamp, status, sequence_num, payload``.
Status is one of ``applied | reverted | superseded``. To "modify" an op,
you add a new op that supersedes it (via ``parent_id`` linking).

There are **24 concrete op kinds** in ``open_edit.ir.types``. The
``kind`` field is the operation class name in snake_case. The full list:

**Clip ops** (manage clips on tracks):
- ``add_clip`` — add a clip from an asset. Payload: ``{asset_hash, track_id, position_sec, in_point_sec, out_point_sec}``.
- ``remove_clip`` — remove a clip by op_id. Payload: ``{clip_id}``.
- ``move_clip`` — move a clip to a new position. Payload: ``{clip_id, new_position_sec, new_track_id?}``.
- ``trim_clip`` — change in/out points. Payload: ``{clip_id, new_in_sec, new_out_sec}``.
- ``slip_clip`` — slide source window without changing clip length. Payload: ``{clip_id, delta_sec}``.
- ``ripple_delete_clip`` — remove a clip and shift subsequent clips. Payload: ``{clip_id}``.
- ``change_clip_speed`` — retime. Payload: ``{clip_id, new_speed}``.
- ``split_clip`` — split a clip at a position. Payload: ``{clip_id, split_at_sec}``.
- ``replace_clip_source`` — point a clip at a different asset. Payload: ``{clip_id, new_asset_hash}``.
- ``set_clip_speed_ramp`` — variable speed. Payload: ``{clip_id, ramp_points[]}``.

**Transition ops**:
- ``add_transition`` — add a transition between two clips. Payload: ``{from_clip_id, to_clip_id, transition_type, duration_sec}``.
- ``remove_transition`` — remove a transition. Payload: ``{transition_id}``.
- ``set_transition_property`` — change a transition's params. Payload: ``{transition_id, property, value}``.

**Effect ops**:
- ``add_effect`` — add an effect to a clip or the timeline. Payload: ``{target_clip_id?, effect_type, params}``.
- ``remove_effect`` — remove an effect. Payload: ``{effect_id}``.
- ``set_effect_param`` — change a single effect param. Payload: ``{effect_id, param, value}``.
- ``set_keyframe`` — set a keyframe. Payload: ``{effect_id, time_sec, value}``.
- ``remove_keyframe`` — remove a keyframe. Payload: ``{keyframe_id}``.

**Audio ops**:
- ``set_audio_gain`` — change clip volume. Payload: ``{clip_id, gain_db}``.
- ``normalize_audio`` — normalize audio. Payload: ``{clip_id, target_dbfs}``.

**Grouping ops**:
- ``group_edits`` — group ops into an atomic block. Payload: ``{edit_ids[]}``.
- ``ungroup_edits`` — dissolve a group. Payload: ``{group_id}``.

**Escape hatches**:
- ``raw_mlt_xml`` — paste raw MLT XML. Payload: ``{xml, scope}``.
- ``free_form_code`` — embed Python code (the result of ``run_python``). Payload: ``{code, project_id, parent_op_id}``.

**Other ops** (less common, mainly for migrations and power users):
- ``undo`` — revert a previous op. Payload: ``{op_id}``.

**Common fields** every op carries (inherited from the ``Operation`` base):
``edit_id`` (UUID), ``parent_id`` (UUID of the op this one descends from;
``None`` for root ops), ``author`` (e.g. ``"agent"``, ``"user"``),
``timestamp`` (ISO 8601 string), ``status``, ``sequence_num`` (auto-assigned
by ``EditGraphStore``), ``payload`` (JSON blob of op-specific data).

**To build an op programmatically**, use ``open_edit.ir.api.IR``. Each
op type has a method on the ``IR`` class (e.g. ``ir.add_clip(...)``,
``ir.add_effect(...)``, ``ir.slip_clip(...)``). The agent's ``run_script``
tool gives you access to ``IR`` and the op classes inside the bwrap
sandbox.

**Review notes** are NOT ops. They live in ``notes.db`` (table ``notes``)
with fields ``note_id, project_id, anchor_type, anchor, text, source,
status, created_at, processed_at, commit_token, resulting_op_ids``.
``anchor`` is JSON-encoded (e.g. ``'{"t_start": 3.2, "t_end": 3.5}'`` for a
timestamp anchor). Use ``add_marker`` (via ``edit_project``) to create
agent-sourced notes.

**Style profile** is a separate key/value store pinned at the project
level. Pinned values override inferred defaults when generating new ops.
Use ``edit_project`` with ``operation=\"set_pinned_value\"`` to pin,
and ``query_project`` with ``query=\"get_style_profile\"`` to read the
slice for a given op kind.
"""
