"""Clip speed-ramp operation: set_clip_speed_ramp.

Split out of clips_edit.py to keep that module under the 300-line cap.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from lxml import etree

from ..errors import BackendError, NotFoundError, validation_error
from ..io import ProjectTree
from ..tracks import resolve_producer
from ._helpers import get_project_fps
from .clips_edit import _find_entry_for_clip


def _find_clip_producer(tree: ProjectTree, entry) -> etree._Element | None:
    """Return the <producer> element for the given <entry>, or None.

    The clip <entry> references its bin producer via the entry's
    `producer` attribute. We follow that reference with resolve_producer
    (which handles kdenlive:id, mlt id, and entry-id forms).
    """
    producer_id = entry.get("producer", "")
    if not producer_id:
        return None
    return resolve_producer(tree, producer_id)


def set_clip_speed_ramp(
    tree: ProjectTree,
    clip_id: str,
    keyframes: Sequence[Mapping[str, int | float]],
) -> dict:
    """Add or replace a keyframed speed ramp on a clip.

    Uses an <link mlt_service="timeremap"> element on the clip's
    producer chain. Replaces the entire existing ramp.
    """
    if not keyframes:
        raise validation_error(
            f"keyframes_empty: keyframes is an empty list\n"
            f"fix: pass at least one keyframe, e.g. "
            f"[{{'time_ms': 0, 'rate': 1.0}}]",
        )
    # Validate ranges
    for i, kf in enumerate(keyframes):
        t = int(kf["time_ms"])
        if t < 0:
            raise validation_error(
                f"time_out_of_range: time_ms={t} at index {i}\n"
                f"fix: pass a non-negative time_ms",
            )
        r = float(kf["rate"])
        if r <= 0.0 or r > 10.0:
            raise validation_error(
                f"rate_out_of_range: rate={r} at index {i} "
                f"(must be in (0.0, 10.0])\n"
                f"fix: pass a rate in (0.0, 10.0]",
            )
    sorted_kfs = sorted(keyframes, key=lambda k: int(k["time_ms"]))
    for i in range(1, len(sorted_kfs)):
        if int(sorted_kfs[i]["time_ms"]) <= int(sorted_kfs[i-1]["time_ms"]):
            raise validation_error(
                f"time_monotonic_violation: duplicate or out-of-order "
                f"time_ms at index {i}\n"
                f"fix: pass keyframes sorted ascending by time_ms, "
                f"no duplicates",
            )
    first = sorted_kfs[0]
    if int(first["time_ms"]) != 0 or float(first["rate"]) != 1.0:
        raise validation_error(
            f"first_keyframe_must_be_zero: first keyframe must be at "
            f"time_ms=0 and rate=1.0 (got time_ms={first['time_ms']}, "
            f"rate={first['rate']})\n"
            f"fix: prepend a keyframe at time_ms=0 with rate=1.0",
        )
    # Find the clip's entry
    track, entry, _ti = _find_entry_for_clip(tree, clip_id)
    # Find the clip's producer in the bin via the entry's producer attr.
    producer = _find_clip_producer(tree, entry)
    if producer is None:
        raise BackendError(
            f"could not find the producer for clip {clip_id!r}\n"
            f"fix: this is a pyagent internal error, please report"
        )
    # Remove any existing <link mlt_service="timeremap">
    for link in list(producer.findall("link")):
        if link.get("mlt_service") == "timeremap":
            producer.remove(link)
    # Build the time_map string (HH:MM:SS:FF=rate;...)
    fps = get_project_fps(tree)
    parts = []
    for kf in sorted_kfs:
        t_sec = int(kf["time_ms"]) / 1000.0
        h = int(t_sec // 3600)
        m = int((t_sec % 3600) // 60)
        s = int(t_sec % 60)
        f = int(round((t_sec - int(t_sec)) * fps))
        if f >= int(fps):
            f = 0
            s += 1
        parts.append(f"{h:02d}:{m:02d}:{s:02d}:{f:02d}={float(kf['rate']):.3f}")
    time_map = ";".join(parts) + ";"
    # Add the new <link mlt_service="timeremap">
    link = etree.SubElement(producer, "link")
    link.set("mlt_service", "timeremap")
    tm_prop = etree.SubElement(link, "property")
    tm_prop.set("name", "time_map")
    tm_prop.text = time_map
    pitch_prop = etree.SubElement(link, "property")
    pitch_prop.set("name", "pitch")
    pitch_prop.text = "1"
    img_prop = etree.SubElement(link, "property")
    img_prop.set("name", "image_mode")
    img_prop.text = "nearest"
    return {
        "clip_id": clip_id,
        "keyframes_added": len(sorted_kfs),
        "time_map": time_map,
        "min_rate": min(float(k["rate"]) for k in sorted_kfs),
        "max_rate": max(float(k["rate"]) for k in sorted_kfs),
    }


__all__ = ["set_clip_speed_ramp"]
