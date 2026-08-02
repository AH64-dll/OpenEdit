"""Dirty-zone selection and atomic manifests for Remotion materialization.

The manifest is deliberately a small JSON document outside the media cache.
It records the last *successful* materialization, so a failed render cannot
make a later run treat incomplete work as reusable.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA = 1


@dataclass(frozen=True)
class DirtySelection:
    """The merged dirty ranges and current Remotion UIDs to process."""

    intervals: tuple[tuple[float, float], ...]
    composition_uids: frozenset[str]


def write_manifest_atomic(
    path: str | Path,
    manifest: Mapping[str, Any],
) -> Path:
    """Write ``manifest`` through a same-directory temporary file.

    The temporary file is flushed and fsynced before ``os.replace`` publishes
    it.  Serialization failures leave an existing manifest untouched.
    """
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(manifest, handle, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def load_manifest(path: str | Path) -> dict[str, Any] | None:
    """Load a valid schema-1 manifest, or ``None`` when unavailable."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return None
    if not isinstance(value, dict) or value.get("schema") != MANIFEST_SCHEMA:
        return None
    return value


def select_dirty_compositions(
    previous: Mapping[str, Any] | None,
    current: Mapping[str, Any],
    force_uids: Collection[str] = (),
) -> DirtySelection:
    """Select current Remotion compositions affected by manifest changes.

    Base clips are compared by ``clip_id``.  A changed, added, or removed clip
    contributes its old and/or new half-open timeline interval.  Ranges that
    overlap or touch are merged.  A current composition is selected when it
    intersects a merged range, is new, has changed content/profile/alpha/
    duration metadata, or is explicitly forced.  Removed compositions
    contribute their old range but are never returned as targets.
    """
    previous_manifest = _as_mapping(previous) if previous is not None else None
    current_manifest = _as_mapping(current)
    previous_clips = _index_entries(previous_manifest, "clips")
    current_clips = _index_entries(current_manifest, "clips")
    previous_compositions = _index_entries(previous_manifest, "compositions")
    current_compositions = _index_entries(current_manifest, "compositions")

    dirty_ranges: list[tuple[float, float]] = []
    for clip_id in sorted(set(previous_clips) | set(current_clips)):
        old_clip = previous_clips.get(clip_id)
        new_clip = current_clips.get(clip_id)
        if old_clip is not None and new_clip is not None:
            if _without_identity(old_clip, "clip_id") == _without_identity(
                new_clip, "clip_id",
            ):
                continue
            _append_interval(dirty_ranges, _entry_interval(old_clip))
            _append_interval(dirty_ranges, _entry_interval(new_clip))
        elif old_clip is not None:
            _append_interval(dirty_ranges, _entry_interval(old_clip))
        elif new_clip is not None:
            _append_interval(dirty_ranges, _entry_interval(new_clip))

    current_ids = set(current_compositions)
    previous_ids = set(previous_compositions)
    for composition_uid in sorted(previous_ids - current_ids):
        _append_interval(
            dirty_ranges,
            _entry_interval(previous_compositions[composition_uid]),
        )

    intervals = _merge_intervals(dirty_ranges)
    force_set = {str(uid) for uid in force_uids}
    render_context_changed = _render_context_changed(
        previous_manifest,
        current_manifest,
    )

    selected: set[str] = set()
    for composition_uid in sorted(current_ids):
        composition = current_compositions[composition_uid]
        previous_composition = previous_compositions.get(composition_uid)
        interval = _entry_interval(composition)
        if (
            composition_uid in force_set
            or previous_composition is None
            or render_context_changed
            or _composition_changed(
                previous_composition,
                composition,
                previous_manifest,
                current_manifest,
            )
            or _intersects_any(interval, intervals)
        ):
            selected.add(composition_uid)

    return DirtySelection(
        intervals=intervals,
        composition_uids=frozenset(selected),
    )


def _as_mapping(value: Mapping[str, Any] | Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="json")
        if isinstance(dumped, Mapping):
            return dict(dumped)
    raise TypeError(f"manifest must be a mapping, got {type(value).__name__}")


def _index_entries(
    manifest: Mapping[str, Any] | None,
    key: str,
) -> dict[str, dict[str, Any]]:
    if manifest is None:
        return {}
    raw_entries = manifest.get(key, ())
    if raw_entries is None:
        return {}
    if isinstance(raw_entries, (str, bytes)) or not isinstance(raw_entries, Sequence):
        raise ValueError(f"manifest {key!r} must be a list")

    entries: dict[str, dict[str, Any]] = {}
    for raw_entry in raw_entries:
        entry = _as_mapping(raw_entry)
        uid = _entry_identity(entry, key)
        if uid is not None:
            entries[uid] = entry
    return entries


def _entry_identity(entry: Mapping[str, Any], collection: str) -> str | None:
    if collection == "clips":
        raw_uid = entry.get("clip_id")
    else:
        raw_uid = (
            entry.get("composition_uid")
            or entry.get("uid")
            or entry.get("id")
        )
    if raw_uid is None:
        return None
    return str(raw_uid)


def _entry_interval(entry: Mapping[str, Any]) -> tuple[float, float] | None:
    try:
        start = float(entry.get("position_sec", entry.get("start_sec", 0.0)))
        if "duration_sec" in entry:
            duration = float(entry["duration_sec"])
            end = start + duration
        elif "out_point_sec" in entry:
            end = float(entry["out_point_sec"])
        else:
            return None
    except (TypeError, ValueError):
        return None
    if not math.isfinite(start) or not math.isfinite(end) or end <= start:
        return None
    return (start, end)


def _append_interval(
    intervals: list[tuple[float, float]],
    interval: tuple[float, float] | None,
) -> None:
    if interval is not None:
        intervals.append(interval)


def _merge_intervals(
    intervals: Sequence[tuple[float, float]],
) -> tuple[tuple[float, float], ...]:
    if not intervals:
        return ()
    ordered = sorted(intervals)
    merged: list[list[float]] = []
    for start, end in ordered:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return tuple((start, end) for start, end in merged)


def _intersects_any(
    interval: tuple[float, float] | None,
    dirty_ranges: Sequence[tuple[float, float]],
) -> bool:
    if interval is None:
        return False
    start, end = interval
    return any(
        start < dirty_end and dirty_start < end
        for dirty_start, dirty_end in dirty_ranges
    )


def _without_identity(
    entry: Mapping[str, Any],
    identity_key: str,
) -> dict[str, Any]:
    return {
        key: value
        for key, value in entry.items()
        if key != identity_key
    }


def _render_context_changed(
    previous: Mapping[str, Any] | None,
    current: Mapping[str, Any],
) -> bool:
    if previous is None:
        return False
    return any(
        previous.get(key) != current.get(key)
        for key in ("mode", "profile_fingerprint")
        if key in previous or key in current
    )


def _composition_changed(
    previous: Mapping[str, Any],
    current: Mapping[str, Any],
    previous_manifest: Mapping[str, Any] | None,
    current_manifest: Mapping[str, Any],
) -> bool:
    for key in (
        "cache_key",
        "composition_id",
        "entry_point",
        "props",
        "alpha",
        "duration_sec",
        "ext",
    ):
        if previous.get(key) != current.get(key):
            return True

    previous_profile = previous.get(
        "profile_fingerprint",
        previous_manifest.get("profile_fingerprint") if previous_manifest else None,
    )
    current_profile = current.get(
        "profile_fingerprint",
        current_manifest.get("profile_fingerprint"),
    )
    if previous_profile != current_profile:
        return True

    previous_mode = previous.get(
        "mode",
        previous_manifest.get("mode") if previous_manifest else None,
    )
    current_mode = current.get("mode", current_manifest.get("mode"))
    return previous_mode != current_mode


__all__ = [
    "MANIFEST_SCHEMA",
    "DirtySelection",
    "load_manifest",
    "select_dirty_compositions",
    "write_manifest_atomic",
]
