"""Tests for phase2_project_engine.ops.markers — add_marker."""
import pytest

from phase2_project_engine.errors import ValidationError
from phase2_project_engine.tests.ops_fixtures import make_minimal_tree


def test_add_marker_creates_marker_in_tractor():
    from phase2_project_engine.ops.markers import add_marker
    tree = make_minimal_tree()
    add_marker(tree, position_sec=2.5, label="cut point", kind="marker")
    tractor = tree.get_tractor()
    markers = tractor.findall("marker")
    assert len(markers) == 1
    m = markers[0]
    props = {p.get("name"): p.text for p in m.iter("property")}
    assert props["time"] == "00:00:02.500"
    assert props["comment"] == "cut point"
    assert props["type"] == "0"  # "marker" -> 0


def test_add_marker_guide_uses_type_1():
    from phase2_project_engine.ops.markers import add_marker
    tree = make_minimal_tree()
    add_marker(tree, position_sec=1.0, label="g", kind="guide")
    tractor = tree.get_tractor()
    markers = tractor.findall("marker")
    assert markers[0].find("property[@name='type']").text == "1"


def test_add_marker_chapter_uses_type_2():
    from phase2_project_engine.ops.markers import add_marker
    tree = make_minimal_tree()
    add_marker(tree, position_sec=3.0, label="c", kind="chapter")
    tractor = tree.get_tractor()
    markers = tractor.findall("marker")
    assert markers[0].find("property[@name='type']").text == "2"


def test_add_marker_rejects_negative_position():
    from phase2_project_engine.ops.markers import add_marker
    tree = make_minimal_tree()
    with pytest.raises(ValidationError) as ei:
        add_marker(tree, position_sec=-1.0, label="x")
    assert "fix:" in str(ei.value)


def test_add_marker_rejects_bad_kind():
    from phase2_project_engine.ops.markers import add_marker
    tree = make_minimal_tree()
    with pytest.raises(ValidationError) as ei:
        add_marker(tree, position_sec=1.0, label="x", kind="bookmark")
    assert "fix:" in str(ei.value)


def test_add_marker_normalizes_kind_case():
    from phase2_project_engine.ops.markers import add_marker
    tree = make_minimal_tree()
    add_marker(tree, position_sec=1.0, label="x", kind="GUIDE")
    tractor = tree.get_tractor()
    assert tractor.findall("marker")[0].find("property[@name='type']").text == "1"
