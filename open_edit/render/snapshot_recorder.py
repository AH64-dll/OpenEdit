"""Render snapshot recording into the RenderSnapshotStore (Phase 4 T4)."""
from __future__ import annotations

from pathlib import Path

from open_edit.storage.render_snapshots import (
    RenderSnapshot, RenderSnapshotStore, RenderStatus,
)


def _snapshots_path(project_dir: Path) -> Path:
    """Resolve the SQLite path for a project's render snapshots.

    Mirrors the chat-UI helper: anchor next to the project file when the
    project_dir is a real directory.
    """
    return project_dir / ".open_edit" / "render_snapshots.db"


def record_snapshot(
    project_dir: Path,
    project_id: str,
    graph_hash: str,
    mp4_path: Path,
    success: bool,
) -> None:
    """Append a snapshot to the RenderSnapshotStore.

    ``success=True`` records a `ready` snapshot and evicts the oldest ready
    entry if the cap is exceeded (per audit M1). ``success=False`` records a
    `failed` snapshot so the user can see the attempt failed in the version
    list; `failed` is never evicted (per audit M1).
    """
    store = RenderSnapshotStore(_snapshots_path(project_dir))
    existing = store.list_for_project(project_id)
    label = f"v{len(existing) + 1}"
    snap = RenderSnapshot(
        project_id=project_id,
        edit_graph_hash=graph_hash,
        render_path=mp4_path,
        status=RenderStatus.ready if success else RenderStatus.failed,
        label=label,
    )
    store.append(snap)
    if success:
        store.evict_oldest_ready(max_versions=20)
