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


# --- clips-edit ops (slip / ripple / speed / split / replace) -------------


def test_slip_clip_shifts_source_within_fixed_window():
    """slip with delta=+1.0 shifts source_in and source_out each by 1.0;
    timeline position and duration are unchanged."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.clips_edit import slip_clip
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                      source_in_sec=0.0, source_out_sec=5.0)
    pre = slip_clip(tree, kid, delta_sec=0.0)
    post = slip_clip(tree, kid, delta_sec=1.0)
    assert abs(post["source_in_sec"] - (pre["source_in_sec"] + 1.0)) < 1e-6
    assert abs(post["source_out_sec"] - (pre["source_out_sec"] + 1.0)) < 1e-6
    assert post["timeline_start_sec"] == pre["timeline_start_sec"]
    assert post["duration_sec"] == pre["duration_sec"]


def test_slip_clip_raises_source_oob_on_out_of_bounds_delta():
    """A delta that would push source_in below 0 raises source_oob."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.clips_edit import slip_clip
    from phase2_project_engine.errors import NotFoundError
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                      source_in_sec=0.0, source_out_sec=5.0)
    with pytest.raises(NotFoundError) as exc:
        slip_clip(tree, kid, delta_sec=-100.0)
    assert "source_oob" in str(exc.value)


def test_change_clip_speed_halves_duration_at_rate_2():
    """rate=2.0 halves the clip's duration on the timeline."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.clips_edit import change_clip_speed
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                      source_in_sec=0.0, source_out_sec=10.0)
    pre_dur = change_clip_speed(tree, kid, rate=1.0)["new_duration_sec"]
    result = change_clip_speed(tree, kid, rate=2.0)
    assert abs(result["new_duration_sec"] - pre_dur / 2.0) < 1e-3
    assert result["rate"] == 2.0


def test_change_clip_speed_rejects_rate_out_of_range():
    """rate > 10.0 raises rate_out_of_range ValidationError."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.clips_edit import change_clip_speed
    from phase2_project_engine.errors import ValidationError
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                      source_in_sec=0.0, source_out_sec=5.0)
    with pytest.raises(ValidationError) as exc:
        change_clip_speed(tree, kid, rate=11.0)
    assert "rate_out_of_range" in str(exc.value)
    assert "fix:" in str(exc.value)


def test_split_clip_returns_left_and_right_clip_ids():
    """split returns the original clip_id (left) and a new id (right)."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.clips_edit import split_clip
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                      source_in_sec=0.0, source_out_sec=10.0)
    result = split_clip(tree, kid, at_sec=4.0)
    assert result["left_clip_id"] == kid
    assert result["right_clip_id"] != kid
    assert result["right_clip_id"].isdigit()


def test_ripple_delete_clip_removes_entry_and_shifts_following():
    """ripple_delete removes the entry and returns the ids of clips that
    follow it on the same track (whose timeline positions change)."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.clips_edit import ripple_delete_clip
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    a = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                    source_in_sec=0.0, source_out_sec=3.0)
    b = insert_clip(tree, track_index=0, position_sec=3.0, source_id=src,
                    source_in_sec=0.0, source_out_sec=3.0)
    result = ripple_delete_clip(tree, a)
    assert result["deleted_clip_id"] == a
    assert b in result["shifted_clip_ids"]
    pl = video_playlist(tree)
    ids = [e.find("property[@name='kdenlive:id']").text
           for e in pl.findall("entry") if e.find("property[@name='kdenlive:id']") is not None]
    assert a not in ids
    assert b in ids


def test_replace_clip_source_resets_rate_and_source_in():
    """replace_clip_source resets source_in to 0, source_out to min(old, new_source),
    and rate to 1.0."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.clips_edit import replace_clip_source
    tree = make_minimal_tree()
    src1 = _import_source(tree, CLIP_SHORT)
    src2 = _import_source(tree, CLIP_SHORT)  # same file, but different source id
    kid = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src1,
                      source_in_sec=2.0, source_out_sec=8.0)
    result = replace_clip_source(tree, kid, new_source_id=src2)
    assert result["new_source_id"] == src2
    assert result["source_in_sec"] == 0.0
    assert result["new_rate"] == 1.0
    assert result["old_duration_sec"] == 6.0
    assert result["new_duration_sec"] == 6.0  # source is the same length
