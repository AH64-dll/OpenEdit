"""Phase 4 Task 5: RenderSnapshotStore + max-versions cap + status states."""
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from open_edit.storage.render_snapshots import (
    RenderSnapshot, RenderSnapshotStore, RenderStatus,
)


def _make_snapshot(project_id: str = "p1", status: RenderStatus = RenderStatus.ready, age_days: int = 0) -> RenderSnapshot:
    return RenderSnapshot(
        version_id=f"v_{project_id}_{age_days}",
        project_id=project_id,
        edit_graph_hash="abc123",
        render_path=Path(f"/tmp/render_{age_days}.mp4"),
        created_at=(datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat(),
        status=status,
        label=f"v{age_days}",
    )


class TestRenderSnapshotStore(unittest.TestCase):
    """Unit tests for RenderSnapshotStore."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_append_and_list(self) -> None:
        store = RenderSnapshotStore(self.tmp_path / "snapshots.db")
        snap = _make_snapshot()
        store.append(snap)
        snaps = store.list_for_project("p1")
        self.assertEqual(len(snaps), 1)
        self.assertEqual(snaps[0].version_id, snap.version_id)

    def test_latest_ready(self) -> None:
        store = RenderSnapshotStore(self.tmp_path / "snapshots.db")
        store.append(_make_snapshot(status=RenderStatus.rendering, age_days=2))
        store.append(_make_snapshot(status=RenderStatus.ready, age_days=1))
        latest = store.latest_ready("p1")
        self.assertIsNotNone(latest)
        self.assertEqual(latest.label, "v1")

    def test_evict_oldest_ready(self) -> None:
        store = RenderSnapshotStore(self.tmp_path / "snapshots.db")
        store.append(_make_snapshot(status=RenderStatus.rendering, age_days=100))
        for i in range(25):
            store.append(_make_snapshot(age_days=i))
        store.evict_oldest_ready(max_versions=20)
        snaps = store.list_for_project("p1")
        self.assertEqual(len(snaps), 21)
        rendering = [s for s in snaps if s.status == RenderStatus.rendering]
        self.assertEqual(len(rendering), 1)
        ready = [s for s in snaps if s.status == RenderStatus.ready]
        self.assertEqual(len(ready), 20)

    def test_status_transitions(self) -> None:
        store = RenderSnapshotStore(self.tmp_path / "snapshots.db")
        snap = _make_snapshot(status=RenderStatus.rendering)
        store.append(snap)
        store.update_status(snap.version_id, RenderStatus.ready)
        latest = store.latest_ready("p1")
        self.assertIsNotNone(latest)
        self.assertEqual(latest.status, RenderStatus.ready)

    def test_failed_not_evicted(self) -> None:
        store = RenderSnapshotStore(self.tmp_path / "snapshots.db")
        for i in range(25):
            store.append(_make_snapshot(age_days=i, status=RenderStatus.failed))
        store.evict_oldest_ready(max_versions=5)
        snaps = store.list_for_project("p1")
        self.assertEqual(len(snaps), 25)

    def test_latest_for_project_returns_newest_any_status(self) -> None:
        store = RenderSnapshotStore(self.tmp_path / "snapshots.db")
        store.append(_make_snapshot(status=RenderStatus.ready, age_days=2))
        store.append(_make_snapshot(status=RenderStatus.failed, age_days=0))
        latest = store.latest_for_project("p1")
        self.assertIsNotNone(latest)
        self.assertEqual(latest.status, RenderStatus.failed)
        ready = store.latest_ready("p1")
        self.assertIsNotNone(ready)
        self.assertEqual(ready.status, RenderStatus.ready)

    def test_latest_for_project_empty_returns_none(self) -> None:
        store = RenderSnapshotStore(self.tmp_path / "snapshots.db")
        self.assertIsNone(store.latest_for_project("p1"))


if __name__ == "__main__":
    unittest.main()
