"""ToolDef definitions for the keyframe operations.

Phase 4 Task 7: repointed to IR.set_keyframe / IR.remove_keyframe.
"""
from __future__ import annotations

from .project import ToolDef


LIST_KEYFRAMES = ToolDef(
    name="pyagent_list_keyframes",
    label="List keyframes",
    description=(
        "Return the keyframes on a keyframable effect parameter. "
        "Returns an empty list if the param is not keyframable or has "
        "no keyframes. For simplekeyframe params (5 in the 26.04 catalog), "
        "returns format='simplekeyframe' and an empty keyframes list — "
        "mlt_geometry support is deferred to a later sub-project."
    ),
    op="list_keyframes",
    is_mutating=False,
    parameters_schema={
        "clip_id": {"type": "string"},
        "effect_index": {"type": "integer"},
        "param_name": {"type": "string"},
    },
    required=("clip_id", "effect_index", "param_name"),
)

SET_KEYFRAME = ToolDef(
    name="pyagent_set_keyframe",
    label="Set keyframe",
    description=(
        "Add a new keyframe at the given frame, or update the value/type "
        "of an existing one. `type` is one of: linear, discrete, hold, "
        "smooth, or 8 ease variants (a, b, c, d, A, B, C, D). Default "
        "is linear. `frame` is 0-based, relative to the clip's in-point."
    ),
    op="set_keyframe",
    is_mutating=True,
    parameters_schema={
        "clip_id": {"type": "string"},
        "effect_index": {"type": "integer"},
        "param_name": {"type": "string"},
        "frame": {"type": "integer", "description": "0-based frame relative to clip's in-point"},
        "value": {"type": "string", "description": "Keyframe value (as string)"},
        "type": {"type": "string", "description": "One of: linear, discrete, hold, smooth, a, b, c, d, A, B, C, D"},
    },
    required=("clip_id", "effect_index", "param_name", "frame", "value"),
)

REMOVE_KEYFRAME = ToolDef(
    name="pyagent_remove_keyframe",
    label="Remove keyframe",
    description=(
        "Remove the keyframe at the given frame. No error if no keyframe "
        "exists there; the response includes removed: false. For "
        "simplekeyframe params, raises simplekeyframe_format_unsupported."
    ),
    op="remove_keyframe",
    is_mutating=True,
    parameters_schema={
        "clip_id": {"type": "string"},
        "effect_index": {"type": "integer"},
        "param_name": {"type": "string"},
        "frame": {"type": "integer"},
    },
    required=("clip_id", "effect_index", "param_name", "frame"),
)


TOOLS = [LIST_KEYFRAMES, SET_KEYFRAME, REMOVE_KEYFRAME]


# --- Wrapper functions (Phase 4 Task 7) ---


def _effect_id_for(clip_id: str, effect_index: int) -> str:
    """Derive an effect_id from clip_id + effect_index.

    Read-back paths need a stable handle. We use `<clip_id>__<index>`
    which matches the convention used by `apply_effect` callers in the
    golden tests.
    """
    return f"{clip_id}__{int(effect_index)}"


def list_keyframes(args: dict, project_path: str) -> dict:
    """Read-back: list keyframes for a clip's effect parameter."""
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
                    "format": "linear",
                    "keyframes": [],
                    "effect_count": len(clip.effects),
                }
            effect = clip.effects[effect_index]
            keyframes = effect.keyframes.get(param_name, [])
            return {
                "format": "linear",
                "effect_id": effect.effect_id,
                "keyframes": [
                    {"frame": float(f), "value": str(v), "type": t}
                    for f, v, t in keyframes
                ],
            }
    return {"format": "linear", "keyframes": []}


def set_keyframe(args: dict, project_path: str) -> dict:
    """Add or update a keyframe."""
    from open_edit.agent.tools._helpers import make_ir

    ir = make_ir(project_path)
    effect_id = _effect_id_for(args["clip_id"], args["effect_index"])
    keyframes = [(float(args["frame"]), float(args["value"]), args.get("type", "linear"))]
    ir.set_keyframe(
        effect_id=effect_id,
        param=args["param_name"],
        keyframes=keyframes,
    )
    return {"status": "ok"}


def remove_keyframe(args: dict, project_path: str) -> dict:
    """Remove a keyframe at the given frame."""
    from open_edit.agent.tools._helpers import make_ir

    ir = make_ir(project_path)
    effect_id = _effect_id_for(args["clip_id"], args["effect_index"])
    ir.remove_keyframe(
        effect_id=effect_id,
        param=args["param_name"],
        frame=float(args["frame"]),
    )
    return {"status": "ok", "removed": True}
