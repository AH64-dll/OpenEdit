"""Render plan building: asset resolution, overlay planning, melt timeline."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from open_edit.ir.types import AddClipOp, Operation, Timeline
from open_edit.render.pipe_builder import OverlayClip, OverlayInput
from open_edit.render.profiles import RenderProfile
from open_edit.render.remotion.frame_feeder import FrameOverlaySpec
from open_edit.render.remotion.renderer import remotion_profile_for_mode
from open_edit.render.source_proxy import DEFAULT_SOURCE_PROXY_PROFILE
from open_edit.storage.assets import AssetStore


EmissionProfile = Literal[
    "final", "review-artifact", "proxy-edit", "preview-chunk",
]
SourceMediaPolicy = Literal["original", "proxy"]

_EMISSION_POLICY: dict[str, SourceMediaPolicy] = {
    "final": "original",
    "review-artifact": "original",
    "proxy-edit": "proxy",
    "preview-chunk": "proxy",
}


def source_media_policy_for(
    emission_profile: EmissionProfile,
) -> SourceMediaPolicy:
    """Map an explicit emission profile to source or derived media."""
    try:
        return _EMISSION_POLICY[emission_profile]
    except KeyError as exc:
        raise ValueError(f"unknown emission profile: {emission_profile!r}") from exc


class RenderPlan(BaseModel):
    """Everything a render needs beyond the edit graph itself."""
    melt_timeline: Timeline
    overlay_clips: list[OverlayInput]
    asset_paths: dict[str, str]
    emission_profile: EmissionProfile
    source_media_policy: SourceMediaPolicy
    source_proxy_hits: dict[str, str] = Field(default_factory=dict)
    source_proxy_fallbacks: dict[str, str] = Field(default_factory=dict)
    frame_overlays: list[FrameOverlaySpec] = Field(default_factory=list)


def build_render_plan(
    timeline: Timeline,
    ops: list[Operation],
    store: AssetStore,
    mode: str,
    *,
    frame_engine: str = "materialize",
    frame_profile: RenderProfile | None = None,
    emission_profile: EmissionProfile | None = None,
    enqueue_missing_proxies: bool = True,
) -> RenderPlan:
    """Build a render plan with explicit source-media semantics.

    ``timeline`` is consumed exactly as supplied.  Preview callers may pass a
    frame-sliced, local-coordinate timeline; planning must not re-derive it or
    restore its original project offset.
    """
    requested_profile = emission_profile or _default_emission_profile(mode)
    source_media_policy = source_media_policy_for(requested_profile)
    if mode == "final" and source_media_policy != "original":
        raise ValueError(
            "final emission requires the original source-media policy"
        )

    asset_paths, source_proxy_hits, source_proxy_fallbacks = (
        _resolve_asset_paths_with_diagnostics(
            ops,
            timeline,
            store,
            source_media_policy=source_media_policy,
            enqueue_missing_proxies=enqueue_missing_proxies,
        )
    )
    remotion_overlays = (
        []
        if frame_engine == "pull"
        else _remotion_overlay_clips(timeline, asset_paths)
    )
    frame_overlays = (
        _frame_overlay_specs(timeline, mode, frame_profile)
        if frame_engine == "pull"
        else []
    )
    video_overlays = _video_track_overlay_clips(timeline, asset_paths)
    overlay_clips = sorted(
        remotion_overlays + frame_overlays + video_overlays,
        key=lambda o: o.position_sec,
    )
    return RenderPlan(
        melt_timeline=timeline_for_melt(timeline),
        overlay_clips=overlay_clips,
        asset_paths=asset_paths,
        emission_profile=requested_profile,
        source_media_policy=source_media_policy,
        source_proxy_hits=source_proxy_hits,
        source_proxy_fallbacks=source_proxy_fallbacks,
        frame_overlays=frame_overlays,
    )


def _default_emission_profile(mode: str) -> EmissionProfile:
    if mode == "final":
        return "final"
    if mode == "proxy":
        return "review-artifact"
    raise ValueError(f"unsupported render mode: {mode!r}")


def resolve_asset_paths(
    ops: list[Operation],
    timeline: Timeline,
    store: AssetStore,
    *,
    source_media_policy: SourceMediaPolicy = "original",
    enqueue_missing_proxies: bool = True,
) -> dict[str, str]:
    """Resolve asset hashes → filesystem paths.

    Collects hashes from applied ops, Remotion compositions, and timeline
    clips (deduplicated), then resolves each once via the AssetStore. The
    public helper keeps the logical asset hash as its key while allowing
    callers to opt into explicit source-proxy semantics.
    """
    asset_paths, _, _ = _resolve_asset_paths_with_diagnostics(
        ops,
        timeline,
        store,
        source_media_policy=source_media_policy,
        enqueue_missing_proxies=enqueue_missing_proxies,
    )
    return asset_paths


def _resolve_asset_paths_with_diagnostics(
    ops: list[Operation],
    timeline: Timeline,
    store: AssetStore,
    *,
    source_media_policy: SourceMediaPolicy,
    enqueue_missing_proxies: bool,
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
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
    source_proxy_hits: dict[str, str] = {}
    source_proxy_fallbacks: dict[str, str] = {}
    materialized_hashes = {
        composition.asset_hash
        for composition in timeline.remotion_compositions
        if composition.asset_hash
    }
    for asset_hash in hashes:
        path = store.path(asset_hash)
        if path is None:
            continue
        if source_media_policy == "original" or asset_hash in materialized_hashes:
            asset_paths[asset_hash] = str(path)
            continue

        asset = store.get(asset_hash)
        proxy_hash = _ready_source_proxy_hash(asset, store)
        if proxy_hash is not None:
            proxy_path = store.path(proxy_hash)
            if proxy_path is not None:
                asset_paths[asset_hash] = str(proxy_path)
                source_proxy_hits[asset_hash] = proxy_hash
                continue

        reason = _source_proxy_fallback_reason(asset, store)
        if enqueue_missing_proxies and _enqueue_missing_source_proxy(
            store,
            asset_hash,
        ):
            source_proxy_fallbacks[asset_hash] = "queued"
        else:
            source_proxy_fallbacks[asset_hash] = reason
        asset_paths[asset_hash] = str(path)
    return asset_paths, source_proxy_hits, source_proxy_fallbacks


def _ready_source_proxy_hash(asset: object, store: AssetStore) -> str | None:
    if asset is None:
        return None
    if (
        getattr(asset, "proxy_status", None) != "ready"
        or getattr(asset, "proxy_profile", None)
        != DEFAULT_SOURCE_PROXY_PROFILE.name
    ):
        return None
    proxy_hash = getattr(asset, "proxy_hash", None)
    if not proxy_hash or store.path(proxy_hash) is None:
        return None
    return str(proxy_hash)


def _source_proxy_fallback_reason(asset: object, store: AssetStore) -> str:
    if asset is None:
        return "asset_metadata_missing"
    if getattr(asset, "proxy_status", None) != "ready":
        return f"status_{getattr(asset, 'proxy_status', 'unknown')}"
    if getattr(asset, "proxy_profile", None) != DEFAULT_SOURCE_PROXY_PROFILE.name:
        return "profile_mismatch"
    proxy_hash = getattr(asset, "proxy_hash", None)
    if not proxy_hash:
        return "proxy_hash_missing"
    if store.path(proxy_hash) is None:
        return "proxy_bytes_missing"
    return "proxy_unavailable"


def _enqueue_missing_source_proxy(store: AssetStore, asset_hash: str) -> bool:
    """Queue one host-side proxy job when the Task 2 service is available."""
    try:
        from open_edit.kernel.asset_proxy_jobs import (
            DEFAULT_ASSET_PROXY_JOB_SERVICE,
        )
    except ImportError:
        # Task 3 remains importable while the optional host-job surface is
        # being deployed; the current render still uses canonical bytes.
        return False

    assets_dir = store.assets_dir
    if assets_dir.parent.name == ".open_edit":
        project_path = assets_dir.parent.parent
    else:
        project_path = assets_dir.parent
    try:
        DEFAULT_ASSET_PROXY_JOB_SERVICE.enqueue(
            project_path.name,
            project_path,
            asset_hash,
            profile=DEFAULT_SOURCE_PROXY_PROFILE,
        )
    except Exception:
        return False
    return True


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


def _frame_overlay_specs(
    timeline: Timeline,
    mode: str,
    frame_profile: RenderProfile | None = None,
) -> list[FrameOverlaySpec]:
    """Convert pending Remotion compositions into pull-stream metadata."""
    overlays: list[FrameOverlaySpec] = []
    for composition in timeline.remotion_compositions:
        profile = frame_profile or remotion_profile_for_mode(
            mode,
            alpha=composition.alpha,
        )
        overlays.append(
            FrameOverlaySpec(
                composition_uid=composition.composition_uid,
                composition_id=composition.composition_id,
                entry_point=composition.entry_point,
                props=dict(composition.props),
                position_sec=composition.position_sec,
                duration_sec=composition.duration_sec,
                width=profile.width,
                height=profile.height,
                fps=profile.frame_rate_num / profile.frame_rate_den,
                alpha=composition.alpha,
                blur_under=bool(composition.props.get("blur_under", False)),
            )
        )
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
