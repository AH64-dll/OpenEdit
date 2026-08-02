"""Materialize Remotion compositions into CAS clips before MLT emit.

Fails hard on render errors — never silently drops a composition.
"""
from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Collection, Mapping
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from open_edit.ir.types import Clip, RemotionComposition, Timeline
from open_edit.render.cache import RenderCache
from open_edit.render.frame_engine import (
    PreviewVideoRenderer,
    PreviewVideoRequest,
)
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
from open_edit.render.remotion.dirty import load_manifest, select_dirty_compositions
from open_edit.render.remotion.renderer import remotion_worker_count
from open_edit.storage.assets import AssetStore


class RemotionMaterializeError(RuntimeError):
    """Raised when a Remotion composition cannot be materialized."""


class _UnavailablePreviewVideoRenderer:
    """Explicit feature-gate until the host M1 renderer is registered.

    The chunk worker depends on the ``PreviewVideoRenderer`` protocol rather
    than reaching into Remotion subprocess details.  M1 deployments replace
    this factory result with the host frame-engine implementation; keeping the
    failure here prevents a second, implicit Remotion bake path from being
    introduced by the chunk worker.
    """

    def __init__(self, project_path: Path) -> None:
        self.project_path = project_path

    def render(self, request: PreviewVideoRequest) -> Path:
        del request
        raise RemotionMaterializeError(
            "the M1 PreviewVideoRenderer seam is not available for "
            f"{self.project_path}"
        )


def get_preview_video_renderer(project_path: Path) -> PreviewVideoRenderer:
    """Construct the host-side M1 preview renderer seam."""

    return _UnavailablePreviewVideoRenderer(Path(project_path))


@dataclass
class MaterializeReport:
    """Structured accounting for one Remotion materialization pass."""

    worker_count: int = 2
    cache_hits: int = 0
    cache_misses: int = 0
    reused_manifest_entries: int = 0
    rendered_uids: list[str] = field(default_factory=list)
    dirty_uids: list[str] = field(default_factory=list)
    elapsed_sec: float = 0.0
    manifest_entries: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class _PendingComposition:
    composition_uid: str
    composition: RemotionComposition
    profile: Any
    cache_key: str
    cache_lookup_key: str
    ext: str
    output_path: Path


def _render_cache(project_path: Path) -> RenderCache:
    # File-backed composition cache under the remotion out dir, keyed
    # ``materialize:<composition_id>:<composition hash>``.
    return RenderCache(resolve_remotion_root(project_path) / "out" / "cache")


def _materialize_key(composition_id: str, key: str) -> str:
    return f"materialize:{composition_id}:{key}"


def remotion_profile_manifest_fingerprint(profile: Any) -> str:
    """Return a compact, stable identity for a Remotion output profile."""
    return (
        f"{profile.name}|{profile.width}x{profile.height}|"
        f"{profile.frame_rate_num}/{profile.frame_rate_den}|{profile.vcodec}"
    )


def materialization_manifest_path(
    project_path: Path,
    mode: Literal["proxy", "final"],
    profile_fingerprint: str,
) -> Path:
    """Return the mode/profile-scoped successful-manifest path."""
    digest = hashlib.sha256(profile_fingerprint.encode("utf-8")).hexdigest()[:16]
    return (
        resolve_remotion_root(Path(project_path))
        / "out"
        / f"materialize_manifest.{mode}.{digest}.json"
    )


def build_materialization_manifest(
    timeline: Timeline,
    report: MaterializeReport,
    *,
    mode: Literal["proxy", "final"],
    profile_fingerprint: str,
    graph_hash: str = "",
) -> dict[str, Any]:
    """Build the manifest that is published after a complete render."""
    return {
        "schema": 1,
        "mode": mode,
        "profile_fingerprint": profile_fingerprint,
        "graph_hash": graph_hash,
        "clips": _clip_manifest_entries(timeline),
        "compositions": [dict(entry) for entry in report.manifest_entries],
    }


def materialize_remotion_compositions(
    timeline: Timeline,
    project_path: Path,
    *,
    mode: Literal["proxy", "final"] = "proxy",
    timeout_s: float = 600.0,
    manifest_path: Path | None = None,
    force_remotion: bool = False,
    force_uids: Collection[str] = (),
    report: MaterializeReport | None = None,
    profile_fingerprint: str | None = None,
) -> Timeline:
    """Render pending Remotion compositions and inject clips onto tracks.

    Mutates a deep-copied timeline: each composition becomes a ``Clip`` with
    a real CAS ``asset_hash``. Returns the updated timeline. Raises
    ``RemotionMaterializeError`` on failure (no silent omission).
    """
    started = time.monotonic()
    worker_count = remotion_worker_count()
    if report is not None:
        _reset_report(report, worker_count)
    if not timeline.remotion_compositions:
        if report is not None:
            report.elapsed_sec = time.monotonic() - started
        return timeline

    project_path = Path(project_path).resolve()
    assets = AssetStore(project_path / ".open_edit" / "assets")
    cache = _render_cache(project_path)
    out_dir = resolve_remotion_root(project_path) / "out" / mode
    out_dir.mkdir(parents=True, exist_ok=True)

    # Work on a copy so callers can keep the derived timeline pristine.
    updated = timeline.model_copy(deep=True)
    compositions = list(updated.remotion_compositions)
    effective_manifest_path = (
        Path(manifest_path)
        if manifest_path is not None
        else materialization_manifest_path(
            project_path,
            mode,
            profile_fingerprint or mode,
        )
    )
    previous = load_manifest(effective_manifest_path)
    force_set = {str(uid) for uid in force_uids}
    if force_remotion:
        force_set.update(composition.composition_uid for composition in compositions)

    # Validate, stage, resolve, and key every composition before any worker is
    # created. Workers must only wait on their own Remotion subprocess.
    prepared: list[_PendingComposition] = []
    current_entries: list[dict[str, Any]] = []
    for composition in compositions:
        profile = remotion_profile_for_mode(mode, alpha=composition.alpha)
        try:
            validate_entry_point(project_path, composition.entry_point)
        except RemotionRenderError as exc:
            raise _materialize_error(composition, exc) from exc
        composition_source = composition_source_bundle(
            project_path, composition.composition_id,
        )
        try:
            stage_referenced_assets(
                project_path, composition_source, composition.props,
            )
        except RemotionRenderError as exc:
            raise _materialize_error(composition, exc) from exc
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
        cache_lookup_key = _materialize_key(composition.composition_id, key)
        current_entries.append(_composition_manifest_entry(
            composition,
            cache_key=key,
            ext=ext,
            mode=mode,
            profile=profile,
            asset_hash=None,
        ))
        prepared.append(_PendingComposition(
            composition_uid=composition.composition_uid,
            composition=composition,
            profile=profile,
            cache_key=key,
            cache_lookup_key=cache_lookup_key,
            ext=ext,
            output_path=out_dir / f"{composition.composition_uid}_{key[:12]}.{ext}",
        ))

    current_manifest = {
        "schema": 1,
        "mode": mode,
        "profile_fingerprint": (
            profile_fingerprint
            or remotion_profile_manifest_fingerprint(prepared[0].profile)
        ),
        "graph_hash": "",
        "clips": _clip_manifest_entries(timeline),
        "compositions": current_entries,
    }
    selection = select_dirty_compositions(
        previous,
        current_manifest,
        force_uids=force_set,
    )
    ordered_uids = [composition.composition_uid for composition in compositions]
    if report is not None:
        report.dirty_uids = [
            uid for uid in ordered_uids if uid in selection.composition_uids
        ]

    rendered_results: dict[str, Any] = {}
    pending: list[_PendingComposition] = []
    for item in prepared:
        composition = item.composition
        previous_entry = _previous_composition(previous, item.composition_uid)
        manifest_asset_hash = (
            previous_entry.get("asset_hash") if previous_entry else None
        )
        if (
            item.composition_uid not in force_set
            and previous_entry is not None
            and previous_entry.get("cache_key") == item.cache_key
            and previous_entry.get("mode") == mode
            and manifest_asset_hash
            and assets.path(str(manifest_asset_hash)) is not None
        ):
            composition.asset_hash = str(manifest_asset_hash)
            if report is not None:
                report.reused_manifest_entries += 1
            continue

        cached_path = None
        if item.composition_uid not in force_set:
            cached_path = cache.get(item.cache_lookup_key, ext=item.ext)
        if cached_path is not None:
            composition.asset_hash = _ingest_cached(
                assets, cached_path, composition,
            )
            if report is not None:
                report.cache_hits += 1
            continue

        pending.append(item)
        if report is not None:
            report.cache_misses += 1

    if pending:
        cancel_event = threading.Event()
        executor = ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="open-edit-remotion",
        )
        futures: dict[Future[Any], _PendingComposition] = {}
        try:
            for item in pending:
                futures[executor.submit(
                    _render_pending,
                    item,
                    project_path,
                    timeout_s,
                    cancel_event,
                )] = item
            for future in as_completed(futures):
                item = futures[future]
                try:
                    rendered_results[item.composition_uid] = future.result()
                except BaseException as exc:
                    cancel_event.set()
                    for other in futures:
                        if other is not future:
                            other.cancel()
                    raise _materialize_error(item.composition, exc) from exc
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

        # Ingest and cache on the caller thread, in timeline order. This
        # keeps CAS writes and timeline state deterministic.
        for item in pending:
            composition = item.composition
            result = rendered_results[item.composition_uid]
            try:
                asset = assets.ingest(result.output_path, transcribe=False)
                cache.put(item.cache_lookup_key, result.output_path, ext=item.ext)
            except Exception as exc:
                raise RemotionMaterializeError(
                    f"failed to ingest remotion output for "
                    f"{composition.composition_uid!r}: {_bounded_error(exc)}"
                ) from exc
            composition.asset_hash = asset.asset_hash
            if report is not None:
                report.rendered_uids.append(composition.composition_uid)

    for composition in compositions:
        _inject_clip(updated, composition)

    if report is not None:
        report.manifest_entries = [
            _composition_manifest_entry(
                composition,
                cache_key=item.cache_key,
                ext=item.ext,
                mode=mode,
                profile=item.profile,
                asset_hash=composition.asset_hash,
            )
            for composition, item in zip(compositions, prepared)
        ]
        report.elapsed_sec = time.monotonic() - started
    # Compositions remain on the timeline for inspection, but clips are now
    # present for emit_timeline.
    return updated


def _reset_report(report: MaterializeReport, worker_count: int) -> None:
    report.worker_count = worker_count
    report.cache_hits = 0
    report.cache_misses = 0
    report.reused_manifest_entries = 0
    report.rendered_uids.clear()
    report.dirty_uids.clear()
    report.elapsed_sec = 0.0
    report.manifest_entries.clear()


def _previous_composition(
    manifest: Mapping[str, Any] | None,
    composition_uid: str,
) -> Mapping[str, Any] | None:
    if not manifest:
        return None
    entries = manifest.get("compositions", ())
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        identity = (
            entry.get("composition_uid")
            or entry.get("uid")
            or entry.get("id")
        )
        if str(identity) == composition_uid:
            return entry
    return None


def _composition_manifest_entry(
    composition: RemotionComposition,
    *,
    cache_key: str,
    ext: str,
    mode: Literal["proxy", "final"],
    profile: Any,
    asset_hash: str | None,
) -> dict[str, Any]:
    return {
        "composition_uid": composition.composition_uid,
        "composition_id": composition.composition_id,
        "entry_point": composition.entry_point,
        "props": composition.props,
        "position_sec": composition.position_sec,
        "duration_sec": composition.duration_sec,
        "cache_key": cache_key,
        "asset_hash": asset_hash,
        "ext": ext,
        "alpha": composition.alpha,
        "mode": mode,
        "profile_fingerprint": remotion_profile_manifest_fingerprint(profile),
    }


def _clip_manifest_entries(timeline: Timeline) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for track in timeline.tracks:
        for clip in track.clips:
            entry = clip.model_dump(mode="json")
            entry["duration_sec"] = max(
                0.0, clip.out_point_sec - clip.in_point_sec,
            )
            entries.append(entry)
    return entries


def _ingest_cached(
    assets: AssetStore,
    cached_path: Path,
    composition: RemotionComposition,
) -> str:
    try:
        return assets.ingest(cached_path, transcribe=False).asset_hash
    except Exception as exc:
        raise RemotionMaterializeError(
            f"failed to re-ingest cached remotion output for "
            f"{composition.composition_uid!r}: {_bounded_error(exc)}"
        ) from exc


def _render_pending(
    item: _PendingComposition,
    project_path: Path,
    timeout_s: float,
    cancel_event: threading.Event,
) -> Any:
    return render_composition(
        project_path,
        entry_point=item.composition.entry_point,
        composition_id=item.composition.composition_id,
        props=item.composition.props,
        output_path=item.output_path,
        profile=item.profile,
        timeout_s=timeout_s,
        alpha=item.composition.alpha,
        cancel_event=cancel_event,
        stage_assets=False,
    )


def _materialize_error(
    composition: RemotionComposition,
    error: BaseException,
) -> RemotionMaterializeError:
    return RemotionMaterializeError(
        f"remotion materialize failed for UID "
        f"{composition.composition_uid!r} ({composition.composition_id!r}): "
        f"{_bounded_error(error)}"
    )


def _bounded_error(error: BaseException, limit: int = 500) -> str:
    text = str(error).strip().replace("\x00", "")
    return text[:limit] or type(error).__name__


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
