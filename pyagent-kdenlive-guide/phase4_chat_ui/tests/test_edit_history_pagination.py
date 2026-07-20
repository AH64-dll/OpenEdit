"""Phase 4 Task 5: edit history list pagination (audit M8).

`EditGraphStore.load_all` returns the full history. For UIs that want to
show the last N or page through 200+ ops, callers slice the returned list.
This test pins down the contract: load_all is stable, ordered, and slices
predictably so the UI can paginate.
"""
import pytest
from pathlib import Path

from open_edit.storage.edit_graph import EditGraphStore
from open_edit.ir.types import AddClipOp


def _make_ops(n: int) -> list[AddClipOp]:
    return [
        AddClipOp(author="user", asset_hash=f"a{i}", track_id="t1", position_sec=0.0)
        for i in range(n)
    ]


def test_pagination_50_ops_per_page(tmp_path):
    store = EditGraphStore(tmp_path / "edit_graph.db")
    for op in _make_ops(120):
        store.append(op)
    page1 = store.load_all()[0:50]
    page2 = store.load_all()[50:100]
    page3 = store.load_all()[100:120]
    assert len(page1) == 50
    assert len(page2) == 50
    assert len(page3) == 20


def test_history_ordering_preserved_across_pages(tmp_path):
    """Per audit M8: pagination must preserve append-order so the UI can
    show 'ops 51-100' without scrambling the timeline. `edit_id` is
    unique per op; pagination should keep the relative order across
    page boundaries (no re-shuffling)."""
    store = EditGraphStore(tmp_path / "edit_graph.db")
    appended_ids: list[str] = []
    for op in _make_ops(10):
        store.append(op)
        appended_ids.append(op.edit_id)
    all_ops = store.load_all()
    page1 = all_ops[0:5]
    page2 = all_ops[5:10]
    page1_ids = [op.edit_id for op in page1]
    page2_ids = [op.edit_id for op in page2]
    assert page1_ids == appended_ids[0:5]
    assert page2_ids == appended_ids[5:10]
