"""Shared test fixtures for ops tests."""
from __future__ import annotations

from pathlib import Path

from lxml import etree

from phase2_project_engine.io import ProjectTree


TESTDATA = Path("/home/ah64/apps/mlt-pipeline/testdata")
CLIP_SHORT = TESTDATA / "clip_short.mp4"


def make_minimal_tree() -> ProjectTree:
    """Create a minimal in-memory Kdenlive project for ops tests.

    Structure: <mlt> with profile, main_bin, one default video track
    (tractor -> multitrack -> track producer=video_track).
    """
    mlt = etree.Element("mlt")
    mlt.set("version", "7.40.0")
    mlt.set("producer", "main_bin")
    mlt.set("LC_NUMERIC", "C")
    profile = etree.SubElement(mlt, "profile")
    profile.set("width", "1920")
    profile.set("height", "1080")
    profile.set("progressive", "1")
    profile.set("frame_rate_num", "30")
    profile.set("frame_rate_den", "1")
    profile.set("colorspace", "709")
    profile.set("description", "1920x1080 30.00fps")
    main_bin = etree.SubElement(mlt, "playlist")
    main_bin.set("id", "main_bin")
    v1 = etree.SubElement(mlt, "playlist")
    v1.set("id", "video_track")
    tractor = etree.SubElement(mlt, "tractor")
    tractor.set("id", "main_tractor")
    tractor.set("in", "00:00:00.000")
    tractor.set("out", "00:00:00.000")
    mt = etree.SubElement(tractor, "multitrack")
    tr = etree.SubElement(mt, "track")
    tr.set("producer", "video_track")
    return ProjectTree(root=mlt, path=None)


def add_audio_track(tree: ProjectTree, audio_playlist_id: str = "audio_track") -> None:
    """Add an audio track (tractor -> track -> audio playlist).

    Marks the tractor with kdenlive:audio_track=1.
    """
    audio_pl = etree.SubElement(tree.root, "playlist")
    audio_pl.set("id", audio_playlist_id)
    audio_tractor = etree.SubElement(tree.root, "tractor")
    audio_tractor.set("id", f"{audio_playlist_id}_tractor")
    audio_tractor.set("in", "00:00:00.000")
    audio_tractor.set("out", "00:00:00.000")
    aprop = etree.SubElement(audio_tractor, "property")
    aprop.set("name", "kdenlive:audio_track")
    aprop.text = "1"
    mt = etree.SubElement(audio_tractor, "multitrack")
    tr = etree.SubElement(mt, "track")
    tr.set("producer", audio_playlist_id)


def video_playlist(tree: ProjectTree) -> etree._Element:
    return tree.root.find("playlist[@id='video_track']")


def audio_playlist(tree: ProjectTree) -> etree._Element | None:
    return tree.root.find("playlist[@id='audio_track']")


def entry_count_in(playlist: etree._Element | None) -> int:
    if playlist is None:
        return 0
    return len(playlist.findall("entry"))


def get_entry_kid(entry: etree._Element) -> str:
    for p in entry.iter("property"):
        if p.get("name") == "kdenlive:id":
            return p.text or ""
    return ""
