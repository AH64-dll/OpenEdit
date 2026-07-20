"""Phase 4 Task 5: RenderSnapshotStore + max-versions cap + status states."""
import json
import pytest
from pathlib import Path
from datetime import datetime, timezone, timedelta

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


def test_append_and_list(tmp_path):
    store = RenderSnapshotStore(tmp_path / "snapshots.db")
    snap = _make_snapshot()
    store.append(snap)
    snaps = store.list_for_project("p1")
    assert len(snaps) == 1
    assert snaps[0].version_id == snap.version_id


def test_latest_ready(tmp_path):
    store = RenderSnapshotStore(tmp_path / "snapshots.db")
    store.append(_make_snapshot(status=RenderStatus.rendering, age_days=2))
    store.append(_make_snapshot(status=RenderStatus.ready, age_days=1))
    latest = store.latest_ready("p1")
    assert latest.label == "v1"


def test_evict_oldest_ready(tmp_path):
    """Per audit M1: max-versions cap; evict oldest status=ready; never evict rendering/failed."""
    store = RenderSnapshotStore(tmp_path / "snapshots.db")
    store.append(_make_snapshot(status=RenderStatus.rendering, age_days=100))
    for i in range(25):
        store.append(_make_snapshot(age_days=i))
    store.evict_oldest_ready(max_versions=20)
    snaps = store.list_for_project("p1")
    # 25 + 1 rendering = 26; evict 5 oldest ready; keep 20 ready + 1 rendering
    assert len(snaps) == 21
    rendering = [s for s in snaps if s.status == RenderStatus.rendering]
    assert len(rendering) == 1
    ready = [s for s in snaps if s.status == RenderStatus.ready]
    assert len(ready) == 20


def test_status_transitions(tmp_path):
    store = RenderSnapshotStore(tmp_path / "snapshots.db")
    snap = _make_snapshot(status=RenderStatus.rendering)
    store.append(snap)
    store.update_status(snap.version_id, RenderStatus.ready)
    latest = store.latest_ready("p1")
    assert latest is not None
    assert latest.status == RenderStatus.ready


def test_failed_not_evicted(tmp_path):
    store = RenderSnapshotStore(tmp_path / "snapshots.db")
    for i in range(25):
        store.append(_make_snapshot(age_days=i, status=RenderStatus.failed))
    store.evict_oldest_ready(max_versions=5)
    snaps = store.list_for_project("p1")
    # All 25 failed; evict only if status==ready
    assert len(snaps) == 25


def test_latest_for_project_returns_newest_any_status(tmp_path):
    """Per fix M3: latest_for_project returns the most recent snapshot
    regardless of status (unlike `latest_ready` which filters by ready).
    The chat UI's commit_feedback handler uses this to broadcast
    `version_ready` for any new snapshot, including failed renders."""
    store = RenderSnapshotStore(tmp_path / "snapshots.db")
    # Older ready + newer failed: latest_for_project returns the failed one.
    store.append(_make_snapshot(status=RenderStatus.ready, age_days=2))
    store.append(_make_snapshot(status=RenderStatus.failed, age_days=0))
    latest = store.latest_for_project("p1")
    assert latest is not None
    assert latest.status == RenderStatus.failed
    # latest_ready still returns the ready one.
    ready = store.latest_ready("p1")
    assert ready is not None
    assert ready.status == RenderStatus.ready


def test_latest_for_project_empty_returns_none(tmp_path):
    store = RenderSnapshotStore(tmp_path / "snapshots.db")
    assert store.latest_for_project("p1") is None
