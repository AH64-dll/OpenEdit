"""Tests for phase2_project_engine.ops.groups — group/ungroup/list using
Kdenlive's real groups format (kdenlive:sequenceproperties.groups)."""
import json
import os
import pytest

from phase2_project_engine.errors import NotFoundError, ValidationError
from phase2_project_engine.tests.ops_fixtures import (
    make_minimal_tree, CLIP_SHORT,
)


def _import_source(tree, source):
    from phase2_project_engine.ops.bin import import_media
    return import_media(tree, [str(source)])[0]


def test_group_clips_writes_json_tree():
    """group_clips writes a JSON array to kdenlive:sequenceproperties.groups
    with one Normal group containing Leaf children for each clip."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.groups import group_clips, list_groups
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    a = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                    source_in_sec=0.0, source_out_sec=3.0)
    b = insert_clip(tree, track_index=0, position_sec=3.0, source_id=src,
                    source_in_sec=0.0, source_out_sec=3.0)
    result = group_clips(tree, clip_ids=[a, b], group_name="intro")
    assert result["group_name"] == "intro"
    assert set(result["clip_ids"]) == {a, b}
    # Verify the JSON tree in the property
    tractor = tree.get_tractor()
    prop = tractor.find("property[@name='kdenlive:sequenceproperties.groups']")
    assert prop is not None
    groups = json.loads(prop.text)
    assert len(groups) == 1
    g = groups[0]
    assert g["type"] == "Normal"
    assert g["pyagent:name"] == "intro"
    assert len(g["children"]) == 2
    for child in g["children"]:
        assert child["type"] == "Leaf"
        assert child["leaf"] == "clip"
        # data format: "<track>:<pos>:-1"
        parts = child["data"].split(":")
        assert len(parts) == 3
        assert parts[2] == "-1"


def test_list_groups_returns_round_trippable_groups():
    """list_groups returns [{group_name, clip_ids}] and resolves (track, pos) -> current clip_id."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.groups import group_clips, list_groups
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    a = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                    source_in_sec=0.0, source_out_sec=3.0)
    b = insert_clip(tree, track_index=0, position_sec=3.0, source_id=src,
                    source_in_sec=0.0, source_out_sec=3.0)
    group_clips(tree, clip_ids=[a, b], group_name="intro")
    result = list_groups(tree)
    assert len(result["groups"]) == 1
    g = result["groups"][0]
    assert g["group_name"] == "intro"
    assert set(g["clip_ids"]) == {a, b}


def test_ungroup_clips_removes_group():
    """ungroup_clips removes the group with the given name."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.groups import group_clips, ungroup_clips, list_groups
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    a = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                    source_in_sec=0.0, source_out_sec=3.0)
    group_clips(tree, clip_ids=[a], group_name="solo")
    ungroup_clips(tree, group_name="solo")
    result = list_groups(tree)
    assert result["groups"] == []


def test_group_clips_rejects_duplicate_name():
    """group_clips raises duplicate_group_name ValidationError on collision."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.groups import group_clips
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    a = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                    source_in_sec=0.0, source_out_sec=3.0)
    b = insert_clip(tree, track_index=0, position_sec=3.0, source_id=src,
                    source_in_sec=0.0, source_out_sec=3.0)
    group_clips(tree, clip_ids=[a], group_name="dup")
    with pytest.raises(ValidationError) as exc:
        group_clips(tree, clip_ids=[b], group_name="dup")
    assert "duplicate_group_name" in str(exc.value)
    assert "fix:" in str(exc.value)


def test_group_clips_rejects_empty_clip_list():
    """group_clips raises empty_clip_list ValidationError when clip_ids is empty."""
    from phase2_project_engine.ops.groups import group_clips
    tree = make_minimal_tree()
    with pytest.raises(ValidationError) as exc:
        group_clips(tree, clip_ids=[], group_name="x")
    assert "empty_clip_list" in str(exc.value)
    assert "fix:" in str(exc.value)


def test_ungroup_clips_rejects_unknown_group():
    """ungroup_clips raises group_not_found NotFoundError on unknown name."""
    from phase2_project_engine.ops.groups import ungroup_clips
    tree = make_minimal_tree()
    with pytest.raises(NotFoundError) as exc:
        ungroup_clips(tree, group_name="nope")
    assert "group_not_found" in str(exc.value)


def test_list_groups_skips_avsplit_groups():
    """AVSplit groups (managed by Kdenlive) are skipped in list_groups output,
    but preserved in the JSON tree (ungroup_clips should not touch them)."""
    from phase2_project_engine.ops.groups import _load_groups, _save_groups, list_groups
    tree = make_minimal_tree()
    # Inject a fake AVSplit group alongside a Normal one
    _save_groups(tree, [
        {"type": "AVSplit", "children": [{"type": "Leaf", "leaf": "clip", "data": "0:0:-1"}]},
        {"type": "Normal", "pyagent:name": "keep", "children": []},
    ])
    result = list_groups(tree)
    # Only the Normal group appears
    names = [g["group_name"] for g in result["groups"]]
    assert names == ["keep"]
    # The AVSplit group is still in the property
    raw = _load_groups(tree)
    types = [g.get("type") for g in raw]
    assert "AVSplit" in types


def test_ungroup_clips_preserves_avsplit_groups():
    """When dissolving a Normal group, any AVSplit groups in the property
    must be left untouched (not enumerated, not removed)."""
    from phase2_project_engine.ops.clips import insert_clip
    from phase2_project_engine.ops.groups import (
        group_clips, ungroup_clips, _load_groups, _save_groups,
    )
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    a = insert_clip(tree, track_index=0, position_sec=0.0, source_id=src,
                    source_in_sec=0.0, source_out_sec=3.0)
    # Pre-seed an AVSplit group
    avsplit = {"type": "AVSplit", "children": [{"type": "Leaf", "leaf": "clip", "data": "0:0:-1"}]}
    _save_groups(tree, [avsplit])
    group_clips(tree, clip_ids=[a], group_name="dissolve_me")
    ungroup_clips(tree, group_name="dissolve_me")
    raw = _load_groups(tree)
    # AVSplit survives, Normal is gone
    assert any(g.get("type") == "AVSplit" for g in raw)
    assert not any(g.get("type") == "Normal" for g in raw)
