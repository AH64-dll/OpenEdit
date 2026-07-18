"""Pure validation functions for the editor backend.

Every function is pure: no I/O, no class state. They either return a
normalized value (path, kdenlive_id, coerced params) or raise
``ValidationError`` with a ``fix:`` line so the LLM caller can
self-correct. Called at the top of every mutating backend operation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from .errors import BackendError, ValidationError, validation_error


# ---- Tracks & positions ----


def validate_track_index(idx: int, count: int) -> None:
    """Reject track indices outside ``[0, count)``."""
    if not (0 <= idx < count):
        raise validation_error(
            f"track_index {idx} out of range (project has {count} track(s))",
            f"set track_index in 0..{max(0, count - 1)}",
        )


def validate_position_sec(pos: float) -> None:
    """Reject negative timeline positions. Zero is valid."""
    if pos < 0:
        raise validation_error(
            f"position_sec must be >= 0, got {pos}",
            "set position_sec to a non-negative number (0 = start of timeline)",
        )


def validate_clip_range(in_sec: float, out_sec: float, source_duration: float) -> None:
    """Reject clip ranges that are inverted, negative, or out of bounds.

    ``in_sec`` >= 0; ``out_sec`` > ``in_sec`` and <= source_duration.
    """
    if in_sec < 0:
        raise validation_error(
            f"in_sec must be >= 0, got {in_sec}",
            "set in_sec to a non-negative number (0 = start of source media)",
        )
    if out_sec <= in_sec:
        raise validation_error(
            f"clip range inverted: in_sec={in_sec} >= out_sec={out_sec}",
            f"set in_sec < out_sec (e.g. in_sec={in_sec}, out_sec={in_sec + 1.0})",
        )
    if out_sec > source_duration:
        raise validation_error(
            f"clip out_sec={out_sec} exceeds source duration {source_duration}",
            f"set out_sec <= source_duration ({source_duration}); "
            f"check get_timeline_summary() for the source's full duration",
        )


# ---- Catalog lookups (transitions, effects) ----


def _catalog_id_lookup(catalog: Sequence[Mapping[str, Any]], kind: str) -> str:
    """Case-insensitive lookup; returns the canonical (as-stored) id."""
    target = kind.strip().lower()
    for entry in catalog:
        kid = entry.get("kdenlive_id")
        if isinstance(kid, str) and kid.lower() == target:
            return kid
    available = ", ".join(
        str(e.get("kdenlive_id", "?")) for e in catalog if e.get("kdenlive_id")
    )
    raise validation_error(
        f"id '{kind}' not in catalog",
        f"choose one of: {available or '(catalog is empty)'}",
    )


def validate_transition_kind(kind: str, catalog: Sequence[Mapping[str, Any]]) -> str:
    """Resolve a transition kind (case-insensitive) to its canonical id."""
    if not isinstance(kind, str) or not kind.strip():
        raise validation_error(
            "transition kind must be a non-empty string",
            "pass one of the catalog's kdenlive_id values (e.g. 'dissolve')",
        )
    return _catalog_id_lookup(catalog, kind)


def validate_effect_id(effect_id: str, catalog: Sequence[Mapping[str, Any]]) -> str:
    """Resolve an effect id (case-insensitive) to its canonical id."""
    if not isinstance(effect_id, str) or not effect_id.strip():
        raise validation_error(
            "effect_id must be a non-empty string",
            "pass one of the catalog's kdenlive_id values (e.g. 'blur')",
        )
    return _catalog_id_lookup(catalog, effect_id)


# ---- Effect parameter validation ----


def _coerce_param(name: str, ptype: str, value: Any) -> str:
    """Coerce a param value to the canonical string form for ``ptype``."""
    if ptype in ("double", "float"):
        try:
            return repr(float(value))
        except (TypeError, ValueError):
            raise validation_error(
                f"param '{name}' expects a number, got {value!r}",
                "pass a numeric value (e.g. '2.5')",
            )
    if ptype in ("int", "integer"):
        try:
            return str(int(value))
        except (TypeError, ValueError):
            raise validation_error(
                f"param '{name}' expects an integer, got {value!r}",
                "pass an integer value (e.g. '42')",
            )
    if ptype == "bool":
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, str):
            s = value.strip().lower()
            if s in ("1", "true", "yes", "on"):
                return "1"
            if s in ("0", "false", "no", "off"):
                return "0"
        raise validation_error(
            f"param '{name}' expects a bool, got {value!r}",
            "pass '0'/'1', 'true'/'false', 'yes'/'no', or 'on'/'off'",
        )
    # Unknown type — pass through as string. Catalog is the source of truth.
    return str(value)


def validate_effect_params(
    entry: Mapping[str, Any],
    params: Mapping[str, Any],
) -> dict[str, str]:
    """Validate and coerce params against a catalog entry.

    Rejects unknown parameter names (typo guard) and values that
    don't match the declared type. Returns a new dict with values
    coerced to the canonical string form for XML.
    """
    declared = {
        p.get("name"): p.get("type", "string")
        for p in entry.get("parameters", [])
        if p.get("name")
    }
    result: dict[str, str] = {}
    for name, value in params.items():
        if name not in declared:
            known = ", ".join(declared.keys()) or "(effect has no parameters)"
            raise validation_error(
                f"effect '{entry.get('kdenlive_id', '?')}' has no parameter "
                f"named '{name}'",
                f"choose one of: {known}",
            )
        result[name] = _coerce_param(name, declared[name], value)
    return result


# ---- Source media ----


def validate_source_path(path: str) -> Path:
    """Reject paths that don't point to an existing file.

    Returns the path as a ``pathlib.Path``.
    """
    if not isinstance(path, str) or not path.strip():
        raise validation_error(
            "source path must be a non-empty string",
            "pass the absolute path to the media file on disk",
        )
    p = Path(path)
    if not p.is_file():
        raise validation_error(
            f"source path does not exist or is not a regular file: {path}",
            "check the path is correct and the file exists; "
            "use an absolute path or a path relative to the project file",
        )
    return p


# ---- Markers ----


_MARKER_KINDS = ("marker", "guide", "chapter")


def validate_marker_kind(kind: str) -> str:
    """Normalize a marker kind to one of ``marker`` | ``guide`` | ``chapter``.

    Case-insensitive; trims whitespace; returns the lowercase form.
    """
    if not isinstance(kind, str) or not kind.strip():
        raise validation_error(
            "marker kind must be a non-empty string",
            f"use one of: {', '.join(_MARKER_KINDS)}",
        )
    target = kind.strip().lower()
    if target not in _MARKER_KINDS:
        raise validation_error(
            f"marker kind '{kind}' not recognized",
            f"use one of: {', '.join(_MARKER_KINDS)}",
        )
    return target


__all__ = [
    "validate_track_index",
    "validate_position_sec",
    "validate_clip_range",
    "validate_transition_kind",
    "validate_effect_id",
    "validate_effect_params",
    "validate_source_path",
    "validate_marker_kind",
]
