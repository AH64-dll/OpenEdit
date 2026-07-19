"""Tests for phase2_project_engine.ops.transitions — add_transition.

Includes the BUG 3 regression test: cross-track transitions must raise
ValidationError with a `fix:` line that names the source track.
Includes the BUG 10 regression test: the transition must be written
to the tractor that owns the playlist where the clips live.
"""
import pytest

from phase2_project_engine.errors import ValidationError
from phase2_project_engine.tests.ops_fixtures import (
    make_minimal_tree, add_audio_track, CLIP_SHORT,
)


def _import_source(tree, source):
    from phase2_project_engine.ops.bin import import_media
    return import_media(tree, [str(source)])[0]


def _two_clips_on_track_0(tree, source):
    from phase2_project_engine.ops.clips import insert_clip, append_clip
    a = insert_clip(
        tree, track_index=0, position_sec=0.0, source_id=source,
        source_in_sec=0.0, source_out_sec=5.0,
    )
    b = append_clip(
        tree, track_index=0, source_id=source,
        source_in_sec=0.0, source_out_sec=5.0,
    )
    return a, b


def test_add_transition_returns_id_and_writes_to_correct_tractor():
    """BUG 10 regression: transition must be inserted into the
    tractor that owns the playlist where the clips live (track_a),
    NOT into get_tractor() (the main sequence tractor)."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.transitions import add_transition
    from phase2_project_engine.tracks import get_tracks
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    a, b = _two_clips_on_track_0(tree, src)
    tid = add_transition(
        tree, clip_a_id=a, clip_b_id=b, kind="dissolve", duration_sec=1.0,
        catalog=[{"kdenlive_id": "dissolve", "mlt_service": "luma"}],
    )
    assert tid.isdigit()
    # The transition must be a child of tracks[0]'s tractor (the
    # one that owns the video playlist), not the main sequence tractor.
    tracks = get_tracks(tree)
    video_tractor = tracks[0]
    transitions_in_video = video_tractor.findall("transition")
    assert len(transitions_in_video) == 1


def test_add_transition_rejects_unknown_kind():
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.transitions import add_transition
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    a, b = _two_clips_on_track_0(tree, src)
    with pytest.raises(ValidationError) as ei:
        add_transition(
            tree, clip_a_id=a, clip_b_id=b, kind="fancy_unknown",
            duration_sec=1.0,
            catalog=[{"kdenlive_id": "dissolve", "mlt_service": "luma"}],
        )
    assert "fix:" in str(ei.value)
    assert "catalog" in str(ei.value).lower()


def _add_second_video_track(tree, playlist_id="video_track_2"):
    """Add a second video track to the project (tractor -> track -> playlist)."""
    from lxml import etree
    pl2 = etree.SubElement(tree.root, "playlist")
    pl2.set("id", playlist_id)
    tr2 = etree.SubElement(tree.root, "tractor")
    tr2.set("id", f"{playlist_id}_tractor")
    tr2.set("in", "00:00:00.000")
    tr2.set("out", "00:00:00.000")
    mt2 = etree.SubElement(tr2, "multitrack")
    track_ref = etree.SubElement(mt2, "track")
    track_ref.set("producer", playlist_id)


def test_add_transition_rejects_cross_track_with_fix_hint():
    """BUG 3 regression: cross-track transitions raise a
    ValidationError with a `fix:` line that names the source track
    where the caller should move the second clip."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.transitions import add_transition
    from phase2_project_engine.ops.clips import insert_clip
    tree = make_minimal_tree()
    _add_second_video_track(tree)
    src = _import_source(tree, CLIP_SHORT)
    a = insert_clip(
        tree, track_index=0, position_sec=0.0, source_id=src,
        source_in_sec=0.0, source_out_sec=5.0,
    )
    b = insert_clip(
        tree, track_index=1, position_sec=0.0, source_id=src,
        source_in_sec=0.0, source_out_sec=5.0,
    )
    with pytest.raises(ValidationError) as ei:
        add_transition(
            tree, clip_a_id=a, clip_b_id=b, kind="dissolve", duration_sec=1.0,
            catalog=[{"kdenlive_id": "dissolve", "mlt_service": "luma"}],
        )
    msg = str(ei.value)
    assert "fix:" in msg
    # The fix hint should name the source track so the caller knows
    # where to move the other clip.
    assert "track 0" in msg
