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

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from open_edit.ir.apply import derive_or_load_timeline, derive_timeline
from open_edit.ir.types import AddClipOp, Project, Timeline
from open_edit.render.cache import RenderCache, canonical_json_hash
from open_edit.render.emitter import EmitterConfig, emit_timeline
from open_edit.render.graphics_overlay import (
    GraphicsOverlayError,
    OverlayClip,
    burn_overlays,
)
from open_edit.render.materialize import RemotionMaterializeError, materialize_remotion_compositions
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
        return RenderResult(
            ok=False, mode=mode, profile=profile.model_dump(),
            duration_sec=timeline.duration_sec, error=str(exc),
        )

    asset_paths: dict[str, str] = {}
    asset_store = AssetStore(project_dir / ".open_edit" / "assets")
    for op in applied_ops:
        if isinstance(op, AddClipOp):
            path = asset_store.path(op.asset_hash)
            if path is not None:
                asset_paths[op.asset_hash] = str(path)
    for composition in timeline.remotion_compositions:
        if composition.asset_hash:
            path = asset_store.path(composition.asset_hash)
            if path is not None:
                asset_paths[composition.asset_hash] = str(path)
    for track in timeline.tracks:
        for clip in track.clips:
            if clip.asset_hash and clip.asset_hash not in asset_paths:
                path = asset_store.path(clip.asset_hash)
                if path is not None:
                    asset_paths[clip.asset_hash] = str(path)

    remotion_overlays = _remotion_overlay_clips(timeline, asset_paths)
    video_overlays = _video_track_overlay_clips(timeline, asset_paths)
    burn_list = sorted(remotion_overlays + video_overlays, key=lambda o: o.position_sec)
    # Melt only the base talk track — Remotion + upper video tracks burn via ffmpeg.
    melt_timeline = _timeline_for_melt(timeline)

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
    xml = emit_timeline(melt_timeline, config, asset_paths=asset_paths)

    workdir.mkdir(parents=True, exist_ok=True)
    xml_path = workdir / f"project_{graph_hash[:12]}.mlt"
    xml_path.write_text(xml)

    melt_mp4 = workdir / f"project_{graph_hash[:12]}.melt.mp4"
    output_mp4 = workdir / f"project_{graph_hash[:12]}.mp4"
    cmd = _build_melt_command(
        melt_bin, xml_path, melt_mp4, profile, nice_level, encoder_backend,
        mode=mode,
    )

    # Final ~30min + Remotion can exceed 10 minutes wall time easily.
    melt_timeout = 7200 if mode == "final" else 600
    t0 = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=melt_timeout)
    except subprocess.TimeoutExpired:
        # Per T5 carry-over #2: record a `failed` snapshot on timeout so
        # the version list shows the attempt rather than disappearing.
        _record_snapshot_failure(project_dir, project_id, graph_hash, output_mp4)
        return RenderResult(
            ok=False, output_path=str(output_mp4), mode=mode,
            profile=profile.model_dump(), duration_sec=timeline.duration_sec,
            elapsed_sec=float(melt_timeout), edit_graph_hash=graph_hash,
            error=f"melt timed out after {melt_timeout}s",
        )
    elapsed = time.monotonic() - t0

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        _record_snapshot_failure(project_dir, project_id, graph_hash, output_mp4)
        return RenderResult(
            ok=False, output_path=str(melt_mp4), mode=mode,
            profile=profile.model_dump(), duration_sec=timeline.duration_sec,
            elapsed_sec=elapsed, edit_graph_hash=graph_hash,
            error=err[-1] if err else f"melt exited {proc.returncode}",
        )

    if burn_list:
        burn_timeout = max(1800.0, timeline.duration_sec * 4.0) if mode == "final" else 900.0
        try:
            burn_overlays(
                melt_mp4,
                burn_list,
                output_mp4,
                width=profile.width,
                height=profile.height,
                encoder_backend=encoder_backend,
                timeout_s=burn_timeout,
                final=(mode == "final"),
            )
        except GraphicsOverlayError as exc:
            _record_snapshot_failure(project_dir, project_id, graph_hash, output_mp4)
            return RenderResult(
                ok=False, output_path=str(output_mp4), mode=mode,
                profile=profile.model_dump(), duration_sec=timeline.duration_sec,
                elapsed_sec=time.monotonic() - t0, edit_graph_hash=graph_hash,
                error=str(exc),
            )
    else:
        # No Remotion overlays — melt output is final.
        melt_mp4.replace(output_mp4)

    cache.put(graph_hash, output_mp4)
    _record_snapshot_success(project_dir, project_id, graph_hash, output_mp4)

    return RenderResult(
        ok=True, output_path=str(output_mp4), mode=mode,
        profile=profile.model_dump(), duration_sec=timeline.duration_sec,
        elapsed_sec=time.monotonic() - t0, cache_hit=False, edit_graph_hash=graph_hash,
    )


def _remotion_overlay_clips(
    timeline: Timeline, asset_paths: dict[str, str],
) -> list[OverlayClip]:
    overlays: list[OverlayClip] = []
    for composition in timeline.remotion_compositions:
        if not composition.asset_hash:
            continue
        path = asset_paths.get(composition.asset_hash)
        if not path:
            continue
        overlays.append(OverlayClip(
            position_sec=composition.position_sec,
            duration_sec=composition.duration_sec,
            media_path=Path(path),
            label=composition.composition_id,
            blur_under=bool((composition.props or {}).get("blur_under", False)),
        ))
    overlays.sort(key=lambda o: o.position_sec)
    return overlays


def _video_track_overlay_clips(
    timeline: Timeline, asset_paths: dict[str, str],
) -> list[OverlayClip]:
    """Fullscreen clips on video tracks above v1 (e.g. screen recordings on v2).

    Skips Remotion-injected clips on ``video_graphics`` — those are burned via
    ``_remotion_overlay_clips`` with correct alpha/blur metadata. Burning them
    again as opaque overlays corrupts ffmpeg output mid-timeline.
    """
    video_tracks = [t for t in timeline.tracks if t.kind == "video"]
    if len(video_tracks) <= 1:
        return []
    remotion_clip_ids = {c.clip_id for c in timeline.remotion_compositions}
    overlays: list[OverlayClip] = []
    for track in video_tracks[1:]:
        if track.track_id == "video_graphics":
            continue
        for clip in track.clips:
            if clip.clip_id in remotion_clip_ids:
                continue
            path = asset_paths.get(clip.asset_hash)
            if not path:
                continue
            dur = clip.out_point_sec - clip.in_point_sec
            overlays.append(OverlayClip(
                position_sec=clip.position_sec,
                duration_sec=dur,
                media_path=Path(path),
                label=track.track_id,
                alpha=False,
            ))
    return overlays


def _timeline_for_melt(timeline: Timeline) -> Timeline:
    """Return a copy of ``timeline`` for melt: base v1 only, no Remotion/overlay tracks.

    Remotion and upper video tracks (v2+) are burned via ffmpeg overlays; melt
    only renders the primary talk track. Multitrack melt composite is unreliable
    on Windows and can blank the base layer.
    """
    updated = timeline.model_copy(deep=True)
    remotion_ids = {c.clip_id for c in updated.remotion_compositions}
    if remotion_ids:
        for track in updated.tracks:
            track.clips = [c for c in track.clips if c.clip_id not in remotion_ids]
    video_tracks = [t for t in updated.tracks if t.kind == "video"]
    if len(video_tracks) > 1:
        base_id = video_tracks[0].track_id
        updated.tracks = [
            t for t in updated.tracks
            if t.kind != "video" or t.track_id == base_id
        ]
    updated.tracks = [t for t in updated.tracks if t.clips]
    return updated


def _timeline_without_remotion_clips(timeline: Timeline) -> Timeline:
    """Deprecated alias — use ``_timeline_for_melt``."""
    return _timeline_for_melt(timeline)


def _build_melt_command(
    melt_bin: str, xml_path: Path, output_mp4: Path,
    profile: RenderProfile, nice_level: int,
    encoder_backend: Optional[str] = None,
    mode: str = "proxy",
) -> list[str]:
    """Build the melt command line."""
    args = [melt_bin, str(xml_path), "-consumer", f"avformat:{output_mp4}"]
    args += profile_to_mlt_args(profile, backend=encoder_backend, mode=mode)
    if nice_level > 0 and os.name == "posix":
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
