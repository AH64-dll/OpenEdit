"""Parse/serialize Kdenlive animation strings + catalog helpers.

Imported by ops/*.py; not part of the public API.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


# Curve-type characters per Kdenlive 26.04's keyframemodel.cpp:22-53.
CURVE_LINEAR = "`"
CURVE_DISCRETE = "|"
CURVE_HOLD = "!"
CURVE_SMOOTH = "~"
# pyagent 2b exposes 15 curve types: 4 listed above + 8 most-common ease
# variants. The full 26-char alphabet (a..u, A..D) is documented but not
# yet exposed.
_ALLOWED_CURVE_CHARS: frozenset[str] = frozenset({
    CURVE_LINEAR, CURVE_DISCRETE, CURVE_HOLD, CURVE_SMOOTH,
    "a", "b", "c", "d", "A", "B", "C", "D",
})


@dataclass(frozen=True)
class Keyframe:
    frame: int
    value: str
    type: str  # empty, or one of the curve chars above


def parse_animation_string(s: str) -> list[Keyframe]:
    """Parse a Kdenlive animation string into a list of Keyframes.

    Format: "{frame}={value}[{type_char}]; {frame}={value}[{type_char}]; ..."
    Empty string returns [].
    """
    if not s:
        return []
    out: list[Keyframe] = []
    for raw_entry in s.split(";"):
        entry = raw_entry.strip()
        if not entry:
            continue
        type_char = ""
        if "=" in entry:
            frame_str, value = entry.split("=", 1)
            value = value.strip()
        else:
            # Shape "frame{type}value" — curve char follows frame digits
            # directly, with no '=' between (e.g. "25~0.5", "50|0.0").
            idx = 0
            while idx < len(entry) and entry[idx].isdigit():
                idx += 1
            frame_str = entry[:idx]
            rest = entry[idx:]
            if rest and rest[0] in _ALLOWED_CURVE_CHARS:
                type_char = rest[0]
                value = rest[1:].strip()
            else:
                value = rest.strip()
        if not frame_str:
            continue
        out.append(Keyframe(frame=int(frame_str),
                            value=value,
                            type=type_char))
    return out


def serialize_keyframes(kfs: Sequence[Keyframe]) -> str:
    """Serialize a list of Keyframes back into a Kdenlive animation string."""
    parts: list[str] = []
    for k in kfs:
        if k.type:
            parts.append(f"{k.frame}{k.type}{k.value}")
        else:
            parts.append(f"{k.frame}={k.value}")
    return "; ".join(parts)


def is_keyframable_param(
    catalog: Sequence[dict],
    effect_id: str,
    param_name: str,
) -> bool | str:
    """Return True if the param is animation-string keyframable, "simplekeyframe"
    if it's mlt_geometry, or False otherwise.

    Reads the `keyframes` field set by build_catalog.py in Task 0.3.
    """
    for entry in catalog:
        if entry.get("kdenlive_id") != effect_id:
            continue
        for p in entry.get("parameters", []):
            if p.get("name") == param_name:
                kf = p.get("keyframes", False)
                if kf is True:
                    return True
                if kf == "simplekeyframe":
                    return "simplekeyframe"
                return False
    return False


def coerce_param_value(param_type: str, value: str) -> str:
    """Coerce `value` to the format expected by `param_type`.

    Returns the string-form of the coerced value. Raises ValueError if the
    value can't be coerced.
    """
    if param_type in ("constant", "string", "url", "fixed", "list", "color",
                       "fixedcolor", "position", "bezier_spline", "geometry",
                       "roto-spline", "curve", "filterjob", "keywords",
                       "listdependency", "fontfamily", "urllist", "switch",
                       "multiswitch", "hidden", "rect", "animatedrect",
                       "animatedfakerect", "animatedfakepoint", "animated"):
        return str(value)
    if param_type in ("double", "float"):
        return str(float(value))
    if param_type in ("integer", "int"):
        return str(int(value))
    if param_type == "bool":
        return "1" if str(value).lower() in ("1", "true", "yes", "on") else "0"
    # Unknown type — pass through.
    return str(value)
