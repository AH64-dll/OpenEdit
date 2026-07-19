"""Shared low-level helpers for the ops modules.

Imported by ops/*.py; not part of the public API.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from lxml import etree

from ..io import _probe_duration_sec, _sec_to_tc, _tc_to_sec


def playlist_duration(pl: etree._Element | None) -> float:
    """Return the total duration of a playlist in seconds.

    Sums every <entry> child's (out - in) and every <blank> child's
    length. Returns 0.0 for a None playlist."""
    if pl is None:
        return 0.0
    duration = 0.0
    for child in pl:
        if child.tag == "entry":
            in_val = _tc_to_sec(child.get("in", "00:00:00.000"))
            out_val = _tc_to_sec(child.get("out", "00:00:00.000"))
            duration += max(0.0, out_val - in_val)
        elif child.tag == "blank":
            duration += _tc_to_sec(child.get("length", "00:00:00.000"))
    return duration


def entry_start_sec(pl: etree._Element | None, entry: etree._Element) -> float:
    """Return the on-timeline start time (seconds) of `entry` in `pl`.

    Walks the playlist from the start, accumulating entry and blank
    durations, until it finds `entry`. If `entry` is not in the
    playlist, returns the total playlist duration (i.e. the
    position past the end)."""
    if pl is None:
        return 0.0
    current = 0.0
    for child in pl:
        if child == entry:
            return current
        if child.tag == "entry":
            in_val = _tc_to_sec(child.get("in", "00:00:00.000"))
            out_val = _tc_to_sec(child.get("out", "00:00:00.000"))
            current += max(0.0, out_val - in_val)
        elif child.tag == "blank":
            current += _tc_to_sec(child.get("length", "00:00:00.000"))
    return current


def shift_entry_on_timeline(
    pl: etree._Element, entry: etree._Element, shift: float
) -> None:
    """Adjust blank spacing around `entry` by `shift` seconds.

    If `shift` is positive, prepend a blank of that length to the
    entry. If `shift` is negative, shrink the blank immediately
    preceding the entry (or remove it if it would go to zero or
    below). No-op when `shift` is exactly 0.0."""
    if shift == 0.0:
        return
    idx = list(pl).index(entry)
    if idx > 0 and pl[idx - 1].tag == "blank":
        blank = pl[idx - 1]
        old_len = _tc_to_sec(blank.get("length", "00:00:00.000"))
        new_len = max(0.0, old_len + shift)
        if new_len > 0.0:
            blank.set("length", _sec_to_tc(new_len))
        else:
            pl.remove(blank)
    elif shift > 0.0:
        blank = etree.Element("blank")
        blank.set("length", _sec_to_tc(shift))
        pl.insert(idx, blank)


def insert_entry_at_position(
    pl: etree._Element, entry: etree._Element, position_sec: float
) -> None:
    """Insert `entry` at `position_sec` on the playlist, splitting
    any existing entry/blank that overlaps the position.

    `entry` MUST be detached before this call (it is added to the
    playlist). If the position is past the end, a trailing blank
    is added if needed so the entry lands at the requested time."""
    items = []
    for child in pl:
        if child == entry:
            continue
        if child.tag == "entry":
            items.append((
                child,
                _tc_to_sec(child.get("in", "00:00:00.000")),
                _tc_to_sec(child.get("out", "00:00:00.000")),
            ))
        elif child.tag == "blank":
            items.append((
                child,
                _tc_to_sec(child.get("length", "00:00:00.000")),
            ))

    for child in list(pl):
        pl.remove(child)

    current_time = 0.0
    inserted = False

    def add_our_entry() -> None:
        nonlocal inserted
        pl.append(entry)
        inserted = True

    for item in items:
        if not inserted:
            item_dur = (item[2] - item[1] if len(item) == 3 else item[1])
            if current_time <= position_sec < current_time + item_dur:
                diff = position_sec - current_time
                if diff > 0.0:
                    if len(item) == 2:
                        b = etree.Element("blank")
                        b.set("length", _sec_to_tc(diff))
                        pl.append(b)
                    else:
                        left = etree.Element("entry")
                        left.set("producer", item[0].get("producer"))
                        left.set("in", _sec_to_tc(item[1]))
                        left.set("out", _sec_to_tc(item[1] + diff))
                        for c in item[0]:
                            left.append(copy_elem(c))
                        pl.append(left)

                add_our_entry()

                right_dur = item_dur - diff
                if right_dur > 0.0:
                    if len(item) == 2:
                        b = etree.Element("blank")
                        b.set("length", _sec_to_tc(right_dur))
                        pl.append(b)
                    else:
                        right = etree.Element("entry")
                        right.set("producer", item[0].get("producer"))
                        right.set("in", _sec_to_tc(item[1] + diff))
                        right.set("out", _sec_to_tc(item[2]))
                        for c in item[0]:
                            right.append(copy_elem(c))
                        pl.append(right)
                continue

        pl.append(item[0])
        current_time += (item[2] - item[1] if len(item) == 3 else item[1])

    if not inserted:
        if position_sec > current_time:
            blank = etree.Element("blank")
            blank.set("length", _sec_to_tc(position_sec - current_time))
            pl.append(blank)
        add_our_entry()


def copy_elem(elem: etree._Element) -> etree._Element:
    """Return a deep copy of an lxml element. Used by
    insert_entry_at_position to split an existing entry into two."""
    import copy as _copy
    return _copy.deepcopy(elem)


def probe_duration_sec(path: Path) -> float:
    """Use ffprobe (already an mlt-pipeline dep) to read duration.
    Returns 0.0 if probe fails.

    Public wrapper around io._probe_duration_sec; re-exported here
    so ops modules can depend on helpers without reaching into io.
    """
    return _probe_duration_sec(path)


__all__ = [
    "playlist_duration",
    "entry_start_sec",
    "shift_entry_on_timeline",
    "insert_entry_at_position",
    "probe_duration_sec",
]
