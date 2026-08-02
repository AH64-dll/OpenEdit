"""Host-worker orchestration for frame-aligned preview chunks.

The worker owns the lifecycle around the preview manifest.  Rendering itself
is delegated to the M1 video-renderer seam and to a small host subprocess
runner for the independent audio/mux commands.  A manifest is published only
after every artifact referenced by that manifest has been validated.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable, Mapping
from fractions import Fraction
from pathlib import Path
from typing import Any

from open_edit.ir.hash import compute_edit_graph_hash
from open_edit.ir.types import Operation, Project, Timeline
from open_edit.render.emitter import EmitterConfig, emit_timeline
from open_edit.render.encoder import EncoderSpec
from open_edit.render.frame_engine import PreviewVideoRenderer, PreviewVideoRequest
from open_edit.render.materialize import get_preview_video_renderer
from open_edit.render.pipe_builder import OverlayClip
from open_edit.render.preview_cache import PreviewChunkCache
from open_edit.render.preview_invalidation import (
    ChunkFingerprint,
    ChunkWindow,
    compute_chunk_fingerprints,
    make_chunk_windows,
    select_dirty_windows,
    slice_timeline,
)
from open_edit.render.preview_manifest import (
    PreviewArtifact,
    PreviewChunk,
    PreviewManifest,
    PreviewPlaneState,
    PreviewRange,
    effective_status,
)
from open_edit.render.preview_pipe import (
    PreviewPipeCommands,
    build_preview_pipe_commands,
)
from open_edit.render.profiles import (
    RenderProfile,
    preview_chunk_profile,
    preview_profile_fingerprint,
    profile_fingerprint,
    resolve_encoder_args,
)
from open_edit.render.remotion.safety import render_reference_fingerprint
from open_edit.storage.assets import AssetStore, list_assets_from_disk
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.storage.paths import ProjectPaths
from open_edit.storage.timeline_cache import derive_or_load_timeline

_DEFAULT_FPS_NUM = 30
_DEFAULT_FPS_DEN = 1
_MEDIA = frozenset({"video", "audio", "both"})
_PLANES = ("video", "audio", "playback")


class PreviewChunkWorkerError(RuntimeError):
    """Raised when a preview job cannot produce a worker result."""


class _GraphChangedError(Exception):
    """Internal control flow for a stale worker."""


def _load_job_params(project_dir: Path, job_id: str) -> dict[str, Any]:
    """Load normalized parameters from the durable render-job row.

    Task 8 owns the job schema and CLI.  Keeping this lookup lazy lets the
    worker remain usable in isolation and makes unit tests independent of the
    render-job service.
    """

    try:
        from open_edit.kernel.render_jobs import RenderJobService

        job = RenderJobService().get(project_dir, job_id)
    except Exception:
        return {}
    if job is None or not isinstance(job.params, Mapping):
        return {}
    return dict(job.params)


def _preview_cache(project_dir: Path) -> PreviewChunkCache:
    return PreviewChunkCache(project_dir / ".open_edit" / "preview_chunks")


def _load_project_state(
    project_id: str,
    project_dir: Path,
) -> tuple[
    EditGraphStore,
    list[Operation],
    Project,
    Timeline,
    int,
    str,
]:
    paths = ProjectPaths.for_project(project_dir)
    store = EditGraphStore(paths.db_path)
    operations = store.load_all()
    assets = {
        asset.asset_hash: asset
        for asset in list_assets_from_disk(project_dir)
    }
    project = Project(
        project_id=project_id,
        name=project_dir.name,
        workdir=project_dir,
        assets=assets,
        edit_graph=operations,
    )
    timeline = derive_or_load_timeline(project, store, strict=True)
    return (
        store,
        operations,
        project,
        timeline,
        store.graph_revision(),
        compute_edit_graph_hash(operations),
    )


def _graph_identity(store: EditGraphStore) -> tuple[int, str]:
    operations = store.load_all()
    return store.graph_revision(), compute_edit_graph_hash(operations)


def _load_snapshot(
    store: EditGraphStore,
    manifest: PreviewManifest | None,
    current_timeline: Timeline,
    current_hash: str,
) -> Timeline | None:
    if manifest is None:
        return None
    if manifest.edit_graph_hash == current_hash:
        return current_timeline
    try:
        payload = store.load_timeline_snapshot(manifest.edit_graph_hash)
        if payload is None:
            return None
        return Timeline.model_validate_json(payload)
    except Exception:
        return None


def _project_fps(project_dir: Path, params: Mapping[str, Any]) -> tuple[int, int]:
    raw_num = params.get("fps_num")
    raw_den = params.get("fps_den")
    if raw_num is not None or raw_den is not None:
        try:
            num = int(raw_num)
            den = int(raw_den or 1)
            if num > 0 and den > 0:
                return num, den
        except (TypeError, ValueError):
            pass

    for asset in list_assets_from_disk(project_dir):
        if asset.fps is None or asset.fps <= 0:
            continue
        fraction = Fraction(str(asset.fps)).limit_denominator(1001)
        if fraction.numerator > 0 and fraction.denominator > 0:
            return fraction.numerator, fraction.denominator
    return _DEFAULT_FPS_NUM, _DEFAULT_FPS_DEN


def _chunk_size(
    fps_num: int,
    fps_den: int,
    params: Mapping[str, Any],
) -> int | None:
    raw = params.get("chunk_frames")
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _parse_params(params: Mapping[str, Any]) -> tuple[
    list[PreviewRange],
    str,
    bool,
]:
    raw_media = params.get("media", "both")
    media = str(raw_media)
    if media not in _MEDIA:
        raise PreviewChunkWorkerError(
            "media must be one of video, audio, or both"
        )

    raw_ranges = params.get("ranges") or []
    if not isinstance(raw_ranges, (list, tuple)):
        raise PreviewChunkWorkerError("ranges must be a list")
    try:
        ranges = [
            item if isinstance(item, PreviewRange) else PreviewRange.model_validate(item)
            for item in raw_ranges
        ]
    except Exception as exc:
        raise PreviewChunkWorkerError(f"invalid preview range: {exc}") from exc

    priority = str(params.get("priority", "interactive"))
    if priority not in {"interactive", "background"}:
        raise PreviewChunkWorkerError(
            "priority must be interactive or background"
        )
    return ranges, media, priority == "background"


def _content_fingerprint(
    project_dir: Path,
    project: Project,
    timeline: Timeline | None = None,
) -> str:
    """Hash stable source identities used by the chunk keys."""

    assets = [
        {
            "asset_hash": asset.asset_hash,
            "content_hash": asset.content_hash or asset.asset_hash,
            "proxy_hash": asset.proxy_hash,
            "proxy_profile": asset.proxy_profile,
            "proxy_status": asset.proxy_status,
        }
        for asset in sorted(project.assets.values(), key=lambda item: item.asset_hash)
    ]
    try:
        remotion = render_reference_fingerprint(
            project_dir,
            list(timeline.remotion_compositions) if timeline is not None else [],
            alpha_mode="opaque",
        )
    except Exception:
        remotion = ""
    payload = {"assets": assets, "remotion": remotion}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _profile_info(
    profile: RenderProfile,
    encoder_backend: str | None,
) -> dict[str, Any]:
    return {
        "name": profile.name,
        "width": profile.width,
        "height": profile.height,
        "fps_num": profile.frame_rate_num,
        "fps_den": profile.frame_rate_den,
        "video_codec": profile.vcodec,
        "audio_codec": profile.acodec,
        "audio_bitrate": profile.ab or "96k",
        "fingerprint": profile_fingerprint(profile, encoder_backend),
        "video_fingerprint": preview_profile_fingerprint(
            profile, "video", encoder_backend,
        ),
        "audio_fingerprint": preview_profile_fingerprint(
            profile, "audio", encoder_backend,
        ),
        "mux_fingerprint": preview_profile_fingerprint(
            profile, "mux", encoder_backend,
        ),
    }


def _artifact_is_usable(
    cache: PreviewChunkCache,
    artifact: PreviewArtifact | None,
) -> PreviewArtifact | None:
    if artifact is None:
        return None
    return artifact if cache.resolve_artifact(artifact.artifact_id) else None


def _prior_artifact(
    cache: PreviewChunkCache,
    state: PreviewPlaneState | None,
) -> PreviewArtifact | None:
    if state is None:
        return None
    if state.status == "green":
        return (
            _artifact_is_usable(cache, state.current)
            or _artifact_is_usable(cache, state.fallback)
        )
    return (
        _artifact_is_usable(cache, state.fallback)
        or _artifact_is_usable(cache, state.current)
    )


def _initial_plane_state(
    cache: PreviewChunkCache,
    old_state: PreviewPlaneState | None,
    dirty: bool,
) -> PreviewPlaneState:
    prior = _prior_artifact(cache, old_state)
    if prior is None:
        return PreviewPlaneState(status="red")
    if not dirty and old_state is not None and old_state.status == "green":
        return PreviewPlaneState(status="green", current=prior)
    return PreviewPlaneState(status="yellow", fallback=prior)


def _chunk_status(chunk: PreviewChunk) -> str:
    candidate = chunk.model_copy(update={"status": "green"})
    return effective_status(candidate)


def _make_chunk_id(window: ChunkWindow) -> str:
    return f"{window.start_frame:06d}-{window.end_frame:06d}"


def _old_chunks(manifest: PreviewManifest | None) -> dict[tuple[int, int, int], PreviewChunk]:
    if manifest is None:
        return {}
    return {
        (chunk.index, chunk.start_frame, chunk.end_frame): chunk
        for chunk in manifest.chunks
    }


def _initial_manifest(
    *,
    cache: PreviewChunkCache,
    previous: PreviewManifest | None,
    project_id: str,
    graph_revision: int,
    graph_hash: str,
    timeline: Timeline,
    windows: list[ChunkWindow],
    fingerprints: list[ChunkFingerprint],
    profile_info: dict[str, Any],
    fps_num: int,
    fps_den: int,
    chunk_frames: int,
    job_id: str,
) -> PreviewManifest:
    old_by_window = _old_chunks(previous)
    chunks: list[PreviewChunk] = []
    for window, fingerprint in zip(windows, fingerprints, strict=True):
        old = old_by_window.get(
            (window.index, window.start_frame, window.end_frame)
        )
        video = _initial_plane_state(
            cache,
            old.video if old is not None else None,
            fingerprint.video_dirty,
        )
        audio = _initial_plane_state(
            cache,
            old.audio if old is not None else None,
            fingerprint.audio_dirty,
        )
        playback = _initial_plane_state(
            cache,
            old.playback if old is not None else None,
            fingerprint.video_dirty or fingerprint.audio_dirty,
        )
        chunk = PreviewChunk(
            chunk_id=_make_chunk_id(window),
            index=window.index,
            start_frame=window.start_frame,
            end_frame=window.end_frame,
            start_sec=window.start_frame * fps_den / fps_num,
            end_sec=window.end_frame * fps_den / fps_num,
            status="red",
            video=video,
            audio=audio,
            playback=playback,
        )
        chunks.append(chunk.model_copy(update={"status": _chunk_status(chunk)}))
    return PreviewManifest(
        project_id=project_id,
        graph_revision=graph_revision,
        edit_graph_hash=graph_hash,
        duration_frames=max(
            0, round(timeline.duration_sec * fps_num / fps_den)
        ),
        duration_sec=max(0.0, float(timeline.duration_sec)),
        fps_num=fps_num,
        fps_den=fps_den,
        chunk_frames=chunk_frames,
        profile=profile_info,
        job_id=job_id,
        updated_at=time.time(),
        chunks=chunks,
    )


def _new_fingerprint_for_media(
    fingerprints: list[ChunkFingerprint],
    media: str,
) -> list[ChunkFingerprint]:
    if media == "video":
        return [
            dataclasses.replace(item, audio_dirty=False)
            for item in fingerprints
        ]
    if media == "audio":
        return [
            dataclasses.replace(item, video_dirty=False)
            for item in fingerprints
        ]
    return list(fingerprints)


def _resolve_encoder(
    profile: RenderProfile,
    params: Mapping[str, Any],
    *,
    injected_runner: bool,
) -> EncoderSpec:
    """Avoid probing host encoders in fake-runner tests."""

    if injected_runner:
        return EncoderSpec(
            vcodec=profile.vcodec,
            melt_args=(),
            ffmpeg_args=(),
        )
    backend = params.get("encoder")
    return resolve_encoder_args(
        profile,
        str(backend) if backend is not None else None,
    )


def _slice_and_emit(
    *,
    project_dir: Path,
    operations: list[Operation],
    timeline: Timeline,
    window: ChunkWindow,
    profile: RenderProfile,
    plane: str,
    temp_dir: Path,
) -> tuple[Timeline, Path, list[OverlayClip]]:
    sliced = slice_timeline(
        timeline,
        render_start_frame=window.render_start_frame,
        render_end_frame=window.render_end_frame,
        fps_num=profile.frame_rate_num,
        fps_den=profile.frame_rate_den,
        plane=plane,  # type: ignore[arg-type]
    )
    from open_edit.render.timeline_plan import build_render_plan

    plan = build_render_plan(
        sliced,
        operations,
        AssetStore(project_dir / ".open_edit" / "assets"),
        "preview-chunks",
        frame_engine="pull" if plane == "video" else "materialize",
        frame_profile=profile,
        emission_profile="preview-chunk",
        enqueue_missing_proxies=False,
    )
    xml_path = temp_dir / f"chunk-{window.index:06d}-{plane}.mlt"
    xml_path.write_text(
        emit_timeline(
            plan.melt_timeline,
            EmitterConfig(profile=profile.model_dump()),
            asset_paths=plan.asset_paths,
        ),
        encoding="utf-8",
    )
    overlays = [
        overlay
        for overlay in plan.overlay_clips
        if isinstance(overlay, OverlayClip)
    ]
    return sliced, xml_path, overlays


def _validate_output(path: Path, label: str) -> None:
    try:
        stat = path.stat()
    except OSError as exc:
        raise PreviewChunkWorkerError(
            f"{label} output is unavailable: {path}"
        ) from exc
    if not path.is_file() or stat.st_size <= 0:
        raise PreviewChunkWorkerError(f"{label} output is empty: {path}")


def _mux_temp_path(playback_path: Path) -> Path:
    return playback_path.with_name(
        f".{playback_path.stem}.tmp{playback_path.suffix}"
    )


def _replace_commands(
    commands: PreviewPipeCommands,
    *,
    video_cmd: list[str] | None = None,
    audio_cmd: list[str] | None = None,
) -> PreviewPipeCommands:
    return dataclasses.replace(
        commands,
        video_cmd=video_cmd,
        audio_cmd=audio_cmd,
    )


def _run_pipeline(command: list[str], *, timeout_s: float) -> None:
    if "|" not in command:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        if completed.returncode != 0:
            raise PreviewChunkWorkerError(
                (completed.stderr or "preview command failed").strip()
            )
        return

    separator = command.index("|")
    producer_cmd = command[:separator]
    consumer_cmd = command[separator + 1:]
    if not producer_cmd or not consumer_cmd:
        raise PreviewChunkWorkerError("invalid preview pipeline command")
    producer = subprocess.Popen(
        producer_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert producer.stdout is not None
    consumer = subprocess.Popen(
        consumer_cmd,
        stdin=producer.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    producer.stdout.close()
    try:
        _, consumer_stderr = consumer.communicate(timeout=timeout_s)
        producer_stderr = producer.stderr.read() if producer.stderr else b""
        producer.wait(timeout=5)
    except subprocess.TimeoutExpired as exc:
        consumer.kill()
        producer.kill()
        consumer.wait()
        producer.wait()
        raise PreviewChunkWorkerError(
            "preview pipeline timed out"
        ) from exc
    if producer.returncode != 0 or consumer.returncode != 0:
        details = (
            consumer_stderr.decode(errors="replace")
            or producer_stderr.decode(errors="replace")
            or "preview pipeline failed"
        ).strip()
        raise PreviewChunkWorkerError(details)


def run_preview_pipe(commands: PreviewPipeCommands) -> None:
    """Run the selected host-side preview commands without a shell."""

    timeout_s = float(os.environ.get("OPEN_EDIT_PREVIEW_PIPE_TIMEOUT_S", "7200"))
    for command in (commands.video_cmd, commands.audio_cmd, commands.mux_cmd):
        if command is not None:
            _run_pipeline(command, timeout_s=timeout_s)

    mux_temp = _mux_temp_path(commands.playback_output)
    if mux_temp.is_file():
        os.replace(mux_temp, commands.playback_output)

    for path, label in (
        (commands.video_output, "video"),
        (commands.audio_output, "audio"),
        (commands.playback_output, "playback"),
    ):
        if path is not None and (
            (commands.video_cmd is not None and path == commands.video_output)
            or (commands.audio_cmd is not None and path == commands.audio_output)
            or (commands.mux_cmd is not None and path == commands.playback_output)
        ):
            _validate_output(path, label)


def _check_graph(
    store: EditGraphStore,
    graph_revision: int,
    graph_hash: str,
) -> None:
    if _graph_identity(store) != (graph_revision, graph_hash):
        raise _GraphChangedError


def _set_plane_state(
    chunk: PreviewChunk,
    plane: str,
    state: PreviewPlaneState,
) -> PreviewChunk:
    return chunk.model_copy(
        update={
            plane: state,
            "status": _chunk_status(
                chunk.model_copy(update={plane: state})
            ),
        }
    )


def _artifact_path(
    cache: PreviewChunkCache,
    state: PreviewPlaneState,
) -> Path | None:
    artifact = state.current or state.fallback
    return cache.resolve_artifact(artifact.artifact_id) if artifact else None


def _playback_key(
    *,
    video: PreviewArtifact,
    audio: PreviewArtifact,
    profile: dict[str, Any],
    chunk: PreviewChunk,
) -> str:
    payload = {
        "video": video.key,
        "audio": audio.key,
        "profile": profile.get("mux_fingerprint", ""),
        "range": [chunk.start_frame, chunk.end_frame],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _bake_chunk(
    *,
    cache: PreviewChunkCache,
    active: PreviewManifest,
    chunk_index: int,
    window: ChunkWindow,
    fingerprint: ChunkFingerprint,
    operations: list[Operation],
    timeline: Timeline,
    project_dir: Path,
    temp_dir: Path,
    renderer: PreviewVideoRenderer,
    run_commands: Callable[[PreviewPipeCommands], None],
    profile: RenderProfile,
    encoder: EncoderSpec,
    melt_bin: str,
    media: str,
    store: EditGraphStore,
    graph_revision: int,
    graph_hash: str,
    failed_chunks: list[str],
) -> bool:
    chunk = active.chunks[chunk_index]
    video_changed = False
    audio_changed = False
    xml_path: Path | None = None
    overlays: list[OverlayClip] = []

    def fail_plane(plane: str, error: BaseException) -> None:
        del error
        nonlocal chunk
        old_state = getattr(chunk, plane)
        chunk = _set_plane_state(
            chunk,
            plane,
            old_state.model_copy(update={"status": "red", "current": None}),
        )
        if chunk.chunk_id not in failed_chunks:
            failed_chunks.append(chunk.chunk_id)

    need_video = media in {"video", "both"} and (
        fingerprint.video_dirty or chunk.video.current is None
    )
    need_audio = media in {"audio", "both"} and (
        fingerprint.audio_dirty or chunk.audio.current is None
    )

    if need_video:
        try:
            _check_graph(store, graph_revision, graph_hash)
            sliced, xml_path, overlays = _slice_and_emit(
                project_dir=project_dir,
                operations=operations,
                timeline=timeline,
                window=window,
                profile=profile,
                plane="video",
                temp_dir=temp_dir,
            )
            request: PreviewVideoRequest = {
                "project_dir": project_dir,
                "timeline": sliced,
                "render_start_frame": window.render_start_frame,
                "render_end_frame": window.render_end_frame,
                "core_start_frame": window.start_frame,
                "core_end_frame": window.end_frame,
                "composition_uids": fingerprint.composition_uids,
                "profile": profile,
                "output_path": temp_dir / f"video-{chunk.index:06d}.mp4",
            }
            rendered_path = Path(renderer.render(request))
            _check_graph(store, graph_revision, graph_hash)
            _validate_output(rendered_path, "video")
            artifact = cache.commit_artifact(
                plane="video",
                key=fingerprint.video_key,
                source=rendered_path,
                suffix="mp4",
                graph_hash=graph_hash,
            )
            chunk = _set_plane_state(
                chunk,
                "video",
                PreviewPlaneState(status="green", current=artifact),
            )
            video_changed = True
        except _GraphChangedError:
            raise
        except Exception as exc:
            fail_plane("video", exc)

    if need_audio:
        try:
            _check_graph(store, graph_revision, graph_hash)
            _sliced, xml_path, audio_overlays = _slice_and_emit(
                project_dir=project_dir,
                operations=operations,
                timeline=timeline,
                window=window,
                profile=profile,
                plane="audio",
                temp_dir=temp_dir,
            )
            del audio_overlays
            audio_output = temp_dir / f"audio-{chunk.index:06d}.m4a"
            commands = build_preview_pipe_commands(
                melt_bin=melt_bin,
                xml_path=xml_path,
                video_output=None,
                audio_output=audio_output,
                playback_output=temp_dir / f"playback-{chunk.index:06d}.mp4",
                profile=profile,
                encoder=encoder,
                overlays=[],
                crop_head_frames=window.crop_head_frames,
                crop_tail_frames=window.crop_tail_frames,
                core_frames=window.end_frame - window.start_frame,
                media="audio",
            )
            run_commands(commands)
            _check_graph(store, graph_revision, graph_hash)
            _validate_output(audio_output, "audio")
            artifact = cache.commit_artifact(
                plane="audio",
                key=fingerprint.audio_key,
                source=audio_output,
                suffix="m4a",
                graph_hash=graph_hash,
            )
            chunk = _set_plane_state(
                chunk,
                "audio",
                PreviewPlaneState(status="green", current=artifact),
            )
            audio_changed = True
        except _GraphChangedError:
            raise
        except Exception as exc:
            fail_plane("audio", exc)

    if video_changed or audio_changed:
        video_path = _artifact_path(cache, chunk.video)
        audio_path = _artifact_path(cache, chunk.audio)
        video_artifact = chunk.video.current
        audio_artifact = chunk.audio.current
        if (
            video_path is not None
            and audio_path is not None
            and video_artifact is not None
            and audio_artifact is not None
        ):
            try:
                _check_graph(store, graph_revision, graph_hash)
                if xml_path is None:
                    xml_path = temp_dir / f"chunk-{chunk.index:06d}-mux.mlt"
                    xml_path.write_text("<mlt/>", encoding="utf-8")
                playback_output = temp_dir / f"playback-{chunk.index:06d}.mp4"
                commands = build_preview_pipe_commands(
                    melt_bin=melt_bin,
                    xml_path=xml_path,
                    video_output=video_path,
                    audio_output=audio_path,
                    playback_output=playback_output,
                    profile=profile,
                    encoder=encoder,
                    overlays=overlays,
                    crop_head_frames=0,
                    crop_tail_frames=0,
                    core_frames=window.end_frame - window.start_frame,
                    media="both",
                )
                run_commands(_replace_commands(commands))
                mux_temp = _mux_temp_path(playback_output)
                if mux_temp.is_file() and not playback_output.is_file():
                    os.replace(mux_temp, playback_output)
                _check_graph(store, graph_revision, graph_hash)
                _validate_output(playback_output, "playback")
                artifact = cache.commit_artifact(
                    plane="playback",
                    key=_playback_key(
                        video=video_artifact,
                        audio=audio_artifact,
                        profile=active.profile,
                        chunk=chunk,
                    ),
                    source=playback_output,
                    suffix="mp4",
                    graph_hash=graph_hash,
                )
                chunk = _set_plane_state(
                    chunk,
                    "playback",
                    PreviewPlaneState(status="green", current=artifact),
                )
            except _GraphChangedError:
                raise
            except Exception as exc:
                fail_plane("playback", exc)

    active.chunks[chunk_index] = chunk.model_copy(
        update={"status": _chunk_status(chunk)}
    )
    return True


def _newer_manifest(
    manifest: PreviewManifest | None,
    graph_revision: int,
    graph_hash: str,
) -> bool:
    if manifest is None:
        return False
    if manifest.graph_revision > graph_revision:
        return True
    return (
        manifest.graph_revision == graph_revision
        and manifest.edit_graph_hash != graph_hash
    )


def _publish(
    cache: PreviewChunkCache,
    manifest: PreviewManifest,
    *,
    graph_revision: int,
    graph_hash: str,
) -> bool:
    current = cache.read_manifest()
    if _newer_manifest(current, graph_revision, graph_hash):
        return False
    cache.write_manifest(manifest.model_copy(update={"updated_at": time.time()}))
    return True


def _clear_job_id(
    cache: PreviewChunkCache,
    *,
    graph_revision: int,
    graph_hash: str,
) -> PreviewManifest | None:
    manifest = cache.read_manifest()
    if manifest is None or _newer_manifest(manifest, graph_revision, graph_hash):
        return manifest
    if manifest.graph_revision != graph_revision or manifest.edit_graph_hash != graph_hash:
        return manifest
    if manifest.job_id is not None:
        manifest = manifest.model_copy(
            update={"job_id": None, "updated_at": time.time()}
        )
        cache.write_manifest(manifest)
    return manifest


def _result(
    *,
    cache: PreviewChunkCache,
    manifest: PreviewManifest | None,
    failed_chunks: list[str],
    graph_changed: bool,
    partial: bool,
    error: str | None = None,
) -> dict[str, Any]:
    chunks = manifest.chunks if manifest is not None else []
    statuses = [effective_status(chunk) for chunk in chunks]
    green = statuses.count("green")
    yellow = statuses.count("yellow")
    red = statuses.count("red")
    result: dict[str, Any] = {
        "ok": error is None,
        "mode": "preview-chunks",
        "output_path": str(cache.manifest_path),
        "manifest_path": str(cache.manifest_path),
        "ready_chunks": green + yellow,
        "green_chunks": green,
        "yellow_chunks": yellow,
        "red_chunks": red,
        "failed_chunks": list(dict.fromkeys(failed_chunks)),
        "partial": partial,
        "graph_changed": graph_changed,
    }
    if error is not None:
        result["error"] = error
    return result


def render_preview_chunks(
    *,
    project_id: str,
    project_dir: Path,
    job_id: str,
    renderer: PreviewVideoRenderer | None = None,
    run_commands: Callable[[PreviewPipeCommands], None] | None = None,
) -> dict[str, Any]:
    """Bake requested dirty ranges and return manifest-oriented JSON."""

    project_dir = Path(project_dir).resolve()
    cache = _preview_cache(project_dir)
    temp_dir = cache.root / "tmp" / job_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    failed_chunks: list[str] = []
    graph_changed = False
    params: dict[str, Any] = {}
    captured_graph_revision: int | None = None
    captured_graph_hash: str | None = None
    try:
        params = _load_job_params(project_dir, job_id)
        requested_ranges, media, background = _parse_params(params)
        (
            store,
            operations,
            project,
            timeline,
            graph_revision,
            graph_hash,
        ) = _load_project_state(project_id, project_dir)
        captured_graph_revision = graph_revision
        captured_graph_hash = graph_hash
        previous = cache.read_manifest()
        if _newer_manifest(previous, graph_revision, graph_hash):
            return _result(
                cache=cache,
                manifest=previous,
                failed_chunks=[],
                graph_changed=True,
                partial=False,
            )
        old_timeline = _load_snapshot(
            store, previous, timeline, graph_hash,
        )
        fps_num, fps_den = _project_fps(project_dir, params)
        chunk_frames = _chunk_size(fps_num, fps_den, params)
        windows = make_chunk_windows(
            max(0, round(timeline.duration_sec * fps_num / fps_den)),
            fps_num,
            fps_den,
            chunk_frames=chunk_frames,
        )
        effective_chunk_frames = (
            windows[0].end_frame - windows[0].start_frame
            if windows else (chunk_frames or max(1, round(fps_num / fps_den)))
        )
        profile = preview_chunk_profile(fps_num, fps_den)
        encoder_backend = (
            str(params["encoder"])
            if params.get("encoder") is not None
            else None
        )
        profile_info = _profile_info(profile, encoder_backend)
        content_fingerprint = _content_fingerprint(
            project_dir,
            project,
            timeline,
        )
        fingerprint_operations = (
            operations
            if previous is None or previous.edit_graph_hash != graph_hash
            else []
        )
        fingerprints = compute_chunk_fingerprints(
            old_timeline=old_timeline,
            new_timeline=timeline,
            old_graph_hash=previous.edit_graph_hash if previous else None,
            new_graph_hash=graph_hash,
            operations=fingerprint_operations,
            windows=windows,
            profile_fingerprint=profile_info["fingerprint"],
            content_fingerprint=content_fingerprint,
        )
        active = _initial_manifest(
            cache=cache,
            previous=previous,
            project_id=project_id,
            graph_revision=graph_revision,
            graph_hash=graph_hash,
            timeline=timeline,
            windows=windows,
            fingerprints=fingerprints,
            profile_info=profile_info,
            fps_num=fps_num,
            fps_den=fps_den,
            chunk_frames=effective_chunk_frames,
            job_id=job_id,
        )
        if not _publish(
            cache,
            active,
            graph_revision=graph_revision,
            graph_hash=graph_hash,
        ):
            return _result(
                cache=cache,
                manifest=cache.read_manifest(),
                failed_chunks=[],
                graph_changed=True,
                partial=False,
            )

        selected = select_dirty_windows(
            _new_fingerprint_for_media(fingerprints, media),
            requested_ranges,
            background=background,
        )
        active_renderer = renderer or get_preview_video_renderer(project_dir)
        active_runner = run_commands or run_preview_pipe
        encoder = _resolve_encoder(
            profile,
            params,
            injected_runner=run_commands is not None,
        )
        melt_bin = shutil.which("melt") or "melt"
        for index in selected:
            _check_graph(store, graph_revision, graph_hash)
            _bake_chunk(
                cache=cache,
                active=active,
                chunk_index=index,
                window=windows[index],
                fingerprint=fingerprints[index],
                operations=operations,
                timeline=timeline,
                project_dir=project_dir,
                temp_dir=temp_dir,
                renderer=active_renderer,
                run_commands=active_runner,
                profile=profile,
                encoder=encoder,
                melt_bin=melt_bin,
                media=media,
                store=store,
                graph_revision=graph_revision,
                graph_hash=graph_hash,
                failed_chunks=failed_chunks,
            )
            _check_graph(store, graph_revision, graph_hash)
            active = active.model_copy(update={"job_id": job_id})
            if not _publish(
                cache,
                active,
                graph_revision=graph_revision,
                graph_hash=graph_hash,
            ):
                graph_changed = True
                break

        if not graph_changed:
            _clear_job_id(
                cache,
                graph_revision=graph_revision,
                graph_hash=graph_hash,
            )
            final_manifest = cache.read_manifest()
            if final_manifest is not None:
                cache.prune(final_manifest)
                final_manifest = cache.read_manifest() or final_manifest
            return _result(
                cache=cache,
                manifest=final_manifest,
                failed_chunks=failed_chunks,
                graph_changed=False,
                partial=bool(failed_chunks),
            )
    except _GraphChangedError:
        graph_changed = True
    except Exception as exc:
        final_manifest = cache.read_manifest()
        if (
            captured_graph_revision is not None
            and captured_graph_hash is not None
        ):
            _clear_job_id(
                cache,
                graph_revision=captured_graph_revision,
                graph_hash=captured_graph_hash,
            )
            final_manifest = cache.read_manifest() or final_manifest
        return _result(
            cache=cache,
            manifest=final_manifest,
            failed_chunks=failed_chunks,
            graph_changed=graph_changed,
            partial=bool(failed_chunks),
            error=str(exc),
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    final_manifest = cache.read_manifest()
    if (
        params
        and captured_graph_revision is not None
        and captured_graph_hash is not None
    ):
        _clear_job_id(
            cache,
            graph_revision=captured_graph_revision,
            graph_hash=captured_graph_hash,
        )
        final_manifest = cache.read_manifest() or final_manifest
    return _result(
        cache=cache,
        manifest=final_manifest,
        failed_chunks=failed_chunks,
        graph_changed=True,
        partial=bool(failed_chunks),
    )


__all__ = [
    "PreviewChunkWorkerError",
    "get_preview_video_renderer",
    "render_preview_chunks",
    "run_preview_pipe",
]
