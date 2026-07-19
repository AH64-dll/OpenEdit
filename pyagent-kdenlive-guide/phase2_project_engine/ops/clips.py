"""Clip operations: insert/append/move/trim/delete.

BUG 1 fix: no `playlists[0]` fallback in the audio path. If
get_video_playlist cannot identify a writable playlist for the
target track, the corresponding (video or audio) insert is
skipped — never silently misrouted to a different playlist.
"""
from __future__ import annotations

from lxml import etree

from ..errors import BackendError
from ..io import ProjectTree, _sec_to_tc, _tc_to_sec
from ..tracks import (
    bump_tractor_duration, find_all_entries, get_tracks,
    get_video_playlist, next_kdenlive_id, resolve_producer,
    resolve_source_duration,
)
from ..validators import (
    validate_clip_range, validate_position_sec, validate_track_index,
)
from ._helpers import (
    insert_entry_at_position, playlist_duration, shift_entry_on_timeline,
)


# --- Internal helpers -------------------------------------------------------


def _is_audio_tractor(t: etree._Element) -> bool:
    a = t.find("property[@name='kdenlive:audio_track']")
    return a is not None and a.text == "1"


def _producer_has_audio(prod: etree._Element) -> bool:
    """False for audio-less or image-only producers (clip_type 2/5/6)
    and for pure-color generators."""
    for p in prod.findall("property"):
        if p.get("name") == "kdenlive:clip_type" and p.text in ("2", "5", "6"):
            return False
    svc = prod.find("property[@name='mlt_service']")
    if svc is not None and svc.text in ("color", "qimage", "blip"):
        return False
    return True


def _split_indices(tracks: list[etree._Element]) -> tuple[list[int], list[int]]:
    """Return (video_indices, audio_indices) in the order they appear."""
    vid, aud = [], []
    for i, t in enumerate(tracks):
        (aud if _is_audio_tractor(t) else vid).append(i)
    return vid, aud


def _paired_index(tracks: list[etree._Element], idx: int) -> int | None:
    """Return the index of the track that pairs with `idx` (N-th video
    pairs with N-th audio). None if there's no pair."""
    vid, aud = _split_indices(tracks)
    if idx in vid and vid.index(idx) < len(aud):
        return aud[vid.index(idx)]
    if idx in aud and aud.index(idx) < len(vid):
        return vid[aud.index(idx)]
    return None


def _first_audio(tracks: list[etree._Element]) -> int | None:
    return _split_indices(tracks)[1][0] if _split_indices(tracks)[1] else None


def _entry_source_kid(tree: ProjectTree, entry: etree._Element) -> str:
    """kdenlive:id of the bin producer referenced by an entry."""
    pid = entry.get("producer", "")
    for prod in tree.root.iter("producer"):
        if prod.get("id") == pid:
            for p in prod.iter("property"):
                if p.get("name") == "kdenlive:id":
                    return p.text or ""
    return ""


def _make_entry(producer_id: str, in_sec: float, out_sec: float, kid: str) -> etree._Element:
    e = etree.Element("entry")
    e.set("producer", producer_id)
    e.set("in", _sec_to_tc(in_sec))
    e.set("out", _sec_to_tc(out_sec))
    p = etree.SubElement(e, "property")
    p.set("name", "kdenlive:id")
    p.text = kid
    return e


def _add_kid(tree: ProjectTree, track_index: int, producer: etree._Element,
             in_sec: float, out_sec: float, pos_sec: float, kid: str) -> bool:
    """Insert one entry into the playlist of `tracks[track_index]`.
    Returns True if the insert happened, False if it was skipped
    (BUG 1 fix: no fallback to playlists[0])."""
    tracks = get_tracks(tree)
    pl = get_video_playlist(tree, tracks[track_index])
    if pl is None:
        return False
    entry = _make_entry(producer.get("id"), in_sec, out_sec, kid)
    insert_entry_at_position(pl, entry, pos_sec)
    return True


# --- Public API -------------------------------------------------------------


def insert_clip(
    tree: ProjectTree, track_index: int, position_sec: float, source_id: str,
    source_in_sec: float = 0.0, source_out_sec: float | None = None,
    video_only: bool = False, audio_only: bool = False,
) -> str:
    """Insert a clip; video goes to the target track's video playlist
    and audio goes to the paired track's playlist (both share the
    same kdenlive:id). BUG 1 fix: skipped, not misrouted, when a
    playlist cannot be identified with confidence."""
    tracks = get_tracks(tree)
    validate_track_index(track_index, len(tracks))
    validate_position_sec(position_sec)
    duration = resolve_source_duration(tree, source_id)
    if source_out_sec is None:
        source_out_sec = duration
    validate_clip_range(source_in_sec, source_out_sec, duration)
    is_audio = _is_audio_tractor(tracks[track_index])
    if is_audio:
        target_audio, target_video = track_index, _paired_index(tracks, track_index)
    else:
        target_video, target_audio = track_index, _paired_index(tracks, track_index)
    producer = resolve_producer(tree, source_id)
    kid = next_kdenlive_id(tree)
    if not audio_only and target_video is not None:
        _add_kid(tree, target_video, producer, source_in_sec, source_out_sec, position_sec, kid)
    if not video_only and target_audio is not None and _producer_has_audio(producer):
        _add_kid(tree, target_audio, producer, source_in_sec, source_out_sec, position_sec, kid)
    bump_tractor_duration(tree)
    return kid


def append_clip(
    tree: ProjectTree, track_index: int, source_id: str,
    source_in_sec: float = 0.0, source_out_sec: float | None = None,
    video_only: bool = False, audio_only: bool = False,
) -> str:
    """Append a clip to the end of the given track."""
    tracks = get_tracks(tree)
    validate_track_index(track_index, len(tracks))
    pl = get_video_playlist(tree, tracks[track_index])
    return insert_clip(
        tree, track_index=track_index, position_sec=playlist_duration(pl),
        source_id=source_id, source_in_sec=source_in_sec,
        source_out_sec=source_out_sec, video_only=video_only, audio_only=audio_only,
    )


def move_clip(tree: ProjectTree, clip_id: str, new_track: int, new_position_sec: float) -> None:
    """Move a clip. BUG 1 fix: no `playlists[0]` fallback."""
    entries = find_all_entries(tree, clip_id)
    if not entries:
        raise BackendError(f"no clip with kdenlive:id='{clip_id}' on any track")
    tracks = get_tracks(tree)
    validate_track_index(new_track, len(tracks))
    validate_position_sec(new_position_sec)
    for entry, track_idx in entries:
        parent = entry.getparent()
        if parent is not None:
            parent.remove(entry)
        is_audio = _is_audio_tractor(tracks[track_idx])
        if is_audio:
            target = _paired_index(tracks, new_track) or _first_audio(tracks) or new_track
        else:
            target = new_track
        pl = get_video_playlist(tree, tracks[target])
        if pl is None:
            continue  # BUG 1 fix: skip, don't misroute
        insert_entry_at_position(pl, entry, new_position_sec)


def trim_clip(tree: ProjectTree, clip_id: str, new_in_sec: float, new_out_sec: float) -> None:
    """Trim a clip to a new [in, out] range within the source."""
    entries = find_all_entries(tree, clip_id)
    if not entries:
        raise BackendError(f"no clip with kdenlive:id='{clip_id}' on any track")
    src_kid = _entry_source_kid(tree, entries[0][0]) or clip_id
    duration = resolve_source_duration(tree, src_kid)
    validate_clip_range(new_in_sec, new_out_sec, duration)
    for entry, _ in entries:
        old_in = _tc_to_sec(entry.get("in", "00:00:00.000"))
        entry.set("in", _sec_to_tc(new_in_sec))
        entry.set("out", _sec_to_tc(new_out_sec))
        parent = entry.getparent()
        if parent is not None:
            shift_entry_on_timeline(parent, entry, new_in_sec - old_in)
    bump_tractor_duration(tree)


def delete_clip(tree: ProjectTree, clip_id: str) -> None:
    """Remove a clip from the timeline (all its video + audio entries)."""
    entries = find_all_entries(tree, clip_id)
    if not entries:
        raise BackendError(f"no clip with kdenlive:id='{clip_id}' on any track")
    for entry, _ in entries:
        parent = entry.getparent()
        if parent is not None:
            parent.remove(entry)
    bump_tractor_duration(tree)


__all__ = ["insert_clip", "append_clip", "move_clip", "trim_clip", "delete_clip"]
