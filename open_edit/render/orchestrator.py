"""Render orchestrator: plan → cache → emit → melt → burn → snapshot → result.

The main entry point: render_project(project_id, ...) -> RenderResult.
Composes the split render modules:

- ``timeline_plan.build_render_plan`` — asset paths, overlay clips, melt timeline
- ``melt_runner.MeltRunner`` — cache mediation + melt subprocess with timeout
- ``snapshot_recorder.record_snapshot`` — RenderSnapshotStore recording

Failure paths funnel through a single ``_fail`` helper producing the
structured RenderResult.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from open_edit.storage.timeline_cache import derive_or_load_timeline
from open_edit.ir.types import Project
from open_edit.render.cache import RenderCache, canonical_json_hash
from open_edit.render.emitter import EmitterConfig, emit_timeline
from open_edit.render.graphics_overlay import GraphicsOverlayError, burn_overlays
from open_edit.render.materialize import RemotionMaterializeError, materialize_remotion_compositions
from open_edit.render.melt_runner import MeltRunner, MeltTimeoutError
from open_edit.render.profiles import RenderProfile, select_profile
from open_edit.render.snapshot_recorder import record_snapshot
from open_edit.render.timeline_plan import build_render_plan
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
    mode: Literal["proxy", "final"] = "proxy",
    profile_name: Optional[str] = None,
    force: bool = False,
    nice_level: int = 10,
    encoder_backend: Optional[str] = None,
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
    timeline = derive_or_load_timeline(project, store, strict=True)

    # Materialize Remotion compositions to CAS clips before emit. Fail hard.
    try:
        timeline = materialize_remotion_compositions(
            timeline, project_dir, mode=mode,
        )
    except RemotionMaterializeError as exc:
        return _fail(
            mode=mode, profile=profile, output_path="",
            duration_sec=timeline.duration_sec, elapsed_sec=0.0,
            graph_hash="", error=str(exc),
        )

    plan = build_render_plan(
        timeline,
        applied_ops,
        AssetStore(project_dir / ".open_edit" / "assets"),
        mode,
    )

    payload = [op.model_dump(mode="json") for op in applied_ops]
    graph_hash = canonical_json_hash(payload)

    runner = MeltRunner(
        melt_bin,
        cache=RenderCache(workdir / "render_cache"),
        nice_level=nice_level,
        encoder_backend=encoder_backend,
    )
    if not force:
        cached = runner.cached(graph_hash)
        if cached and runner.is_fresh(cached):
            return RenderResult(
                ok=True, output_path=str(cached), mode=mode,
                profile=profile.model_dump(), duration_sec=timeline.duration_sec,
                elapsed_sec=0.0, cache_hit=True, edit_graph_hash=graph_hash,
            )

    config = EmitterConfig(profile=profile.model_dump())
    xml = emit_timeline(plan.melt_timeline, config, asset_paths=plan.asset_paths)

    workdir.mkdir(parents=True, exist_ok=True)
    xml_path = workdir / f"project_{graph_hash[:12]}.mlt"
    xml_path.write_text(xml)

    melt_mp4 = workdir / f"project_{graph_hash[:12]}.melt.mp4"
    output_mp4 = workdir / f"project_{graph_hash[:12]}.mp4"

    # Final ~30min + Remotion can exceed 10 minutes wall time easily.
    melt_timeout = 7200 if mode == "final" else 600
    t0 = time.monotonic()
    try:
        proc = runner.run(
            xml_path, melt_mp4, profile, mode=mode, timeout_s=melt_timeout,
        )
    except MeltTimeoutError as exc:
        # Per T5 carry-over #2: record a `failed` snapshot on timeout so
        # the version list shows the attempt rather than disappearing.
        return _fail(
            mode=mode, profile=profile, output_path=str(output_mp4),
            duration_sec=timeline.duration_sec, elapsed_sec=float(melt_timeout),
            graph_hash=graph_hash, error=str(exc),
            project_dir=project_dir, project_id=project_id, record_failed_snapshot=True,
        )
    elapsed = time.monotonic() - t0

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        return _fail(
            mode=mode, profile=profile, output_path=str(melt_mp4),
            duration_sec=timeline.duration_sec, elapsed_sec=elapsed,
            graph_hash=graph_hash,
            error=err[-1] if err else f"melt exited {proc.returncode}",
            project_dir=project_dir, project_id=project_id, record_failed_snapshot=True,
        )

    if plan.overlay_clips:
        burn_timeout = max(1800.0, timeline.duration_sec * 4.0) if mode == "final" else 900.0
        try:
            burn_overlays(
                melt_mp4,
                plan.overlay_clips,
                output_mp4,
                width=profile.width,
                height=profile.height,
                encoder_backend=encoder_backend,
                timeout_s=burn_timeout,
                final=(mode == "final"),
            )
        except GraphicsOverlayError as exc:
            return _fail(
                mode=mode, profile=profile, output_path=str(output_mp4),
                duration_sec=timeline.duration_sec,
                elapsed_sec=time.monotonic() - t0,
                graph_hash=graph_hash, error=str(exc),
                project_dir=project_dir, project_id=project_id, record_failed_snapshot=True,
            )
    else:
        # No Remotion overlays — melt output is final.
        melt_mp4.replace(output_mp4)

    runner.cache_put(graph_hash, output_mp4)
    record_snapshot(project_dir, project_id, graph_hash, output_mp4, success=True)

    return RenderResult(
        ok=True, output_path=str(output_mp4), mode=mode,
        profile=profile.model_dump(), duration_sec=timeline.duration_sec,
        elapsed_sec=time.monotonic() - t0, cache_hit=False, edit_graph_hash=graph_hash,
    )


def _fail(
    *,
    mode: str,
    profile: RenderProfile,
    output_path: str,
    duration_sec: float,
    elapsed_sec: float,
    graph_hash: str,
    error: str,
    project_dir: Optional[Path] = None,
    project_id: Optional[str] = None,
    record_failed_snapshot: bool = False,
) -> RenderResult:
    """Single failure path: produce the failure RenderResult.

    When ``record_failed_snapshot`` is set, a `failed` snapshot is appended
    first so the version list surfaces the attempt (per audit M1 + T5
    carry-over #2).
    """
    if record_failed_snapshot:
        record_snapshot(
            project_dir, project_id, graph_hash, Path(output_path), success=False,
        )
    return RenderResult(
        ok=False, output_path=output_path, mode=mode,
        profile=profile.model_dump(), duration_sec=duration_sec,
        elapsed_sec=elapsed_sec, edit_graph_hash=graph_hash, error=error,
    )
