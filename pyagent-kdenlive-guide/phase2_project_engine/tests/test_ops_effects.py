"""Tests for phase2_project_engine.ops.effects — apply_effect.

Includes the BUG 5 regression test: apply_effect with no params must
read defaults from the catalog. Includes the BUG 9 regression test:
the effect label property must be `kdenlive:id` (with a colon), not
`kdenlive_id` (snake).
"""
import os
import pytest

from phase2_project_engine.errors import ValidationError, CatalogError
from phase2_project_engine.tests.ops_fixtures import (
    make_minimal_tree, CLIP_SHORT, video_playlist,
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
            {"name": "level", "type": "animated", "default": "1"},
        ],
    }
]


def test_apply_effect_with_explicit_params():
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.effects import apply_effect
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = _insert_clip(tree, CLIP_SHORT, src)
    eid = apply_effect(
        tree, clip_id=kid, effect_id="brightness",
        params={"level": "2.5"}, catalog=BRIGHTNESS_CATALOG,
    )
    assert eid == "brightness"
    pl = video_playlist(tree)
    entry = pl.findall("entry")[0]
    # The level param should be present in the filter.
    level = None
    for f in entry.iter("filter"):
        for p in f.iter("property"):
            if p.get("name") == "level":
                level = p.text
    assert level is not None
    assert float(level) == 2.5


def test_apply_effect_with_no_params_uses_catalog_defaults():
    """BUG 5 regression: when params is empty/None, the catalog's
    parameter `default` values should be written to the filter."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.effects import apply_effect
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = _insert_clip(tree, CLIP_SHORT, src)
    apply_effect(
        tree, clip_id=kid, effect_id="brightness", params=None,
        catalog=BRIGHTNESS_CATALOG,
    )
    pl = video_playlist(tree)
    entry = pl.findall("entry")[0]
    level = None
    for f in entry.iter("filter"):
        for p in f.iter("property"):
            if p.get("name") == "level":
                level = p.text
    # The brightness effect has default level=1
    assert level is not None
    assert float(level) == 1.0


def test_apply_effect_writes_kdenlive_id_with_colon():
    """BUG 9 regression: the effect label property name must be
    `kdenlive:id` (with a colon), not `kdenlive_id` (snake)."""
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.effects import apply_effect
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = _insert_clip(tree, CLIP_SHORT, src)
    apply_effect(
        tree, clip_id=kid, effect_id="brightness", params=None,
        catalog=BRIGHTNESS_CATALOG,
    )
    pl = video_playlist(tree)
    entry = pl.findall("entry")[0]
    has_colon_label = any(
        p.get("name") == "kdenlive:id" and p.text == "brightness"
        for p in entry.iter("property")
    )
    has_snake_label = any(
        p.get("name") == "kdenlive_id" for p in entry.iter("property")
    )
    assert has_colon_label, "effect must write kdenlive:id (colon) label"
    assert not has_snake_label, "effect must NOT write kdenlive_id (snake) label"


def test_apply_effect_rejects_unknown_id():
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.effects import apply_effect
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = _insert_clip(tree, CLIP_SHORT, src)
    with pytest.raises(ValidationError) as ei:
        apply_effect(
            tree, clip_id=kid, effect_id="nope_not_an_effect",
            catalog=BRIGHTNESS_CATALOG,
        )
    assert "fix:" in str(ei.value)
    assert "catalog" in str(ei.value).lower()


def test_apply_effect_rejects_bad_param_name():
    if not CLIP_SHORT.exists():
        pytest.skip(f"missing testdata: {CLIP_SHORT}")
    from phase2_project_engine.ops.effects import apply_effect
    tree = make_minimal_tree()
    src = _import_source(tree, CLIP_SHORT)
    kid = _insert_clip(tree, CLIP_SHORT, src)
    with pytest.raises(ValidationError) as ei:
        apply_effect(
            tree, clip_id=kid, effect_id="brightness",
            params={"totally_made_up": 0.5}, catalog=BRIGHTNESS_CATALOG,
        )
    assert "fix:" in str(ei.value)
