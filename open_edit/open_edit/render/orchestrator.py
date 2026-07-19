"""Render orchestrator: melt subprocess + cache + QC dispatch.

The main entry point: render_project(project_id, ...) -> RenderResult.
Handles:
- Building the Timeline from the edit graph
- Computing the canonical-JSON hash for cache lookup
- Resolving asset paths via the AssetStore and passing them to the emitter
- Emitting MLT XML
- Calling melt via subprocess (with optional cache hit/force flag)
- Returning a structured RenderResult
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from open_edit.ir.apply import derive_timeline
from open_edit.ir.types import AddClipOp, Project
from open_edit.render.cache import RenderCache, canonical_json_hash
from open_edit.render.emitter import EmitterConfig, emit_timeline
from open_edit.render.profiles import RenderProfile, select_profile, profile_to_mlt_args
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore


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
    mode: str = "proxy",
    profile_name: str = "720p30",
    force: bool = False,
    nice_level: int = 10,
) -> RenderResult:
    """Render a project to an MP4.

    project_dir: directory containing `.open_edit/edit_graph.db`
    workdir: directory for the rendered MP4 (and the cache)
    """
    if mode not in ("proxy", "final"):
        return RenderResult(ok=False, error=f"invalid mode: {mode}")

    melt_bin = shutil.which("melt")
    if melt_bin is None:
        return RenderResult(ok=False, error="melt not on PATH")

    profile = select_profile(profile_name)

    project_path = project_dir / ".open_edit" / "edit_graph.db"
    store = EditGraphStore(project_path)
    ops = store.load_all()
    if not ops:
        return RenderResult(ok=False, error="empty edit graph; nothing to render")

    project = Project(name=project_id)
    project.edit_graph = list(ops)
    timeline = derive_timeline(project)

    asset_paths: dict[str, str] = {}
    asset_store = AssetStore(project_dir / ".open_edit" / "assets")
    for op in ops:
        if isinstance(op, AddClipOp):
            path = asset_store.path(op.asset_hash)
            if path is not None:
                asset_paths[op.asset_hash] = str(path)

    payload = [op.model_dump(mode="json") for op in ops]
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
        return RenderResult(
            ok=False, output_path=str(output_mp4), mode=mode,
            profile=profile.model_dump(), duration_sec=timeline.duration_sec,
            elapsed_sec=600.0, edit_graph_hash=graph_hash,
            error="melt timed out after 600s",
        )
    elapsed = time.monotonic() - t0

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        return RenderResult(
            ok=False, output_path=str(output_mp4), mode=mode,
            profile=profile.model_dump(), duration_sec=timeline.duration_sec,
            elapsed_sec=elapsed, edit_graph_hash=graph_hash,
            error=err[-1] if err else f"melt exited {proc.returncode}",
        )

    cache.put(graph_hash, output_mp4)

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
