"""Clip-edit operations: slip / ripple-delete / speed / split / replace.

These are the "modification" ops (transforming an existing clip in
place or splitting it). The "placement" ops (insert/append/move/
trim/delete) live in `clips.py`. The split is a deliberate
per-domain choice driven by the 300-line module-size cap.
"""
from __future__ import annotations

from lxml import etree

from ..errors import NotFoundError, validation_error
from ..io import ProjectTree, _sec_to_tc, _tc_to_sec
from ..tracks import (
    get_track_playlists, get_tracks, next_kdenlive_id,
    resolve_producer, resolve_source_duration,
)
from ._helpers import entry_start_sec


# --- Internal helpers (shared by the 5 ops) -------------------------------


def _find_entry_for_clip(tree: ProjectTree, clip_id: str) -> tuple[etree._Element, etree._Element, int]:
    """Return (track, entry, track_index) for a given clip_id, or raise NotFoundError.

    Entries live inside the playlists referenced by track refs, not
    inside the tractor itself — so we must walk tracks -> playlists ->
    entries (same pattern as tracks.find_all_entries).
    """
    for ti, track in enumerate(get_tracks(tree)):
        for pl in get_track_playlists(tree, track):
            for entry in pl.iter("entry"):
                kid_prop = entry.find("property[@name='kdenlive:id']")
                if kid_prop is not None and kid_prop.text == clip_id:
                    return track, entry, ti
    raise NotFoundError(
        f"clip_not_found: clip_id={clip_id!r}\n"
        f"fix: call get_timeline_summary and re-pick"
    )


# --- Public ops ------------------------------------------------------------


def slip_clip(tree: ProjectTree, clip_id: str, delta_sec: float) -> dict:
    """Slip the clip: shift source in/out by `delta_sec` while keeping
    the timeline window fixed.
    """
    track, entry, ti = _find_entry_for_clip(tree, clip_id)
    producer_id = entry.get("producer", "")
    src = resolve_producer(tree, producer_id)
    src_dur = resolve_source_duration(tree, producer_id)

    cur_in = _tc_to_sec(entry.get("in", "00:00:00.000"))
    cur_out = _tc_to_sec(entry.get("out", "00:00:00.000"))
    new_in = cur_in + delta_sec
    new_out = cur_out + delta_sec

    if new_in < 0 or new_out > src_dur:
        raise NotFoundError(
            f"source_oob: slip would push source_in={new_in} or source_out={new_out} "
            f"outside source duration={src_dur}\n"
            f"fix: delta must keep source_in >= 0 and source_out <= source duration"
        )

    entry.set("in", _sec_to_tc(new_in))
    entry.set("out", _sec_to_tc(new_out))
    return {
        "clip_id": clip_id,
        "source_id": producer_id,
        "source_in_sec": new_in,
        "source_out_sec": new_out,
        "track_index": ti,
        "timeline_start_sec": entry_start_sec(entry.getparent(), entry),
        "duration_sec": new_out - new_in,
    }


def ripple_delete_clip(tree: ProjectTree, clip_id: str) -> dict:
    """Remove the clip and close the gap on the same track by shifting
    all following clips left by the deleted duration.

    The actual timeline recalc happens when the file is reloaded
    (Kdenlive computes timeline positions from source in/out sums);
    we return the list of clip_ids whose position changes.
    """
    track, entry, ti = _find_entry_for_clip(tree, clip_id)
    playlist = entry.getparent()
    cur_in = _tc_to_sec(entry.get("in", "00:00:00.000"))
    cur_out = _tc_to_sec(entry.get("out", "00:00:00.000"))
    deleted_dur = cur_out - cur_in

    # Collect kdenlive:ids of entries that follow `entry` BEFORE removal,
    # because after `playlist.remove(entry)` the `entry` ref is detached
    # and the position-based follow check no longer has its anchor.
    entries = [e for e in playlist.findall("entry") if e is not None]
    entry_idx = next(
        (i for i, e in enumerate(entries) if e is entry),
        len(entries),
    )
    shifted: list[str] = []
    for e in entries[entry_idx + 1:]:
        kid_prop = e.find("property[@name='kdenlive:id']")
        if kid_prop is not None and kid_prop.text:
            shifted.append(kid_prop.text)

    playlist.remove(entry)
    return {"deleted_clip_id": clip_id, "shifted_clip_ids": shifted}


def change_clip_speed(tree: ProjectTree, clip_id: str, rate: float) -> dict:
    """Change the playback rate (1.0 = normal, 2.0 = 2x faster, 0.5 = 2x slower).
    Rate must be in [0.1, 10.0].
    """
    if rate < 0.1 or rate > 10.0:
        raise validation_error(
            f"rate_out_of_range: rate={rate} not in [0.1, 10.0]",
            "use a rate between 0.1 and 10.0",
        )
    track, entry, ti = _find_entry_for_clip(tree, clip_id)
    cur_in = _tc_to_sec(entry.get("in", "00:00:00.000"))
    cur_out = _tc_to_sec(entry.get("out", "00:00:00.000"))
    cur_dur = cur_out - cur_in
    new_dur = cur_dur / rate

    # Set the producer's speed property. Kdenlive reads "warp_speed" for
    # the producer's playback rate; the source in/out stay the same.
    producer = entry.find("producer")
    if producer is None:
        # The entry uses an external producer reference; look it up.
        producer = tree.root.find(f".//producer[@id='{entry.get('producer')}']")
    if producer is not None:
        speed_prop = producer.find("property[@name='warp_speed']")
        if speed_prop is None:
            speed_prop = etree.SubElement(producer, "property")
            speed_prop.set("name", "warp_speed")
        speed_prop.text = str(rate)

    return {
        "clip_id": clip_id,
        "source_id": entry.get("producer", ""),
        "source_in_sec": cur_in,
        "source_out_sec": cur_out,
        "rate": rate,
        "old_duration_sec": cur_dur,
        "new_duration_sec": new_dur,
    }


def split_clip(tree: ProjectTree, clip_id: str, at_sec: float) -> dict:
    """Split the clip at `at_sec` (a timeline-relative position within
    the clip's range). Returns the left (original) and right (new) clip ids.
    """
    track, entry, ti = _find_entry_for_clip(tree, clip_id)
    playlist = entry.getparent()
    timeline_start = entry_start_sec(playlist, entry)
    cur_in = _tc_to_sec(entry.get("in", "00:00:00.000"))
    cur_out = _tc_to_sec(entry.get("out", "00:00:00.000"))
    cur_dur = cur_out - cur_in
    if at_sec <= timeline_start or at_sec >= timeline_start + cur_dur:
        raise NotFoundError(
            f"split_position_invalid: at_sec={at_sec} not strictly between "
            f"{timeline_start} and {timeline_start + cur_dur}\n"
            f"fix: use at_sec strictly between clip_start and clip_end"
        )
    rel_offset = at_sec - timeline_start  # offset from clip start
    new_left_out = cur_in + rel_offset
    # Left half: original entry, with new "out"
    entry.set("out", _sec_to_tc(new_left_out))
    # Right half: new entry, fresh kid, in=offset, out=cur_out
    right_kid = next_kdenlive_id(tree)
    right_entry = etree.SubElement(playlist, "entry")
    right_entry.set("producer", entry.get("producer", ""))
    right_entry.set("in", _sec_to_tc(new_left_out))
    right_entry.set("out", _sec_to_tc(cur_out))
    kid_prop = etree.SubElement(right_entry, "property")
    kid_prop.set("name", "kdenlive:id")
    kid_prop.text = right_kid
    # Move right_entry to be right after the original entry
    playlist.remove(right_entry)
    entry.addnext(right_entry)
    return {"left_clip_id": clip_id, "right_clip_id": right_kid}


def replace_clip_source(tree: ProjectTree, clip_id: str, new_source_id: str) -> dict:
    """Replace the clip's source media. Resets rate to 1.0. New duration
    = min(old_timeline_duration, new_source_duration).
    """
    track, entry, ti = _find_entry_for_clip(tree, clip_id)
    old_source_id = entry.get("producer", "")
    old_in = _tc_to_sec(entry.get("in", "00:00:00.000"))
    old_out = _tc_to_sec(entry.get("out", "00:00:00.000"))
    old_dur = old_out - old_in
    new_src_dur = resolve_source_duration(tree, new_source_id)
    new_dur = min(old_dur, new_src_dur)
    # Update the producer reference
    entry.set("producer", new_source_id)
    # Reset source in/out
    entry.set("in", _sec_to_tc(0.0))
    entry.set("out", _sec_to_tc(new_dur))
    # Reset the warp_speed on the producer to 1.0
    producer = entry.find("producer")
    if producer is None:
        producer = tree.root.find(f".//producer[@id='{new_source_id}']")
    if producer is not None:
        speed_prop = producer.find("property[@name='warp_speed']")
        if speed_prop is None:
            speed_prop = etree.SubElement(producer, "property")
            speed_prop.set("name", "warp_speed")
        speed_prop.text = "1.0"
    return {
        "clip_id": clip_id,
        "old_source_id": old_source_id,
        "new_source_id": new_source_id,
        "old_rate": 1.0,  # we can't easily read the current rate; assume 1.0 pre-replace
        "new_rate": 1.0,
        "old_duration_sec": old_dur,
        "new_duration_sec": new_dur,
        "source_in_sec": 0.0,
        "source_out_sec": new_dur,
    }


__all__ = [
    "slip_clip", "ripple_delete_clip", "change_clip_speed",
    "split_clip", "replace_clip_source",
]
