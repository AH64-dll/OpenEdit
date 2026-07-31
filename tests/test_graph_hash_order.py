"""Regression tests for the edit-graph hash order-sensitivity bug (H1).

Before Task 6.5, ``compute_edit_graph_hash`` was order-insensitive in
practice: ``load_all()`` never populated ``sequence_num``, so the sort
key degenerated to ``(0, edit_id)`` and a reordered graph produced the
same digest. ``derive_or_load_timeline`` then returned the STALE cached
snapshot for the reordered graph.
"""
from __future__ import annotations

import pytest

from open_edit.ir.derive import derive_timeline
from open_edit.ir.hash import compute_edit_graph_hash
from open_edit.ir.types import AddClipOp, Project
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.storage.timeline_cache import derive_or_load_timeline


def _make_store(tmp_path) -> tuple[EditGraphStore, AddClipOp, AddClipOp]:
    store = EditGraphStore(tmp_path / "edit_graph.db")
    _ = store.project_id  # ensure project_id row exists before any snapshot
    a = AddClipOp(
        author="user", asset_hash="aaa", track_id="v1", position_sec=0.0,
        clip_id="c1",
    )
    b = AddClipOp(
        author="user", asset_hash="bbb", track_id="v1", position_sec=2.0,
        clip_id="c2",
    )
    store.append(a)
    store.append(b)
    return store, a, b


def test_hash_changes_when_order_changes(tmp_path) -> None:
    """Reordering ops via the store's reorder API changes the hash."""
    store, a, b = _make_store(tmp_path)

    h_before = compute_edit_graph_hash(store.load_all())

    store.reorder_all([b.edit_id, a.edit_id])

    h_after = compute_edit_graph_hash(store.load_all())
    assert h_after != h_before


def test_adjacent_reorder_changes_hash(tmp_path) -> None:
    """The adjacent-swap reorder API must also invalidate the hash."""
    store, a, b = _make_store(tmp_path)

    h_before = compute_edit_graph_hash(store.load_all())

    store.reorder(a.edit_id, b.edit_id)

    h_after = compute_edit_graph_hash(store.load_all())
    assert h_after != h_before


def test_delete_op_changes_hash(tmp_path) -> None:
    store, a, b = _make_store(tmp_path)

    h_before = compute_edit_graph_hash(store.load_all())

    store.delete_op(a.edit_id)

    h_after = compute_edit_graph_hash(store.load_all())
    assert h_after != h_before


def test_derive_or_load_timeline_reflects_reorder_not_stale_snapshot(tmp_path) -> None:
    """After a reorder, snapshot cache must not serve the stale timeline."""
    store, a, b = _make_store(tmp_path)
    project = Project(name="t", project_id=store.project_id)
    project.edit_graph = store.load_all()

    tl_before = derive_or_load_timeline(project, store)
    assert store.load_timeline_snapshot(compute_edit_graph_hash(project.edit_graph)) is not None

    store.reorder_all([b.edit_id, a.edit_id])
    project.edit_graph = store.load_all()

    h_after = compute_edit_graph_hash(project.edit_graph)
    # The reordered graph's hash is new: no stale snapshot may exist for it.
    assert store.load_timeline_snapshot(h_after) is None

    tl_after = derive_or_load_timeline(project, store)
    # The reordered timeline (clips in swapped order), not the stale one.
    assert tl_after.model_dump() != tl_before.model_dump()
    assert tl_after.model_dump() == derive_timeline(project).model_dump()


def test_hash_equal_for_same_graph_loaded_twice(tmp_path) -> None:
    """The digest is stable across load_all() calls for the same graph."""
    store, _a, _b = _make_store(tmp_path)
    assert compute_edit_graph_hash(store.load_all()) == compute_edit_graph_hash(store.load_all())


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
