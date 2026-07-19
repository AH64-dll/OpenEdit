"""Tests for phase2_project_engine.ops.track_effects — add_effect_to_track, list_track_effects."""
from __future__ import annotations

import pytest

from phase2_project_engine.errors import NotFoundError, ValidationError
from phase2_project_engine.tests.ops_fixtures import make_minimal_tree, add_audio_track


VOLUME_CATALOG = [
    {
        "kdenlive_id": "volume",
        "mlt_service": "volume",
        "name": "Volume",
        "kdenlive_type": "audio",
        "parameters": [{"name": "level", "type": "double", "default": "1"}],
    }
]


def test_add_effect_to_track_audio_track():
    """Add a volume effect to an audio track."""
    from phase2_project_engine.ops.track_effects import add_effect_to_track
    tree = make_minimal_tree()
    add_audio_track(tree)
    audio_track_idx = _find_audio_track_index(tree)
    result = add_effect_to_track(tree, audio_track_idx, "volume",
                                  params={"level": "0.5"},
                                  catalog=VOLUME_CATALOG)
    assert result["effect_id"] == "volume"
    assert result["effect_index"] == 0


def test_add_effect_to_track_video_effect_on_audio_track_rejected():
    """A video effect cannot be added to an audio track."""
    from phase2_project_engine.ops.track_effects import add_effect_to_track
    VIDEO_CATALOG = [
        {
            "kdenlive_id": "blur",
            "mlt_service": "blur",
            "name": "Blur",
            "kdenlive_type": "video",
            "parameters": [],
        }
    ]
    tree = make_minimal_tree()
    add_audio_track(tree)
    audio_track_idx = _find_audio_track_index(tree)
    with pytest.raises(ValidationError, match="effect_id_must_be_audio"):
        add_effect_to_track(tree, audio_track_idx, "blur", catalog=VIDEO_CATALOG)


def test_list_track_effects_empty():
    """An empty track effect stack returns an empty list."""
    from phase2_project_engine.ops.track_effects import list_track_effects
    tree = make_minimal_tree()
    result = list_track_effects(tree, 0)
    assert result["track_index"] == 0
    assert result["effects"] == []


def test_list_track_effects_with_added_effect():
    """After add_effect_to_track, list returns the effect with its params."""
    from phase2_project_engine.ops.track_effects import (
        add_effect_to_track, list_track_effects,
    )
    tree = make_minimal_tree()
    add_audio_track(tree)
    audio_track_idx = _find_audio_track_index(tree)
    add_effect_to_track(tree, audio_track_idx, "volume", params={"level": "0.5"},
                        catalog=VOLUME_CATALOG)
    result = list_track_effects(tree, audio_track_idx)
    assert result["track_index"] == audio_track_idx
    assert len(result["effects"]) == 1
    assert result["effects"][0]["effect_id"] == "volume"
    assert result["effects"][0]["params"]["level"] == "0.5"


def test_list_track_effects_track_index_out_of_range():
    from phase2_project_engine.ops.track_effects import list_track_effects
    tree = make_minimal_tree()
    with pytest.raises(NotFoundError, match="track_index_out_of_range"):
        list_track_effects(tree, 999)


def _find_audio_track_index(tree):
    """Return the index of the first audio track in the tree."""
    from phase2_project_engine.tracks import get_tracks, is_audio_track
    tracks = get_tracks(tree)
    for i, tr in enumerate(tracks):
        if is_audio_track(tree, tr):
            return i
    raise RuntimeError("No audio track in fixture")
