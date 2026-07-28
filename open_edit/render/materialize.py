"""Materialize Remotion compositions into CAS clips before MLT emit.

Fails hard on render errors — never silently drops a composition.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from open_edit.ir.types import Clip, RemotionComposition, Timeline
from open_edit.render.remotion import (
    RemotionRenderError,
    composition_cache_key,
    remotion_profile_for_mode,
    render_composition,
    resolve_remotion_root,
    validate_entry_point,
)
from open_edit.storage.assets import AssetStore


class RemotionMaterializeError(RuntimeError):
    """Raised when a Remotion composition cannot be materialized."""


def _cache_path(project_path: Path) -> Path:
    return resolve_remotion_root(project_path) / "out" / "materialize_cache.json"


def _load_cache(project_path: Path) -> dict[str, str]:
    path = _cache_path(project_path)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_cache(project_path: Path, cache: dict[str, str]) -> None:
    path = _cache_path(project_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


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
    cache = _load_cache(project_path)
    out_dir = resolve_remotion_root(project_path) / "out" / mode
    out_dir.mkdir(parents=True, exist_ok=True)

    # Work on a copy so callers can keep the derived timeline pristine.
    updated = timeline.model_copy(deep=True)

    for composition in list(updated.remotion_compositions):
        profile = remotion_profile_for_mode(mode, alpha=composition.alpha)
        try:
            entry_abs = validate_entry_point(project_path, composition.entry_point)
        except RemotionRenderError as exc:
            raise RemotionMaterializeError(str(exc)) from exc
        entry_source = entry_abs.read_text(encoding="utf-8")
        key = composition_cache_key(
            entry_source=entry_source,
            composition_id=composition.composition_id,
            props=composition.props,
            profile=profile,
            alpha=composition.alpha,
        )
        asset_hash = cache.get(key)
        if asset_hash and assets.path(asset_hash) is not None:
            composition.asset_hash = asset_hash
        else:
            output_path = out_dir / f"{composition.composition_uid}_{key[:12]}.mp4"
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
            cache[key] = asset.asset_hash

        _inject_clip(updated, composition)

    _save_cache(project_path, cache)
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
