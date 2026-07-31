"""Render plan building: asset resolution, overlay planning, melt timeline."""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from open_edit.ir.types import AddClipOp, Operation, Timeline
from open_edit.render.pipe_builder import OverlayClip
from open_edit.storage.assets import AssetStore


class RenderPlan(BaseModel):
    """Everything a render needs beyond the edit graph itself."""
    melt_timeline: Timeline
    overlay_clips: list[OverlayClip]
    asset_paths: dict[str, str]


def build_render_plan(
    timeline: Timeline,
    ops: list[Operation],
    store: AssetStore,
    mode: str,
) -> RenderPlan:
    """Build the render plan: resolved assets, ffmpeg overlay clips, melt timeline.

    ``mode`` is reserved for future plan-time decisions (proxy vs final); the
    current plan shape is mode-independent.
    """
    asset_paths = resolve_asset_paths(ops, timeline, store)
    remotion_overlays = _remotion_overlay_clips(timeline, asset_paths)
    video_overlays = _video_track_overlay_clips(timeline, asset_paths)
    overlay_clips = sorted(
        remotion_overlays + video_overlays, key=lambda o: o.position_sec,
    )
    return RenderPlan(
        melt_timeline=timeline_for_melt(timeline),
        overlay_clips=overlay_clips,
        asset_paths=asset_paths,
    )


def resolve_asset_paths(
    ops: list[Operation],
    timeline: Timeline,
    store: AssetStore,
) -> dict[str, str]:
    """Resolve asset hashes → filesystem paths.

    Collects hashes from applied ops, Remotion compositions, and timeline
    clips (deduplicated), then resolves each once via the AssetStore.
    """
    hashes: list[str] = []
    for op in ops:
        if isinstance(op, AddClipOp) and op.asset_hash not in hashes:
            hashes.append(op.asset_hash)
    for composition in timeline.remotion_compositions:
        if composition.asset_hash and composition.asset_hash not in hashes:
            hashes.append(composition.asset_hash)
    for track in timeline.tracks:
        for clip in track.clips:
            if clip.asset_hash and clip.asset_hash not in hashes:
                hashes.append(clip.asset_hash)
    asset_paths: dict[str, str] = {}
    for asset_hash in hashes:
        path = store.path(asset_hash)
        if path is not None:
            asset_paths[asset_hash] = str(path)
    return asset_paths


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


def timeline_for_melt(timeline: Timeline) -> Timeline:
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
