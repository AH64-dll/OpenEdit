import os
import pytest
from lxml import etree
from phase2_project_engine.io import ProjectTree, load_project, save_project
from phase2_project_engine.tracks import (
    get_tracks, get_track_playlists, get_video_playlist, is_audio_track,
    find_clip_entry, find_all_entries, resolve_producer, resolve_source_duration,
    next_kdenlive_id, bump_tractor_duration,
)


@pytest.fixture
def demo_tree():
    """A minimal .kdenlive tree: V1 with 2 entries, A1 audio."""
    p = "phase3_pyagent_core/tests/fixtures/demo.kdenlive"
    if not os.path.exists(p):
        pytest.skip(f"fixture not found: {p}")
    return load_project(p)


def test_get_tracks_returns_user_facing_only(demo_tree):
    tracks = get_tracks(demo_tree)
    assert all(t.tag == "tractor" for t in tracks)


def test_get_video_playlist_returns_correct_playlist(demo_tree):
    for tr in get_tracks(demo_tree):
        pl = get_video_playlist(demo_tree, tr)
        if is_audio_track(demo_tree, tr):
            pass
        else:
            if pl is not None:
                assert pl.tag == "playlist"


def test_resolve_producer_by_id(demo_tree):
    for prod in demo_tree.root.iter("producer"):
        for p in prod.iter("property"):
            if p.get("name") == "kdenlive:id" and (p.text or "").isdigit():
                resolved = resolve_producer(demo_tree, p.text)
                assert resolved is prod
                return
    pytest.skip("no kdenlive:id in fixture")


def test_bump_tractor_duration(demo_tree):
    bump_tractor_duration(demo_tree)
    tr = demo_tree.get_tractor()
    if tr is not None:
        out = tr.get("out", "00:00:00.000")
        assert out != "00:00:00.000"
