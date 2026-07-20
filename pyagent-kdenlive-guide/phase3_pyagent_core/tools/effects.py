"""Tool defs for effect application.

Phase 4 Task 7: bodies repointed from KdenliveFileBackend.* to
open_edit.ir.api.IR.*. Names + JSON schemas unchanged.
"""
from __future__ import annotations

from .project import ToolDef


_APPLY_DESCRIPTION = (
    "Apply an effect to a clip. effect_id must come from the catalog "
    "(use pyagent_list_catalog to look it up). params is {name: value}."
)


APPLY_EFFECT = ToolDef(
    name="pyagent_apply_effect",
    label="Apply effect",
    description=_APPLY_DESCRIPTION,
    op="apply_effect",
    is_mutating=True,
    parameters_schema={
        "clip_id": {"type": "string"},
        "effect_id": {"type": "string", "description": "catalog effect id"},
        "params": {"type": "object", "additionalProperties": True},
    },
    required=("clip_id", "effect_id"),
)


REMOVE_EFFECT = ToolDef(
    name="pyagent_remove_effect",
    label="Remove effect",
    description=(
        "Remove an effect from a clip by its index. effect_index is the "
        "0-based position in the clip's effect list. Call "
        "pyagent_get_timeline_summary first to see what effect indices "
        "exist on the clip."
    ),
    op="remove_effect",
    is_mutating=True,
    parameters_schema={
        "clip_id": {"type": "string"},
        "effect_index": {"type": "integer", "minimum": 0},
    },
    required=("clip_id", "effect_index"),
)


GET_EFFECT_PARAM = ToolDef(
    name="pyagent_get_effect_param",
    label="Get effect param",
    description=(
        "Read the current value of an effect parameter on a clip. "
        "For keyframable params, also returns the parsed keyframes list. "
        "WARNING: this does NOT validate that the clip's effect stack "
        "matches the catalog; the returned 'effect_id' is read from the "
        "kdenlive:id property in the file. To change a param's value, "
        "use set_effect_param."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "clip_id": {"type": "string", "description": "Target clip id"},
            "effect_index": {"type": "integer", "description": "0-based effect index in the clip's filter list"},
            "param_name": {"type": "string", "description": "Parameter name (e.g. 'opacity', 'level')"},
        },
        "required": ["clip_id", "effect_index", "param_name"],
        "additionalProperties": False,
    },
    op="get_effect_param",
    is_mutating=False,
)

SET_EFFECT_PARAM = ToolDef(
    name="pyagent_set_effect_param",
    label="Set effect param",
    description=(
        "Set an effect parameter to a static value. "
        "WARNING: if the param is keyframable, this REPLACES the entire "
        "animation string. The response includes 'is_keyframable' and "
        "'previous_value' so the caller can detect the case and use "
        "set_keyframe instead. For non-keyframable params, the value is "
        "coerced to the catalog's type."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "clip_id": {"type": "string"},
            "effect_index": {"type": "integer"},
            "param_name": {"type": "string"},
            "value": {"type": "string", "description": "New value (as string; coerced to type)"},
        },
        "required": ["clip_id", "effect_index", "param_name", "value"],
        "additionalProperties": False,
    },
    op="set_effect_param",
    is_mutating=True,
)


TOOLS = [APPLY_EFFECT, REMOVE_EFFECT, GET_EFFECT_PARAM, SET_EFFECT_PARAM]


# --- Wrapper functions (Phase 4 Task 7) ---


def apply_effect(args: dict, project_path: str) -> dict:
    """Add an effect to a clip. Returns the new effect_id."""
    from open_edit.agent.tools._helpers import make_ir

    ir = make_ir(project_path)
    target_kind = args.get("target_kind", "clip")
    target_id = args.get("target_id") or args["clip_id"]
    effect_type = args.get("effect_type") or args["effect_id"]
    params = args.get("params", {})
    effect_id = ir.add_effect(
        target_kind=target_kind,
        target_id=target_id,
        effect_type=effect_type,
        params=params,
    )
    return {"effect_id": effect_id}


def remove_effect(args: dict, project_path: str) -> dict:
    """Remove an effect from a clip by index."""
    from open_edit.agent.tools._helpers import make_ir

    ir = make_ir(project_path)
    ir.remove_effect(
        clip_id=args["clip_id"],
        effect_index=args["effect_index"],
    )
    return {"status": "ok"}


def get_effect_param(args: dict, project_path: str) -> dict:
    """Read a clip effect's parameter value (and keyframes if keyframable).

    Read-back: loads the project, derives the timeline, finds the clip+effect,
    returns the param value. If the param is not found, returns a structured
    'not_found' response.
    """
    from open_edit.agent.tools._helpers import load_project
    from open_edit.ir.apply import derive_timeline

    project = load_project(project_path)
    timeline = derive_timeline(project)
    clip_id = args["clip_id"]
    effect_index = int(args["effect_index"])
    param_name = args["param_name"]
    for track in timeline.tracks:
        for clip in track.clips:
            if clip.clip_id != clip_id:
                continue
            if effect_index < 0 or effect_index >= len(clip.effects):
                return {
                    "status": "not_found",
                    "reason": f"effect_index {effect_index} out of range",
                    "effect_count": len(clip.effects),
                }
            effect = clip.effects[effect_index]
            value = effect.params.get(param_name)
            keyframes = effect.keyframes.get(param_name, [])
            return {
                "effect_id": effect.effect_id,
                "value": value,
                "is_keyframable": param_name in effect.keyframes,
                "keyframes": keyframes,
            }
    return {
        "status": "not_found",
        "reason": f"clip_id {clip_id!r} not in timeline",
    }


def set_effect_param(args: dict, project_path: str) -> dict:
    """Set an effect parameter to a static value."""
    from open_edit.agent.tools._helpers import make_ir

    ir = make_ir(project_path)
    ir.set_effect_param(
        clip_id=args["clip_id"],
        effect_index=int(args["effect_index"]),
        param_name=args["param_name"],
        value=str(args["value"]),
    )
    return {"status": "ok"}
