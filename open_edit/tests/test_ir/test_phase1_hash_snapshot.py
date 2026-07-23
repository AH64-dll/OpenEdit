"""Phase 1 tests: canonical edit-graph hashing and timeline snapshot caching."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from open_edit.ir.apply import derive_or_load_timeline, derive_timeline
from open_edit.ir.hash import compute_edit_graph_hash
from open_edit.ir.types import AddClipOp, Project
from open_edit.storage.edit_graph import EditGraphStore


def _op(asset_hash: str, position_sec: float = 0.0) -> AddClipOp:
    return AddClipOp(
        author="user",
        asset_hash=asset_hash,
        track_id="v1",
        position_sec=position_sec,
    )


class TestComputeEditGraphHash(unittest.TestCase):
    def test_order_independent(self) -> None:
        a = _op("aaa", 0.0)
        b = _op("bbb", 1.0)
        self.assertEqual(
            compute_edit_graph_hash([a, b]),
            compute_edit_graph_hash([b, a]),
        )

    def test_payload_change_changes_hash(self) -> None:
        a = _op("aaa", 0.0)
        h1 = compute_edit_graph_hash([a])
        a.position_sec = 5.0
        h2 = compute_edit_graph_hash([a])
        self.assertNotEqual(h1, h2)

    def test_status_change_changes_hash(self) -> None:
        a = _op("aaa", 0.0)
        h1 = compute_edit_graph_hash([a])
        a.status = "reverted"
        h2 = compute_edit_graph_hash([a])
        self.assertNotEqual(h1, h2)


class TestDeriveOrLoadTimeline(unittest.TestCase):
    def test_snapshot_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = EditGraphStore(Path(d) / "edit_graph.db")
            project = Project(name="t")
            op = _op("aaa", 0.0)
            store.append(op)
            project.edit_graph = store.load_all()

            h = compute_edit_graph_hash(project.edit_graph)
            self.assertIsNone(store.load_timeline_snapshot(h))

            tl1 = derive_or_load_timeline(project, store)
            self.assertIsNotNone(store.load_timeline_snapshot(h))

            tl2 = derive_or_load_timeline(project, store)
            self.assertEqual(tl1.model_dump(), tl2.model_dump())
            self.assertEqual(tl2.model_dump(), derive_timeline(project).model_dump())

    def test_mutation_triggers_fresh_derive(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = EditGraphStore(Path(d) / "edit_graph.db")
            project = Project(name="t")
            op = _op("aaa", 0.0)
            store.append(op)
            project.edit_graph = store.load_all()

            derive_or_load_timeline(project, store)

            mutated = _op("bbb", 3.0)
            store.append(mutated)
            project.edit_graph = store.load_all()

            new_hash = compute_edit_graph_hash(project.edit_graph)
            self.assertIsNone(store.load_timeline_snapshot(new_hash))

            tl = derive_or_load_timeline(project, store)
            self.assertEqual(tl.model_dump(), derive_timeline(project).model_dump())
            self.assertIsNotNone(store.load_timeline_snapshot(new_hash))

    def test_no_store_always_derives(self) -> None:
        project = Project(name="t")
        project.edit_graph = [_op("aaa", 0.0)]
        tl = derive_or_load_timeline(project, None)
        self.assertEqual(tl.model_dump(), derive_timeline(project).model_dump())


if __name__ == "__main__":
    unittest.main()
