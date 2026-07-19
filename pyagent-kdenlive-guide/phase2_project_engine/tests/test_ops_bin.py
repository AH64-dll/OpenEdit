"""Tests for phase2_project_engine.ops.bin — import_media."""
import os
import pytest

from phase2_project_engine.errors import BackendError, ValidationError
from phase2_project_engine.tests.ops_fixtures import (
    make_minimal_tree, CLIP_SHORT,
)


def test_import_media_returns_one_id_per_path():
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.bin import import_media
    tree = make_minimal_tree()
    ids = import_media(tree, [str(CLIP_SHORT)])
    assert len(ids) == 1
    assert ids[0].isdigit()


def test_import_media_assigns_unique_kdenlive_ids():
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.bin import import_media
    tree = make_minimal_tree()
    ids = import_media(tree, [str(CLIP_SHORT), str(CLIP_SHORT)])
    assert len(set(ids)) == 2


def test_import_media_creates_root_level_producers():
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.bin import import_media
    tree = make_minimal_tree()
    import_media(tree, [str(CLIP_SHORT)])
    # Producers must be direct children of the MLT root, NOT inside main_bin.
    main_bin = tree.root.find("playlist[@id='main_bin']")
    assert len(main_bin.findall("producer")) == 0
    assert len(tree.root.findall("producer")) >= 1


def test_import_media_rejects_missing_path():
    from phase2_project_engine.ops.bin import import_media
    tree = make_minimal_tree()
    with pytest.raises(ValidationError) as ei:
        import_media(tree, ["/nope/not/here.mp4"])
    assert "fix:" in str(ei.value)


def test_import_media_rejects_empty_string():
    from phase2_project_engine.ops.bin import import_media
    tree = make_minimal_tree()
    with pytest.raises(ValidationError) as ei:
        import_media(tree, [""])
    assert "fix:" in str(ei.value)
