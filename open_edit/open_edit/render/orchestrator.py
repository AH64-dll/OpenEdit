"""Render orchestrator: melt subprocess + cache + QC dispatch.

The main entry point: render_project(project_id, ...) -> RenderResult.
Handles:
- Building the Timeline from the edit graph
- Computing the canonical-JSON hash for cache lookup
- Resolving asset paths via the AssetStore and passing them to the emitter
- Emitting MLT XML
- Calling melt via subprocess (with optional cache hit/force flag)
- Recording a `RenderSnapshot` in `RenderSnapshotStore` (Phase 4 T4) so the
  preview UI can show a version list and switch between renders.
- Returning a structured RenderResult
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from open_edit.ir.apply import derive_or_load_timeline, derive_timeline
from open_edit.ir.types import AddClipOp, Project
from open_edit.render.cache import RenderCache, canonical_json_hash
from open_edit.render.emitter import EmitterConfig, emit_timeline
from open_edit.render.profiles import RenderProfile, select_profile, profile_to_mlt_args
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.storage.render_snapshots import (
    RenderSnapshot, RenderSnapshotStore, RenderStatus,
)


class RenderResult(BaseModel):
    """Outcome of a render operation."""
    ok: bool
    output_path: str = ""
    mode: str = "proxy"
    profile: dict = Field(default_factory=dict)
    duration_sec: float = 0.0
    elapsed_sec: float = 0.0
    cache_hit: bool = False
    edit_graph_hash: str = ""
    error: Optional[str] = None


def render_project(
    project_id: str,
    project_dir: Path,
    workdir: Path,
    mode: Literal["proxy", "final"] = "proxy",
    profile_name: Optional[str] = None,
    force: bool = False,
    nice_level: int = 10,
) -> RenderResult:
    """Render a project to an MP4.

    project_dir: directory containing `.open_edit/edit_graph.db`
    workdir: directory for the rendered MP4 (and the cache)

    If profile_name is None, a profile is auto-selected from mode:
    proxy -> 720p30, final -> 1080p30.
    """
    melt_bin = shutil.which("melt")
    if melt_bin is None:
        return RenderResult(ok=False, error="melt not on PATH")

    if profile_name is None or profile_name == "":
        profile_name = "1080p30" if mode == "final" else "720p30"
    profile = select_profile(profile_name)

    project_path = project_dir / ".open_edit" / "edit_graph.db"
    store = EditGraphStore(project_path)
    ops = store.load_all()
    applied_ops = [op for op in ops if op.status == "applied"]
    if not applied_ops:
        return RenderResult(ok=False, error="empty edit graph; nothing to render")

    project = Project(name=project_id)
    project.edit_graph = list(applied_ops)
    timeline = derive_or_load_timeline(project, store)

    asset_paths: dict[str, str] = {}
    asset_store = AssetStore(project_dir / ".open_edit" / "assets")
    for op in applied_ops:
        if isinstance(op, AddClipOp):
            path = asset_store.path(op.asset_hash)
            if path is not None:
                asset_paths[op.asset_hash] = str(path)

    payload = [op.model_dump(mode="json") for op in applied_ops]
    graph_hash = canonical_json_hash(payload)

    cache = RenderCache(workdir / "render_cache")
    if not force:
        cached = cache.get(graph_hash)
        if cached and cache.is_fresh(cached):
            return RenderResult(
                ok=True, output_path=str(cached), mode=mode,
                profile=profile.model_dump(), duration_sec=timeline.duration_sec,
                elapsed_sec=0.0, cache_hit=True, edit_graph_hash=graph_hash,
            )

    config = EmitterConfig(profile=profile.model_dump())
    xml = emit_timeline(timeline, config, asset_paths=asset_paths)

    workdir.mkdir(parents=True, exist_ok=True)
    xml_path = workdir / f"project_{graph_hash[:12]}.mlt"
    xml_path.write_text(xml)

    output_mp4 = workdir / f"project_{graph_hash[:12]}.mp4"
    cmd = _build_melt_command(melt_bin, xml_path, output_mp4, profile, nice_level)

    t0 = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        # Per T5 carry-over #2: record a `failed` snapshot on timeout so
        # the version list shows the attempt rather than disappearing.
        _record_snapshot_failure(project_dir, project_id, graph_hash, output_mp4)
        return RenderResult(
            ok=False, output_path=str(output_mp4), mode=mode,
            profile=profile.model_dump(), duration_sec=timeline.duration_sec,
            elapsed_sec=600.0, edit_graph_hash=graph_hash,
            error="melt timed out after 600s",
        )
    elapsed = time.monotonic() - t0

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        _record_snapshot_failure(project_dir, project_id, graph_hash, output_mp4)
        return RenderResult(
            ok=False, output_path=str(output_mp4), mode=mode,
            profile=profile.model_dump(), duration_sec=timeline.duration_sec,
            elapsed_sec=elapsed, edit_graph_hash=graph_hash,
            error=err[-1] if err else f"melt exited {proc.returncode}",
        )

    cache.put(graph_hash, output_mp4)
    _record_snapshot_success(project_dir, project_id, graph_hash, output_mp4)

    return RenderResult(
        ok=True, output_path=str(output_mp4), mode=mode,
        profile=profile.model_dump(), duration_sec=timeline.duration_sec,
        elapsed_sec=elapsed, cache_hit=False, edit_graph_hash=graph_hash,
    )


def _build_melt_command(
    melt_bin: str, xml_path: Path, output_mp4: Path,
    profile: RenderProfile, nice_level: int,
) -> list[str]:
    """Build the melt command line."""
    args = [melt_bin, str(xml_path), "-consumer", f"avformat:{output_mp4}"]
    args += profile_to_mlt_args(profile)
    if nice_level > 0:
        return ["nice", "-n", str(nice_level)] + args
    return args


def _snapshots_path(project_dir: Path) -> Path:
    """Resolve the SQLite path for a project's render snapshots.

    Mirrors the chat-UI helper: anchor next to the project file when the
    project_dir is a real directory.
    """
    return project_dir / ".open_edit" / "render_snapshots.db"


def _record_snapshot_success(
    project_dir: Path, project_id: str, graph_hash: str, mp4_path: Path,
) -> None:
    """Append a `ready` snapshot to the RenderSnapshotStore and evict
    the oldest ready entry if the cap is exceeded (per audit M1)."""
    store = RenderSnapshotStore(_snapshots_path(project_dir))
    existing = store.list_for_project(project_id)
    label = f"v{len(existing) + 1}"
    snap = RenderSnapshot(
        project_id=project_id,
        edit_graph_hash=graph_hash,
        render_path=mp4_path,
        status=RenderStatus.ready,
        label=label,
    )
    store.append(snap)
    store.evict_oldest_ready(max_versions=20)


def _record_snapshot_failure(
    project_dir: Path, project_id: str, graph_hash: str, mp4_path: Path,
) -> None:
    """Append a `failed` snapshot so the user can see the attempt failed
    in the version list. Per audit M1, `failed` is never evicted."""
    store = RenderSnapshotStore(_snapshots_path(project_dir))
    existing = store.list_for_project(project_id)
    label = f"v{len(existing) + 1}"
    snap = RenderSnapshot(
        project_id=project_id,
        edit_graph_hash=graph_hash,
        render_path=mp4_path,
        status=RenderStatus.failed,
        label=label,
    )
    store.append(snap)
