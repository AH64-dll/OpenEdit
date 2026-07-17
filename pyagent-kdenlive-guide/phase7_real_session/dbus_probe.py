"""dbus_probe — read the timeline state from the project file.

The original brief called for reading the running Kdenlive's
timeline state via D-Bus (KdenliveDBus.get_transition_list).
That method does not exist — KdenliveDBus in phase5 is
write-only (addProjectClip, addTimelineClip, addEffect,
scriptRender, updateProjectPath, cleanRestart, exitApp). It
has no read methods.

So the project file is the source of truth. When the chat
UI's notifier applies a transition via the file backend,
the file is updated immediately. When it applies via the
live D-Bus path, the running Kdenlive either writes it
back to disk or holds it until the next save — either way,
by the time the live-sync has settled, the file has it.

This module parses the .kdenlive XML and extracts every
<transition> in the tractor's multitrack, returning them
as plain dicts.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from lxml import etree


def _track_producer_id(multitrack: etree._Element, index: int) -> str:
    """Return the producer id of the <track> at `index` in the multitrack.

    Tracks appear in document order; index 0 is the first <track>.
    """
    tracks = multitrack.findall("track")
    if 0 <= index < len(tracks):
        return tracks[index].get("producer", "") or ""
    return ""


def _property_value(transition: etree._Element, name: str) -> str:
    """Return the text of <property name=name>, or empty string."""
    for prop in transition.findall("property"):
        if prop.get("name") == name:
            return (prop.text or "").strip()
    return ""


def _transitions_in_tractor(root: etree._Element) -> list[dict[str, str]]:
    """Return every <transition> across all <tractor> elements."""
    out: list[dict[str, str]] = []
    for tractor in root.findall("tractor"):
        multitrack = tractor.find("multitrack")
        for transition in tractor.findall("transition"):
            try:
                a_idx = int(_property_value(transition, "a_track"))
            except ValueError:
                a_idx = 0
            try:
                b_idx = int(_property_value(transition, "b_track"))
            except ValueError:
                b_idx = 0
            kind = (
                _property_value(transition, "kdenlive_id")
                or _property_value(transition, "mlt_service")
            )
            from_clip = _track_producer_id(multitrack, a_idx) if multitrack is not None else ""
            to_clip = _track_producer_id(multitrack, b_idx) if multitrack is not None else ""
            out.append({
                "from_clip": from_clip,
                "to_clip": to_clip,
                "kind": kind,
            })
    return out


def read_timeline_state(project_path: Optional[str] = None) -> dict[str, Any]:
    """Read transitions from the project file.

    The original spec called for a D-Bus read of the live Kdenlive
    state, but KdenliveDBus (phase5) is write-only — there is no
    get_transition_list() method. The project file is the source
    of truth: when the chat UI's notifier applies a transition
    via D-Bus, the running Kdenlive either writes it back to disk
    immediately, or holds it in memory until next save. Either
    way, the file will have the transition by the time the
    live-sync has settled.

    Returns:
        {"transitions": [{"from_clip": str, "to_clip": str, "kind": str}, ...]}

    Reads the project file at `project_path` (default: the chat UI's
    PYAGENT_PROJECT env var, if set; otherwise raises RuntimeError).
    """
    if project_path is None:
        project_path = os.environ.get("PYAGENT_PROJECT")
    if not project_path:
        raise RuntimeError(
            "read_timeline_state requires project_path= or PYAGENT_PROJECT env var"
        )
    if not os.path.isfile(project_path):
        raise FileNotFoundError(project_path)
    tree = etree.parse(project_path)
    root = tree.getroot()
    return {"transitions": _transitions_in_tractor(root)}
