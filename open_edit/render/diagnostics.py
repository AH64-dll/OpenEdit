"""Stable product and stage diagnostics for render results."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Literal


RenderMode = Literal["proxy", "final"]
StageStatus = Literal["completed", "skipped", "failed"]

CANONICAL_STAGE_NAMES: tuple[str, ...] = (
    "derive_timeline",
    "render_cache_lookup",
    "remotion_materialize",
    "hyperframes_materialize",
    "build_render_plan",
    "emit_mlt",
    "melt_audio",
    "melt_video",
    "ffmpeg_encode",
    "source_repair",
    "qc",
)

LEGACY_STAGE_ALIASES: dict[str, str] = {
    "melt": "melt_video",
    "ffmpeg": "ffmpeg_encode",
    "audio": "melt_audio",
}

_STAGE_STATUSES = frozenset({"completed", "skipped", "failed"})


def _finite_non_negative(value: object) -> float:
    """Return a usable elapsed value for a JSON diagnostics payload."""
    try:
        elapsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(elapsed) or elapsed < 0.0:
        return 0.0
    return elapsed


def _diagnostic_scalar(value: object) -> object:
    """Keep diagnostics JSON-compatible without copying nested user data."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else 0.0
    return None


class StageRecorder:
    """Collect canonical stage status, timing, and bounded scalar fields."""

    def __init__(self) -> None:
        self._stages: dict[str, dict[str, object]] = {}

    def record(
        self,
        name: str,
        elapsed_sec: float,
        *,
        status: StageStatus = "completed",
        **fields: object,
    ) -> None:
        if status not in _STAGE_STATUSES:
            raise ValueError(f"unknown stage status: {status!r}")
        if not isinstance(name, str) or not name:
            raise ValueError("stage name must be a non-empty string")

        entry: dict[str, object] = {
            "elapsed_sec": _finite_non_negative(elapsed_sec),
            "status": status,
        }
        for key, value in fields.items():
            if not isinstance(key, str):
                continue
            scalar = _diagnostic_scalar(value)
            if scalar is not None or value is None:
                entry[key] = scalar
        self._stages[name] = entry

    def skip(self, name: str, *, reason: str, **fields: object) -> None:
        self.record(name, 0.0, status="skipped", reason=reason, **fields)

    @property
    def stages(self) -> dict[str, dict[str, object]]:
        """Return a JSON-compatible snapshot of the recorded stages."""
        return {name: dict(entry) for name, entry in self._stages.items()}


def _dimension(
    profile: Any,
    name: str,
    explicit: int | None,
) -> int:
    if explicit is not None:
        return int(explicit)
    if profile is None:
        raise TypeError(f"{name} is required when profile is omitted")
    if isinstance(profile, Mapping):
        value = profile.get(name)
    else:
        value = getattr(profile, name, None)
    if value is None:
        raise TypeError(f"profile has no {name}")
    return int(value)


def product_descriptor(
    mode: RenderMode | str,
    profile: Any | None = None,
    *,
    width: int | None = None,
    height: int | None = None,
) -> dict[str, object]:
    """Describe the full-timeline product represented by a render mode.

    ``profile`` may be a ``RenderProfile`` or a mapping with ``width`` and
    ``height`` keys. Explicit dimensions are accepted for callers that have
    already resolved a profile's output size.
    """
    if mode == "proxy":
        kind = "review_artifact"
        label = "Review artifact"
    elif mode == "final":
        kind = "final_export"
        label = "Final export"
    else:
        raise ValueError(f"unsupported render mode: {mode!r}")

    return {
        "kind": kind,
        "mode": mode,
        "label": label,
        "width": _dimension(profile, "width", width),
        "height": _dimension(profile, "height", height),
        "interactive": False,
        "source_proxy": False,
        "timeline_preview_chunk": False,
    }


def with_legacy_stage_aliases(
    stages: Mapping[str, Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    """Return stage entries with compatibility names for old consumers."""
    result = {name: dict(entry) for name, entry in stages.items()}
    for alias, canonical in LEGACY_STAGE_ALIASES.items():
        if canonical in result:
            result[alias] = dict(result[canonical])
    return result

