"""Tool defs for track-level effect operations.

Phase 4 Task 7: repointed to IR.add_effect (target_kind='track') +
read-back via derive_timeline.
"""
from __future__ import annotations

from .project import ToolDef


ADD_EFFECT_TO_TRACK = ToolDef(
    name="pyagent_add_effect_to_track",
    label="Add effect to track",
    description=(
        "Add a Kdenlive effect to a track (not a clip). The effect is "
        "added as a filter on the track's tractor, so it applies to "
        "every clip on the track. Video effects cannot be added to "
        "audio tracks and vice versa."
    ),
    op="add_effect_to_track",
    is_mutating=True,
    parameters_schema={
        "track_index": {"type": "integer", "description": "0-based track index"},
        "effect_id": {"type": "string", "description": "Kdenlive effect id (e.g. 'volume', 'blur')"},
        "params": {"type": "object", "description": "Optional parameter overrides (defaults from catalog if omitted)"},
    },
    required=("track_index", "effect_id"),
)


LIST_TRACK_EFFECTS = ToolDef(
    name="pyagent_list_track_effects",
    label="List track effects",
    description=(
        "Return the effect stack of a track. Each entry includes the "
        "effect_id, enabled state, and current parameter values."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "track_index": {"type": "integer"},
        },
        "required": ["track_index"],
        "additionalProperties": False,
    },
    op="list_track_effects",
    is_mutating=False,
)


TOOLS = [ADD_EFFECT_TO_TRACK, LIST_TRACK_EFFECTS]


# --- Wrapper functions (Phase 4 Task 7) ---


def _track_id(track_index: int) -> str:
    return f"track_{int(track_index)}"


def add_effect_to_track(args: dict, project_path: str) -> dict:
    """Add an effect to a track."""
    from open_edit.agent.tools._helpers import make_ir

    ir = make_ir(project_path)
    effect_id = ir.add_effect(
        target_kind="track",
        target_id=_track_id(args["track_index"]),
        effect_type=args["effect_id"],
        params=args.get("params", {}),
    )
    return {"effect_id": effect_id}


def list_track_effects(args: dict, project_path: str) -> dict:
    """Read-back: list effects on the given track."""
    from open_edit.agent.tools._helpers import load_project
    from open_edit.ir.apply import derive_timeline

    project = load_project(project_path)
    timeline = derive_timeline(project)
    target_id = _track_id(int(args["track_index"]))
    for t in timeline.tracks:
        if t.track_id == target_id:
            return {
                "track_id": t.track_id,
                "effects": [
                    {
                        "effect_id": e.effect_id,
                        "effect_type": e.effect_type,
                        "params": e.params,
                    }
                    for e in t.effects
                ],
            }
    return {"track_id": target_id, "effects": []}
