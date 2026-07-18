"""tracks.py — track, clip, and producer navigation helpers.

These are pure functions that take a ProjectTree as the first argument
and know Kdenlive's track conventions:
  - a "track tractor" holds <track producer="playlistN"/> refs
  - audio tracks are marked with property kdenlive:audio_track=1
  - some files invert that (audio-marked tractor holds video content)
    so we detect that case by checking playlist entry content

Pure functions, no class state, so ops can call these directly:
  get_tracks(tree), get_video_playlist(tree, tr), etc.
"""
from __future__ import annotations

from lxml import etree

from .errors import BackendError
from .io import _probe_duration_sec, _sec_to_tc, _tc_to_sec


# --- Tracks -----------------------------------------------------------------


def get_tracks(tree) -> list[etree._Element]:
    """Return the user-facing track tractors, in the order Kdenlive
    renders them: video first, audio at the end.

    Skipped:
      - the main sequence tractor (referenced from main_bin)
      - any tractor that has no <track> children at all
      - tractors with kdenlive:projectTractor=1

    Audio-marked tractors are moved to the END of the returned list
    regardless of XML order.
    """
    mb = tree.root.find("playlist[@id='main_bin']")
    main_seq_id = None
    if mb is not None:
        for e in mb.findall("entry"):
            prod = e.get("producer")
            if prod and prod.startswith("{"):
                main_seq_id = prod
                break
    video_tracks: list[etree._Element] = []
    audio_tracks: list[etree._Element] = []
    for tr in tree.root.findall("tractor"):
        tid = tr.get("id") or ""
        if tid == main_seq_id:
            continue
        if tr.find("property[@name='kdenlive:projectTractor']") is not None:
            continue
        if not tr.findall(".//track"):
            continue
        at = tr.find("property[@name='kdenlive:audio_track']")
        if at is not None and at.text == "1":
            audio_tracks.append(tr)
        else:
            video_tracks.append(tr)
    return video_tracks + audio_tracks


def get_track_playlists(tree, tractor: etree._Element) -> list[etree._Element]:
    """Return the child playlists of a track tractor, resolved by
    following each <track producer="..."> reference.

    Kdenlive's track structure varies:
      - Real Kdenlive files: <tractor><track producer="playlistN"/></tractor>
      - Our generated files: <tractor><multitrack><track .../></multitrack></tractor>
    We handle both via .//track which finds tracks at any depth.
    """
    result: list[etree._Element] = []
    for tref in tractor.findall(".//track"):
        prod_id = tref.get("producer")
        if not prod_id:
            continue
        pl = tree.root.find(f"playlist[@id='{prod_id}']")
        if pl is not None:
            result.append(pl)
    return result


def is_audio_track(tree, tractor: etree._Element) -> bool:
    """True if the tractor is marked kdenlive:audio_track=1."""
    at = tractor.find("property[@name='kdenlive:audio_track']")
    return at is not None and at.text == "1"


def get_video_playlist(tree, tractor: etree._Element) -> etree._Element | None:
    """Return the playlist to write video entries to, or None.

    Kdenlive's track structure: a track tractor has 1-2 child
    playlists (video + audio). The tractor has kdenlive:audio_track=1
    only for the audio track. The video playlist is the OTHER one
    (the tractor without that property).

    In some files (like the demo edit.kdenlive), the structure is
    inverted: a tractor with kdenlive:audio_track=1 has child
    tracks that hold VIDEO content. We detect that case by checking
    whether the tractor's first child playlist already has video
    entries (entries whose producers have resource/avformat
    service), and return it if so.

    BUG 1 fix: removed the `playlists[0]` fallback. If we cannot
    identify a video playlist with confidence, return None instead
    of guessing.
    """
    playlists = get_track_playlists(tree, tractor)
    if not playlists:
        return None
    if is_audio_track(tree, tractor):
        for pl in playlists:
            if _playlist_has_video_entries(tree, pl):
                return pl
        return None
    for pl in playlists:
        if pl.get("kdenlive:audio_track") == "1":
            continue
        return pl
    return None


def _playlist_has_video_entries(tree, pl: etree._Element) -> bool:
    """True if any entry in this playlist references a video producer
    (one with a resource path / avformat service, NOT just an audio
    waveform)."""
    for e in pl.findall("entry"):
        prod = tree.root.find(f"producer[@id='{e.get('producer')}']")
        if prod is None:
            continue
        svc = prod.find("property[@name='mlt_service']")
        if svc is not None and svc.text and "audio" in (svc.text or "").lower():
            continue
        res = prod.find("property[@name='resource']")
        if res is not None and res.text:
            return True
    return False


# --- Producers --------------------------------------------------------------


def resolve_producer(tree, source_id: str) -> etree._Element:
    """Resolve a bin producer from any id form the caller might pass.

    Accepts:
      * the producer's `kdenlive:id` property (e.g. "1", "21"),
      * the MLT producer `id` attribute (e.g. "producer_41"),
      * a timeline ENTRY's `kdenlive:id` (e.g. "12") — we follow
        the entry's `producer` attribute to the real bin producer.

    BUG 6 fix: this is now the SINGLE source for finding a producer.
    Earlier code had 3 separate helpers (_resolve_producer_by_id,
    _resolve_source_duration, _find_clip_source_kdenlive_id) that all
    did similar searches with subtle differences; this consolidates
    them into one function.
    """
    if not source_id:
        raise BackendError(
            "resolve_producer called with empty source_id",
            "fix: pass the kdenlive:id from get_timeline_summary() or the "
            "producer's id attribute (e.g. 'producer_41')",
        )
    # 1) producer's kdenlive:id property
    for prod in tree.root.iter("producer"):
        for p in prod.iter("property"):
            if p.get("name") == "kdenlive:id" and p.text == source_id:
                return prod
    # 2) MLT producer id attribute (e.g. "producer_41")
    for prod in tree.root.iter("producer"):
        if prod.get("id") == source_id:
            return prod
    # 3) a timeline entry's kdenlive:id -> resolve its producer
    for pl in tree.root.iter("playlist"):
        for entry in pl.iter("entry"):
            for p in entry.iter("property"):
                if p.get("name") == "kdenlive:id" and p.text == source_id:
                    entry_prod = entry.get("producer", "")
                    if entry_prod:
                        return resolve_producer(tree, entry_prod)
                    break
    raise BackendError(
        f"no bin entry with kdenlive:id='{source_id}'",
        "fix: call import_media() with the source path first, then "
        "use the returned id, or pass the bin producer's kdenlive:id "
        "from get_timeline_summary()'s source_id field",
    )


def resolve_source_duration(tree, source_id: str) -> float:
    """Return the source duration in seconds for a producer."""
    prod = resolve_producer(tree, source_id)
    for p in prod.iter("property"):
        if p.get("name") == "kdenlive:duration":
            return _tc_to_sec(p.text or "0")
    for p in prod.iter("property"):
        if p.get("name") == "resource":
            return _probe_duration_sec_path(p.text)
    return 0.0


def _probe_duration_sec_path(path_str: str | None) -> float:
    """Thin wrapper around io._probe_duration_sec that tolerates
    a string (vs. the original's Path argument) and a missing file."""
    if not path_str:
        return 0.0
    from pathlib import Path
    return _probe_duration_sec(Path(path_str))


# --- Clip entries -----------------------------------------------------------


def find_clip_entry(tree, clip_id: str) -> tuple[etree._Element, int]:
    """Return (entry, track_index) for the first entry on any track
    with kdenlive:id == clip_id. Raises BackendError if not found."""
    for i, tr in enumerate(get_tracks(tree)):
        for pl in get_track_playlists(tree, tr):
            for entry in pl.iter("entry"):
                for p in entry.iter("property"):
                    if p.get("name") == "kdenlive:id" and p.text == clip_id:
                        return entry, i
    raise BackendError(
        f"no clip with kdenlive:id='{clip_id}' on any track",
        "fix: call get_timeline_summary() to see the current clip ids",
    )


def find_all_entries(tree, clip_id: str) -> list[tuple[etree._Element, int]]:
    """Return a list of (entry, track_index) for every entry across all
    tracks with kdenlive:id == clip_id. Empty list if none found
    (does not raise)."""
    results: list[tuple[etree._Element, int]] = []
    for i, tr in enumerate(get_tracks(tree)):
        for pl in get_track_playlists(tree, tr):
            for entry in pl.iter("entry"):
                for p in entry.iter("property"):
                    if p.get("name") == "kdenlive:id" and p.text == clip_id:
                        results.append((entry, i))
    return results


# --- Id + tractor duration --------------------------------------------------


def next_kdenlive_id(tree) -> str:
    """Return the next free numeric kdenlive:id as a string."""
    used: set[int] = set()
    for p in tree.root.iter("property"):
        if p.get("name") == "kdenlive:id" and (p.text or "").isdigit():
            used.add(int(p.text or "0"))
    n = 1
    while n in used:
        n += 1
    return str(n)


def bump_tractor_duration(tree) -> None:
    """Set the main tractor's `out` attribute to the max out of any entry."""
    t = tree.get_tractor()
    if t is None:
        return
    max_out = 0.0
    for e in tree.root.iter("entry"):
        max_out = max(max_out, _tc_to_sec(e.get("out", "00:00:00.000")))
    t.set("out", _sec_to_tc(max_out))
