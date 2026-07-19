"""Keyframe operations: list_keyframes, set_keyframe, remove_keyframe."""
from __future__ import annotations

from ..errors import NotFoundError, ValidationError, validation_error
from ..io import ProjectTree
from .._keyframes import (
    parse_animation_string,
    serialize_keyframes,
)


def list_keyframes(
    tree: ProjectTree,
    clip_id: str,
    effect_index: int,
    param_name: str,
) -> dict:
    """Return the keyframes on a keyframable param.

    For non-keyframable params, returns an empty keyframes list and
    format=''. For simplekeyframe params, returns an empty keyframes
    list and format='simplekeyframe' (mlt_geometry not yet supported).
    """
    from .clips_edit import _find_entry_for_clip

    track, entry, _ti = _find_entry_for_clip(tree, clip_id)
    filters = list(entry.findall("filter"))
    if effect_index < 0 or effect_index >= len(filters):
        raise NotFoundError(
            f"effect_index_out_of_range: effect_index={effect_index}, "
            f"effect_count={len(filters)}\n"
            f"fix: call get_timeline_summary to see valid indices"
        )
    filt = filters[effect_index]
    effect_id = ""
    for prop in filt.findall("property"):
        if prop.get("name") == "kdenlive:id" and prop.text:
            effect_id = prop.text
            break
    # Find the param's current value
    value = None
    for prop in filt.findall("property"):
        if prop.get("name") == param_name:
            value = prop.text or ""
            break
    if value is None:
        raise NotFoundError(
            f"param_not_found: effect '{effect_id}' (index {effect_index}) on "
            f"clip '{clip_id}' has no parameter named '{param_name}'\n"
            f"fix: call list_catalog to see valid parameter names for {effect_id}"
        )
    # Determine format from the value's structure (catalog not available here)
    if "=" in value and ";" in value:
        kfs = parse_animation_string(value)
        fmt = "animated"  # generic; catalog can refine in 2c
        keyframes = [{"frame": k.frame, "value": k.value, "type": k.type}
                     for k in kfs]
    else:
        keyframes = []
        fmt = ""
    return {
        "clip_id": clip_id,
        "effect_index": effect_index,
        "param_name": param_name,
        "format": fmt,
        "keyframes": keyframes,
    }


_TYPE_NAME_TO_CHAR = {
    "linear": "`",
    "discrete": "|",
    "hold": "!",
    "smooth": "~",
    "ease_in_a": "a", "ease_in_b": "b", "ease_in_c": "c", "ease_in_d": "d",
    "ease_out_a": "A", "ease_out_b": "B", "ease_out_c": "C", "ease_out_d": "D",
}


def _get_project_fps(tree: ProjectTree) -> float:
    try:
        profile = tree.root.find("profile")
        if profile is None:
            return 25.0
        num = float(profile.get("frame_rate_num", "25"))
        den = float(profile.get("frame_rate_den", "1"))
        return num / den if den else 25.0
    except Exception:
        return 25.0


def set_keyframe(
    tree: ProjectTree,
    clip_id: str,
    effect_index: int,
    param_name: str,
    frame: int,
    value: str,
    type: str = "linear",
) -> dict:
    """Add or update a keyframe at `frame`.

    `type` is one of: linear, discrete, hold, smooth, or the 8 ease
    variants (a, b, c, d, A, B, C, D). Default is linear.
    """
    from .clips_edit import _find_entry_for_clip

    if type not in _TYPE_NAME_TO_CHAR:
        raise validation_error(
            f"invalid_type: type={type!r} is not in the allowed set\n"
            f"fix: pass one of {sorted(_TYPE_NAME_TO_CHAR.keys())}",
        )
    type_char = _TYPE_NAME_TO_CHAR[type]
    track, entry, _ti = _find_entry_for_clip(tree, clip_id)
    filters = list(entry.findall("filter"))
    if effect_index < 0 or effect_index >= len(filters):
        raise NotFoundError(
            f"effect_index_out_of_range: effect_index={effect_index}, "
            f"effect_count={len(filters)}\n"
            f"fix: call get_timeline_summary to see valid indices"
        )
    filt = filters[effect_index]
    # Find current value
    value_prop = None
    for prop in filt.findall("property"):
        if prop.get("name") == param_name:
            value_prop = prop
            break
    if value_prop is None:
        raise NotFoundError(
            f"param_not_found: effect at index {effect_index} on clip "
            f"{clip_id!r} has no parameter named {param_name!r}\n"
            f"fix: call list_catalog to see valid parameter names"
        )
    current_str = value_prop.text or ""
    kfs = parse_animation_string(current_str)
    # Compute the clip's effective duration in frames
    from ..io import _tc_to_sec
    out_sec = _tc_to_sec(entry.get("out", "00:00:00.000"))
    in_sec = _tc_to_sec(entry.get("in", "00:00:00.000"))
    fps = _get_project_fps(tree)
    clip_duration_frames = int(round((out_sec - in_sec) * fps))
    if frame < 0 or frame >= clip_duration_frames:
        raise validation_error(
            f"frame_out_of_range: frame={frame}, clip_duration_frames={clip_duration_frames}\n"
            f"fix: pass a frame in [0, {clip_duration_frames - 1}]",
        )
    # Find existing keyframe at this frame, or insert
    from .._keyframes import Keyframe
    action = "added"
    new_kfs = []
    for k in kfs:
        if k.frame == frame:
            new_kfs.append(Keyframe(frame=frame, value=value, type=type_char))
            action = "updated"
        else:
            new_kfs.append(k)
    if action == "added":
        new_kfs.append(Keyframe(frame=frame, value=value, type=type_char))
    new_kfs.sort(key=lambda k: k.frame)
    kfs = new_kfs
    value_prop.text = serialize_keyframes(kfs)
    return {
        "clip_id": clip_id,
        "effect_index": effect_index,
        "param_name": param_name,
        "frame": frame,
        "value": value,
        "type": type,
        "action": action,
    }


def remove_keyframe(
    tree: ProjectTree,
    clip_id: str,
    effect_index: int,
    param_name: str,
    frame: int,
) -> dict:
    """Remove the keyframe at `frame`. No error if no keyframe exists there."""
    from .clips_edit import _find_entry_for_clip

    track, entry, _ti = _find_entry_for_clip(tree, clip_id)
    filters = list(entry.findall("filter"))
    if effect_index < 0 or effect_index >= len(filters):
        raise NotFoundError(
            f"effect_index_out_of_range: effect_index={effect_index}, "
            f"effect_count={len(filters)}\n"
            f"fix: call get_timeline_summary to see valid indices"
        )
    filt = filters[effect_index]
    value_prop = None
    for prop in filt.findall("property"):
        if prop.get("name") == param_name:
            value_prop = prop
            break
    if value_prop is None:
        raise NotFoundError(
            f"param_not_found: effect at index {effect_index} on clip "
            f"{clip_id!r} has no parameter named {param_name!r}\n"
            f"fix: call list_catalog to see valid parameter names"
        )
    current_str = value_prop.text or ""
    kfs = parse_animation_string(current_str)
    removed = False
    new_kfs = [k for k in kfs if k.frame != frame]
    if len(new_kfs) != len(kfs):
        removed = True
    value_prop.text = serialize_keyframes(new_kfs)
    return {
        "clip_id": clip_id,
        "effect_index": effect_index,
        "param_name": param_name,
        "frame": frame,
        "removed": removed,
    }
