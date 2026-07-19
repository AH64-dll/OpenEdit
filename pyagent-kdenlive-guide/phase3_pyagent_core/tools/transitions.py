"""Tool defs for transition operations."""
from __future__ import annotations

from .project import ToolDef


_S = {"type": "string"}


ADD_TRANSITION = ToolDef(
    name="pyagent_add_transition",
    label="Add transition",
    description=(
        "Add a transition between two adjacent clips on the same track. "
        "kind must be a transition id from the catalog (e.g. 'dissolve', 'composite', 'wipe')."
    ),
    op="add_transition",
    is_mutating=True,
    parameters_schema={
        "clip_a_id": {"type": "string", "description": "first clip's id"},
        "clip_b_id": {"type": "string", "description": "second (adjacent) clip's id"},
        "kind": {"type": "string", "description": "catalog transition id"},
        "duration_sec": {"type": "number", "minimum": 0},
    },
    required=("clip_a_id", "clip_b_id"),
)


REMOVE_TRANSITION = ToolDef(
    name="pyagent_remove_transition",
    label="Remove transition",
    description=(
        "Remove a transition by its id. Call pyagent_get_timeline_summary "
        "first to see what transition_ids exist."
    ),
    op="remove_transition",
    is_mutating=True,
    parameters_schema={
        "transition_id": _S,
    },
    required=("transition_id",),
)


SET_TRANSITION_PROPERTY = ToolDef(
    name="pyagent_set_transition_property",
    label="Set transition property",
    description=(
        "Set any one property on a transition service. Reserved names "
        "(mlt_service, id, _childid, kdenlive:id, anything starting with _) "
        "are rejected. Use for editing timing (in, out, a_track, b_track) "
        "or transition-specific params (e.g. 'geometry' for wipes)."
    ),
    op="set_transition_property",
    is_mutating=True,
    parameters_schema={
        "transition_id": _S,
        "prop_name": _S,
        "value": _S,
    },
    required=("transition_id", "prop_name", "value"),
)


TOOLS = [ADD_TRANSITION, REMOVE_TRANSITION, SET_TRANSITION_PROPERTY]
