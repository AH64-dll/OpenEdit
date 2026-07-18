"""Tests for phase2_project_engine.ops.clips — insert/append/move/trim/delete.

Includes the BUG 1 regression test: insert_clip into an audio track
must NOT misroute the entry into the video playlist.
"""
import os
import pytest

from phase2_project_engine.errors import BackendError, ValidationError
from phase2_project_engine.tests.ops_fixtures import (
    make_minimal_tree, add_audio_track, CLIP_SHORT,
    video_playlist, audio_playlist, entry_count_in,
)


def _import_source(tree, source):
    from phase2_project_engine.ops.bin import import_media
    return import_media(tree, [str(source)])[0]


def test_insert_clip_into_video_track_writes_to_video_playlist():
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = insert_clip(
        tree, track_index=0, position_sec=0.0, source_id=src,
        source_in_sec=0.0, source_out_sec=5.0,
    )
    assert kid.isdigit()
    pl = video_playlist(tree)
    assert entry_count_in(pl) == 1
    e = pl.findall("entry")[0]
    assert e.get("in") == "00:00:00.000"
    assert e.get("out") == "00:00:05.000"


def test_insert_clip_into_audio_track_does_not_misroute_to_video():
    """BUG 1 regression: the audio insert must NOT fall back to
    playlists[0] of the audio tractor (which would be the audio
    playlist, but a buggy implementation could pick a video one).

    With the BUG 1 fix, when the audio track's video_playlist
    cannot be identified with confidence, the audio insert is
    skipped — the audio track stays empty, and we do NOT silently
    misroute the entry to a video playlist."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    tree = make_minimal_tree()
    add_audio_track(tree)
    src = _import_source(tree, CLIP_SHORT)
    insert_clip(
        tree, track_index=1, position_sec=0.0, source_id=src,
        source_in_sec=0.0, source_out_sec=5.0,
    )
    # The audio track (track 1) must remain empty — the audio
    # insert was correctly skipped because get_video_playlist
    # returned None (no video content in the audio playlist) and
    # we no longer fall back to playlists[0].
    assert entry_count_in(audio_playlist(tree)) == 0
    # The video playlist gets the paired video insert (track 0
    # is the pair of audio track 1) — this is the intended
    # dual-track behavior, NOT a misroute.
    assert entry_count_in(video_playlist(tree)) == 1


def test_insert_clip_rejects_out_of_range_track():
    from phase2_project_engine.ops.clips import insert_clip
    tree = make_minimal_tree()
    with pytest.raises(ValidationError) as ei:
        insert_clip(tree, track_index=99, position_sec=0.0, source_id="1")
    assert "fix:" in str(ei.value)


def test_insert_clip_rejects_negative_position():
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    with pytest.raises(ValidationError) as ei:
        insert_clip(
            tree, track_index=0, position_sec=-1.0, source_id=src,
            source_in_sec=0.0, source_out_sec=2.0,
        )
    assert "fix:" in str(ei.value)


def test_insert_clip_rejects_inverted_range():
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    with pytest.raises(ValidationError) as ei:
        insert_clip(
            tree, track_index=0, position_sec=0.0, source_id=src,
            source_in_sec=5.0, source_out_sec=2.0,
        )
    assert "fix:" in str(ei.value)


def test_insert_clip_rejects_unknown_source():
    from phase2_project_engine.ops.clips import insert_clip
    tree = make_minimal_tree()
    with pytest.raises(Exception) as ei:
        insert_clip(
            tree, track_index=0, position_sec=0.0, source_id="9999",
        )
    assert "no bin entry" in str(ei.value).lower()


def test_append_clip_lands_at_end_of_track():
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip, append_clip
    from phase2_project_engine.ops._helpers import entry_start_sec
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    insert_clip(
        tree, track_index=0, position_sec=0.0, source_id=src,
        source_in_sec=0.0, source_out_sec=3.0,
    )
    append_clip(tree, track_index=0, source_id=src, source_in_sec=0.0, source_out_sec=2.0)
    pl = video_playlist(tree)
    entries = pl.findall("entry")
    assert len(entries) == 2
    # First entry: timeline 0..3, second: timeline 3..5
    assert entry_start_sec(pl, entries[0]) == 0.0
    assert entry_start_sec(pl, entries[1]) == 3.0


def test_move_clip_to_new_position():
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip, move_clip
    from phase2_project_engine.ops._helpers import entry_start_sec
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = insert_clip(
        tree, track_index=0, position_sec=0.0, source_id=src,
        source_in_sec=0.0, source_out_sec=5.0,
    )
    move_clip(tree, kid, new_track=0, new_position_sec=10.0)
    pl = video_playlist(tree)
    entries = pl.findall("entry")
    assert len(entries) == 1
    # `in` is the SOURCE in (unchanged by move); the timeline
    # position is what we moved.
    assert entry_start_sec(pl, entries[0]) == 10.0


def test_move_clip_rejects_negative_position():
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip, move_clip
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = insert_clip(
        tree, track_index=0, position_sec=0.0, source_id=src,
        source_in_sec=0.0, source_out_sec=2.0,
    )
    with pytest.raises(ValidationError) as ei:
        move_clip(tree, kid, new_track=0, new_position_sec=-1.0)
    assert "fix:" in str(ei.value)


def test_trim_clip_changes_in_out():
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip, trim_clip
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = insert_clip(
        tree, track_index=0, position_sec=0.0, source_id=src,
        source_in_sec=0.0, source_out_sec=5.0,
    )
    trim_clip(tree, kid, new_in_sec=1.0, new_out_sec=4.0)
    pl = video_playlist(tree)
    entries = pl.findall("entry")
    assert entries[0].get("in") == "00:00:01.000"
    assert entries[0].get("out") == "00:00:04.000"


def test_trim_clip_rejects_inverted_range():
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip, trim_clip
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = insert_clip(
        tree, track_index=0, position_sec=0.0, source_id=src,
        source_in_sec=0.0, source_out_sec=5.0,
    )
    with pytest.raises(ValidationError) as ei:
        trim_clip(tree, kid, new_in_sec=4.0, new_out_sec=2.0)
    assert "fix:" in str(ei.value)


def test_delete_clip_removes_entry():
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip, delete_clip
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = insert_clip(
        tree, track_index=0, position_sec=0.0, source_id=src,
        source_in_sec=0.0, source_out_sec=5.0,
    )
    assert entry_count_in(video_playlist(tree)) == 1
    delete_clip(tree, kid)
    assert entry_count_in(video_playlist(tree)) == 0


def test_delete_clip_rejects_unknown_id():
    from phase2_project_engine.ops.clips import delete_clip
    tree = make_minimal_tree()
    with pytest.raises(Exception) as ei:
        delete_clip(tree, "99999")
    assert "no clip" in str(ei.value).lower()
