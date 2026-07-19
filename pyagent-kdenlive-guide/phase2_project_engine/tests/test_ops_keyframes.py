"""Tests for phase2_project_engine.ops.keyframes — list/set/remove keyframe."""
from __future__ import annotations

import pytest

from phase2_project_engine.errors import ValidationError
from phase2_project_engine.tests.ops_fixtures import (
    make_minimal_tree,
    CLIP_SHORT,
)


def _import_source(tree, source):
    from phase2_project_engine.ops.bin import import_media
    return import_media(tree, [str(source)])[0]


def _insert_clip(tree, source, src_id):
    from phase2_project_engine.ops.clips import insert_clip
    return insert_clip(
        tree, track_index=0, position_sec=0.0, source_id=src_id,
        source_in_sec=0.0, source_out_sec=5.0,
    )


BRIGHTNESS_CATALOG = [
    {
        "kdenlive_id": "brightness",
        "mlt_service": "brightness",
        "name": "Intensity",
        "parameters": [
            {"name": "level", "type": "animated", "default": "1",
             "keyframes": True},
        ],
    }
]


def test_list_keyframes_with_animation_string():
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.effects import apply_effect
    from phase2_project_engine.ops.keyframes import list_keyframes
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = _insert_clip(tree, CLIP_SHORT, src)
    apply_effect(tree, kid, "brightness",
                 params={"level": "0=1.0; 25~0.5; 50=0.0"},
                 catalog=BRIGHTNESS_CATALOG)
    result = list_keyframes(tree, kid, 0, "level")
    assert result["format"] == "animated"
    assert result["keyframes"] == [
        {"frame": 0, "value": "1.0", "type": ""},
        {"frame": 25, "value": "0.5", "type": "~"},
        {"frame": 50, "value": "0.0", "type": ""},
    ]


def test_list_keyframes_empty():
    """Non-keyframable params return empty list and format=''."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.effects import apply_effect
    from phase2_project_engine.ops.keyframes import list_keyframes
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = _insert_clip(tree, CLIP_SHORT, src)
    apply_effect(tree, kid, "brightness", params={"level": "0.5"},
                 catalog=BRIGHTNESS_CATALOG)
    result = list_keyframes(tree, kid, 0, "level")
    assert result["format"] == ""
    assert result["keyframes"] == []


def test_set_keyframe_adds_new():
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.effects import apply_effect
    from phase2_project_engine.ops.keyframes import set_keyframe, list_keyframes
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = _insert_clip(tree, CLIP_SHORT, src)
    apply_effect(tree, kid, "brightness",
                 params={"level": "0=1.0; 50=0.0"},
                 catalog=BRIGHTNESS_CATALOG)
    result = set_keyframe(tree, kid, 0, "level", 25, "0.5", "smooth")
    assert result["action"] == "added"
    kfs = list_keyframes(tree, kid, 0, "level")
    assert len(kfs["keyframes"]) == 3
    assert kfs["keyframes"][1] == {"frame": 25, "value": "0.5", "type": "~"}


def test_set_keyframe_updates_existing():
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.effects import apply_effect
    from phase2_project_engine.ops.keyframes import set_keyframe
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = _insert_clip(tree, CLIP_SHORT, src)
    apply_effect(tree, kid, "brightness",
                 params={"level": "0=1.0; 25=0.5; 50=0.0"},
                 catalog=BRIGHTNESS_CATALOG)
    result = set_keyframe(tree, kid, 0, "level", 25, "0.7", "linear")
    assert result["action"] == "updated"
    assert result["value"] == "0.7"


def test_set_keyframe_invalid_type():
    from phase2_project_engine.errors import ValidationError
    from phase2_project_engine.ops.keyframes import set_keyframe
    tree = make_minimal_tree()
    with pytest.raises(ValidationError, match="invalid_type"):
        set_keyframe(tree, "2", 0, "level", 0, "1.0", "bogus_curve_type")


def test_remove_keyframe_existing():
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.effects import apply_effect
    from phase2_project_engine.ops.keyframes import remove_keyframe, list_keyframes
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = _insert_clip(tree, CLIP_SHORT, src)
    apply_effect(tree, kid, "brightness",
                 params={"level": "0=1.0; 25=0.5; 50=0.0"},
                 catalog=BRIGHTNESS_CATALOG)
    result = remove_keyframe(tree, kid, 0, "level", 25)
    assert result["removed"] is True
    kfs = list_keyframes(tree, kid, 0, "level")
    assert len(kfs["keyframes"]) == 2


def test_remove_keyframe_nonexistent_is_noop():
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.effects import apply_effect
    from phase2_project_engine.ops.keyframes import remove_keyframe
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = _insert_clip(tree, CLIP_SHORT, src)
    apply_effect(tree, kid, "brightness", params={"level": "0.5"},
                 catalog=BRIGHTNESS_CATALOG)
    result = remove_keyframe(tree, kid, 0, "level", 999)
    assert result["removed"] is False


SIMPLEKEYFRAME_CATALOG = [
    {
        "kdenlive_id": "rotation_keyframable",
        "mlt_service": "affine",
        "name": "Rotate (keyframable)",
        "parameters": [
            {"name": "transition.rotate_x", "type": "simplekeyframe",
             "keyframes": "simplekeyframe"},
        ],
    }
]


def test_set_keyframe_on_simplekeyframe_rejected():
    """set_keyframe on a simplekeyframe param raises
    simplekeyframe_format_unsupported (spec error code)."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.effects import apply_effect
    from phase2_project_engine.ops.keyframes import set_keyframe
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = _insert_clip(tree, CLIP_SHORT, src)
    apply_effect(tree, kid, "rotation_keyframable",
                 params={"transition.rotate_x": "0=0"},
                 catalog=SIMPLEKEYFRAME_CATALOG)
    with pytest.raises(ValidationError, match="simplekeyframe_format_unsupported"):
        set_keyframe(tree, kid, 0, "transition.rotate_x", 10, "0.5",
                     catalog=SIMPLEKEYFRAME_CATALOG)


def test_remove_keyframe_on_simplekeyframe_rejected():
    """remove_keyframe on a simplekeyframe param raises
    simplekeyframe_format_unsupported (spec error code)."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.effects import apply_effect
    from phase2_project_engine.ops.keyframes import remove_keyframe
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = _insert_clip(tree, CLIP_SHORT, src)
    apply_effect(tree, kid, "rotation_keyframable",
                 params={"transition.rotate_x": "0=0"},
                 catalog=SIMPLEKEYFRAME_CATALOG)
    with pytest.raises(ValidationError, match="simplekeyframe_format_unsupported"):
        remove_keyframe(tree, kid, 0, "transition.rotate_x", 0,
                        catalog=SIMPLEKEYFRAME_CATALOG)
