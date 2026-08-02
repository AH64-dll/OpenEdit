"""Materialize Remotion compositions into CAS clips before MLT emit.

Fails hard on render errors — never silently drops a composition.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from open_edit.ir.types import Clip, RemotionComposition, Timeline
from open_edit.render.cache import RenderCache
from open_edit.render.remotion import (
    RemotionRenderError,
    composition_cache_key,
    composition_source_bundle,
    remotion_profile_for_mode,
    render_composition,
    resolve_remotion_root,
    stage_referenced_assets,
    validate_entry_point,
)
from open_edit.storage.assets import AssetStore


class RemotionMaterializeError(RuntimeError):
    """Raised when a Remotion composition cannot be materialized."""


def _render_cache(project_path: Path) -> RenderCache:
    # File-backed composition cache under the remotion out dir, keyed
    # ``materialize:<composition_id>:<composition hash>``.
    return RenderCache(resolve_remotion_root(project_path) / "out" / "cache")


def _materialize_key(composition_id: str, key: str) -> str:
    return f"materialize:{composition_id}:{key}"


def materialize_remotion_compositions(
    timeline: Timeline,
    project_path: Path,
    *,
    mode: Literal["proxy", "final"] = "proxy",
    timeout_s: float = 600.0,
) -> Timeline:
    """Render pending Remotion compositions and inject clips onto tracks.

    Mutates a deep-copied timeline: each composition becomes a ``Clip`` with
    a real CAS ``asset_hash``. Returns the updated timeline. Raises
    ``RemotionMaterializeError`` on failure (no silent omission).
    """
    if not timeline.remotion_compositions:
        return timeline

    project_path = Path(project_path).resolve()
    assets = AssetStore(project_path / ".open_edit" / "assets")
    cache = _render_cache(project_path)
    out_dir = resolve_remotion_root(project_path) / "out" / mode
    out_dir.mkdir(parents=True, exist_ok=True)

    # Work on a copy so callers can keep the derived timeline pristine.
    updated = timeline.model_copy(deep=True)

    for composition in list(updated.remotion_compositions):
        profile = remotion_profile_for_mode(mode, alpha=composition.alpha)
        try:
            validate_entry_point(project_path, composition.entry_point)
        except RemotionRenderError as exc:
            raise RemotionMaterializeError(str(exc)) from exc
        composition_source = composition_source_bundle(
            project_path, composition.composition_id,
        )
        try:
            stage_referenced_assets(
                project_path, composition_source, composition.props,
            )
        except RemotionRenderError as exc:
            raise RemotionMaterializeError(str(exc)) from exc
        key = composition_cache_key(
            composition_source=composition_source,
            composition_id=composition.composition_id,
            props=composition.props,
            profile=profile,
            alpha=composition.alpha,
            duration_sec=composition.duration_sec,
            project_path=project_path,
        )
        # ProRes 4444 with alpha is .mov; VP8 alpha is WebM. The container
        # extension must agree with Remotion's codec or its CLI rejects the
        # render before starting.
        if composition.alpha:
            ext = "webm" if profile.vcodec in {"libvpx", "libvpx-vp9"} else "mov"
        else:
            ext = "mp4"
        cache_key = _materialize_key(composition.composition_id, key)
        cached_path = cache.get(cache_key, ext=ext)
        if cached_path is not None:
            try:
                asset = assets.ingest(cached_path, transcribe=False)
            except Exception as exc:
                raise RemotionMaterializeError(
                    f"failed to re-ingest cached remotion output for "
                    f"{composition.composition_id!r}: {exc}"
                ) from exc
            composition.asset_hash = asset.asset_hash
        else:
            output_path = out_dir / f"{composition.composition_uid}_{key[:12]}.{ext}"
            try:
                result = render_composition(
                    project_path,
                    entry_point=composition.entry_point,
                    composition_id=composition.composition_id,
                    props=composition.props,
                    output_path=output_path,
                    profile=profile,
                    timeout_s=timeout_s,
                    alpha=composition.alpha,
                )
            except RemotionRenderError as exc:
                raise RemotionMaterializeError(
                    f"remotion materialize failed for "
                    f"{composition.composition_id!r}: {exc}"
                ) from exc
            try:
                asset = assets.ingest(result.output_path, transcribe=False)
            except Exception as exc:
                raise RemotionMaterializeError(
                    f"failed to ingest remotion output for "
                    f"{composition.composition_id!r}: {exc}"
                ) from exc
            composition.asset_hash = asset.asset_hash
            cache.put(cache_key, result.output_path, ext=ext)

        _inject_clip(updated, composition)

    # Compositions remain on the timeline for inspection, but clips are now
    # present for emit_timeline.
    return updated


def _inject_clip(timeline: Timeline, composition: RemotionComposition) -> None:
    assert composition.asset_hash
    track = None
    for candidate in timeline.tracks:
        if candidate.track_id == composition.track_id:
            track = candidate
            break
    if track is None:
        from open_edit.ir.types import Track
        track = Track(track_id=composition.track_id, kind="video")
        timeline.tracks.append(track)

    # Replace existing clip with same clip_id if re-materializing.
    track.clips = [c for c in track.clips if c.clip_id != composition.clip_id]
    track.clips.append(Clip(
        clip_id=composition.clip_id,
        asset_hash=composition.asset_hash,
        track_id=composition.track_id,
        track_kind="video",
        position_sec=composition.position_sec,
        in_point_sec=0.0,
        out_point_sec=composition.duration_sec,
    ))
    track.clips.sort(key=lambda c: c.position_sec)
