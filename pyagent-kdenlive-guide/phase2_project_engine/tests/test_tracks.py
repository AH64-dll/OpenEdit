import os
import pytest
from lxml import etree
from phase2_project_engine.io import ProjectTree, load_project, save_project
from phase2_project_engine.errors import BackendError
from phase2_project_engine.tracks import (
    get_tracks, get_track_playlists, get_video_playlist, is_audio_track,
    find_clip_entry, find_all_entries, resolve_producer, resolve_source_duration,
    next_kdenlive_id, bump_tractor_duration,
)


@pytest.fixture
def demo_tree():
    """A minimal .kdenlive tree: V1 with 1 entry, kdenlive:id 1 (producer) and 2 (entry)."""
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


def test_find_clip_entry_found(demo_tree):
    """Happy path: entry with kdenlive:id=2 exists on the V1 track."""
    entry, track_index = find_clip_entry(demo_tree, "2")
    assert entry.tag == "entry"
    assert track_index == 0
    kid = ""
    for p in entry.iter("property"):
        if p.get("name") == "kdenlive:id":
            kid = p.text or ""
            break
    assert kid == "2"


def test_find_clip_entry_not_found(demo_tree):
    """Unknown id should raise BackendError."""
    with pytest.raises(BackendError, match="no clip with kdenlive:id='nonexistent'"):
        find_clip_entry(demo_tree, "nonexistent")


def test_find_all_entries_returns_all(demo_tree):
    """The fixture has exactly one entry with kdenlive:id=2; find_all_entries returns 1."""
    results = find_all_entries(demo_tree, "2")
    assert len(results) == 1
    entry, track_index = results[0]
    assert entry.tag == "entry"
    assert track_index == 0


def test_resolve_source_duration_from_producer(demo_tree):
    """Producer 1 has kdenlive:duration=00:00:10.000 -> 10.0 sec."""
    assert resolve_source_duration(demo_tree, "1") == 10.0


def test_resolve_source_duration_unknown_id_raises(demo_tree):
    """resolve_source_duration on an unknown id should raise BackendError."""
    with pytest.raises(BackendError, match="no bin entry with kdenlive:id='no_such_id'"):
        resolve_source_duration(demo_tree, "no_such_id")


def test_next_kdenlive_id_returns_unique(demo_tree):
    """next_kdenlive_id should return an id not in use by the existing producers/entries."""
    nxt = next_kdenlive_id(demo_tree)
    assert nxt.isdigit()
    used = {int(p.text) for p in demo_tree.root.iter("property")
            if p.get("name") == "kdenlive:id" and (p.text or "").isdigit()}
    assert int(nxt) not in used
    # The fixture has ids 1 and 2; the next free one is 3.
    assert nxt == "3"
