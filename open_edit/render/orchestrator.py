"""Render orchestrator: plan → cache → emit → frame-server pipe → snapshot → result.

The main entry point: render_project(project_id, ...) -> RenderResult.
Composes the split render modules:

- ``timeline_plan.build_render_plan`` — asset paths, overlay clips, melt timeline
- ``pipe_builder.build_pipe_commands`` + ``melt_runner.run_pipe`` — single-pass render
- ``snapshot_recorder.record_snapshot`` — RenderSnapshotStore recording

Failure paths funnel through a single ``_fail`` helper producing the
structured RenderResult.
"""
from __future__ import annotations

import os
import shutil
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from open_edit.ir.types import Project
from open_edit.render.cache import RenderCache, canonical_json_hash, render_cache_key
from open_edit.render.diagnostics import (
    CANONICAL_STAGE_NAMES,
    LEGACY_STAGE_ALIASES,
    StageRecorder,
    product_descriptor,
)
from open_edit.render.emitter import EmitterConfig, emit_timeline
from open_edit.render.encoder import resolve_backend
from open_edit.render.materialize import RemotionMaterializeError, materialize_remotion_compositions
from open_edit.render.melt_runner import PipeRunError, run_pipe
from open_edit.render.pipe_builder import build_pipe_commands
from open_edit.render.profiles import (
    RenderProfile,
    profile_fingerprint,
    profile_with_quality,
    resolve_encoder_args,
)
from open_edit.render.remotion import resolve_alpha_mode
from open_edit.render.remotion.safety import render_reference_fingerprint
from open_edit.render.snapshot_recorder import record_snapshot
from open_edit.render.source_repair import (
    SOURCE_REPAIR_POLICY_VERSION,
    collect_source_baseline,
    repair_render_output,
)
from open_edit.render.timeline_plan import build_render_plan
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.storage.timeline_cache import derive_or_load_timeline


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
    diagnostics: dict = Field(default_factory=dict)
    error: Optional[str] = None


def _contractualize_diagnostics(
    mode: str,
    profile: RenderProfile,
    diagnostics: Optional[dict] = None,
) -> dict:
    """Normalize stage entries while retaining the pre-M0 names."""
    result = dict(diagnostics or {})
    recorder = StageRecorder()
    raw_stages = result.get("stages", {})
    if isinstance(raw_stages, Mapping):
        pending: dict[str, Mapping] = {}
        for name, raw_entry in raw_stages.items():
            if not isinstance(raw_entry, Mapping):
                continue
            canonical_name = LEGACY_STAGE_ALIASES.get(name, name)
            # Canonical entries win if a caller supplied both forms.
            if canonical_name not in pending or name == canonical_name:
                pending[canonical_name] = raw_entry
        for name, entry in pending.items():
            status = entry.get("status", "completed")
            fields = {
                key: value
                for key, value in entry.items()
                if key not in {"elapsed_sec", "status"}
            }
            recorder.record(
                name,
                entry.get("elapsed_sec", 0.0),
                status=status,
                **fields,
            )
    stages = recorder.stages
    for name in CANONICAL_STAGE_NAMES:
        if name not in stages:
            recorder.skip(name, reason="not_reached")
    stages = recorder.stages
    for alias, canonical in LEGACY_STAGE_ALIASES.items():
        if canonical in stages:
            stages[alias] = dict(stages[canonical])
    result["stages"] = stages
    result["legacy_stage_aliases"] = dict(LEGACY_STAGE_ALIASES)
    result["product"] = product_descriptor(mode, profile)
    return result


_gpu_decode_ok: bool | None = None


def _gpu_decode_available() -> bool:
    """True if melt can decode with hwaccel=cuda (probed once per process)."""
    global _gpu_decode_ok
    if _gpu_decode_ok is not None:
        return _gpu_decode_ok
    import shutil as _sh
    import subprocess as _sp

    melt_bin = _sh.which("melt")
    if melt_bin is None:
        _gpu_decode_ok = False
        return False
    clip_a = Path(__file__).resolve().parents[2] / "tests" / "testdata" / "raw_videos" / "clip_a.mp4"
    probe_mlt = ("<mlt><producer id='p0'><property name='resource'>"
                 f"{clip_a}</property>"
                 "<property name='hwaccel'>cuda</property>"
                 "<property name='hwaccel_device'>0</property></producer>"
                 "<playlist id='pl'><entry producer='p0'/></playlist>"
                 "<tractor id='t0'><track producer='pl'/></tractor></mlt>")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        mlt = Path(td) / "probe.mlt"
        mlt.write_text(probe_mlt)
        proc = _sp.run([melt_bin, str(mlt), "-consumer", "null",
                        "s=64x64", "frame_rate_num=30", "frame_rate_den=1"],
                       capture_output=True, text=True, timeout=60)
        _gpu_decode_ok = proc.returncode == 0
    return _gpu_decode_ok


def render_project(
    project_id: str,
    project_dir: Path,
    workdir: Path,
    mode: Literal["proxy", "final"] = "proxy",
    profile_name: Optional[str] = None,
    quality: Optional[str] = None,
    overrides: Optional[dict] = None,
    force: bool = False,
    nice_level: int = 10,
    encoder_backend: Optional[str] = None,
) -> RenderResult:
    """Render a project to an MP4.

    project_dir: directory containing `.open_edit/edit_graph.db`
    workdir: directory for the rendered MP4 (and the cache)

    If profile_name is None, the profile is auto-selected from mode:
    proxy -> fast_proxy (640x360), final -> 1080p30.
    """
    profile = profile_with_quality(profile_name, mode, quality, overrides)
    recorder = StageRecorder()
    melt_bin = shutil.which("melt")
    if melt_bin is None:
        return RenderResult(
            ok=False,
            profile=profile.model_dump(),
            mode=mode,
            error="melt not on PATH",
            diagnostics=_contractualize_diagnostics(
                mode, profile, {"stages": recorder.stages},
            ),
        )

    project_path = project_dir / ".open_edit" / "edit_graph.db"
    store = EditGraphStore(project_path)
    ops = store.load_all()
    applied_ops = [op for op in ops if op.status == "applied"]
    if not applied_ops:
        recorder.skip("derive_timeline", reason="empty_edit_graph")
        return RenderResult(
            ok=False,
            error="empty edit graph; nothing to render",
            profile=profile.model_dump(),
            mode=mode,
            diagnostics=_contractualize_diagnostics(
                mode, profile, {"stages": recorder.stages},
            ),
        )

    project = Project(name=project_id)
    project.edit_graph = list(applied_ops)
    derive_t0 = time.monotonic()
    try:
        timeline = derive_or_load_timeline(project, store, strict=True)
    except Exception as exc:
        recorder.record(
            "derive_timeline",
            time.monotonic() - derive_t0,
            status="failed",
            error=str(exc),
        )
        return _fail(
            mode=mode,
            profile=profile,
            output_path="",
            duration_sec=0.0,
            elapsed_sec=time.monotonic() - derive_t0,
            graph_hash="",
            error=str(exc),
            diagnostics={"stages": recorder.stages},
        )
    recorder.record(
        "derive_timeline",
        time.monotonic() - derive_t0,
        duration_sec=timeline.duration_sec,
    )

    # Materialize Remotion compositions to CAS clips before emit. Fail hard.
    materialize_t0 = time.monotonic()
    try:
        timeline = materialize_remotion_compositions(
            timeline, project_dir, mode=mode,
        )
    except RemotionMaterializeError as exc:
        materialize_elapsed = time.monotonic() - materialize_t0
        recorder.record(
            "remotion_materialize",
            materialize_elapsed,
            status="failed",
            bytes=0,
            error=str(exc),
        )
        return _fail(
            mode=mode, profile=profile, output_path="",
            duration_sec=timeline.duration_sec, elapsed_sec=0.0,
            graph_hash="", error=str(exc),
            diagnostics={"stages": recorder.stages},
        )
    materialize_elapsed = time.monotonic() - materialize_t0

    plan_t0 = time.monotonic()
    try:
        plan = build_render_plan(
            timeline,
            applied_ops,
            AssetStore(project_dir / ".open_edit" / "assets"),
            mode,
        )
    except Exception as exc:
        recorder.record(
            "remotion_materialize",
            materialize_elapsed,
            bytes=0,
        )
        recorder.record(
            "build_render_plan",
            time.monotonic() - plan_t0,
            status="failed",
            error=str(exc),
        )
        return _fail(
            mode=mode,
            profile=profile,
            output_path="",
            duration_sec=timeline.duration_sec,
            elapsed_sec=time.monotonic() - plan_t0,
            graph_hash="",
            error=str(exc),
            diagnostics={"stages": recorder.stages},
        )
    recorder.record("build_render_plan", time.monotonic() - plan_t0)
    source_baseline = collect_source_baseline(
        plan.melt_timeline, plan.asset_paths,
    )
    materialized_bytes = sum(
        ov.media_path.stat().st_size
        for ov in plan.overlay_clips
        if ov.media_path.is_file()
    )
    recorder.record(
        "remotion_materialize",
        materialize_elapsed,
        bytes=materialized_bytes,
    )
    diagnostics = {
        "stages": recorder.stages,
        "profile": {
            "name": profile.name,
            "width": profile.width,
            "height": profile.height,
            "quality": profile.quality or "fast",
            "audio_bitrate": profile.ab or ("320k" if mode == "final" else "96k"),
        },
        "source_baseline": source_baseline,
    }

    cache_lookup_t0 = time.monotonic()
    fingerprint = profile_fingerprint(profile, encoder_backend)
    payload = [op.model_dump(mode="json") for op in applied_ops]
    graph_hash = canonical_json_hash(payload)
    alpha_modes = sorted({
        resolve_alpha_mode() if composition.alpha else "opaque"
        for composition in timeline.remotion_compositions
    })
    content_fingerprint = render_reference_fingerprint(
        project_dir, timeline.remotion_compositions,
        alpha_mode=",".join(alpha_modes) or "opaque",
    )
    diagnostics["content_fingerprint"] = content_fingerprint
    diagnostics["alpha_mode"] = ",".join(alpha_modes) or "opaque"
    diagnostics["profile"].update({
        "fingerprint": fingerprint,
        "encoder_backend": resolve_backend(encoder_backend),
    })

    cache = RenderCache(workdir / "render_cache")
    # Source repair runs after overlays are burned. Include its policy version
    # so a corrected overlay-protection rule cannot serve an older proxy.
    cache_content_fingerprint = (
        f"{content_fingerprint}|{SOURCE_REPAIR_POLICY_VERSION}"
    )
    cache_key = render_cache_key(
        graph_hash, fingerprint, cache_content_fingerprint,
    )
    if force:
        cached = None
        recorder.skip("render_cache_lookup", reason="force_requested")
    else:
        cached = cache.get(cache_key)
        cache_hit = bool(cached and cache.is_fresh(cached))
        recorder.record(
            "render_cache_lookup",
            time.monotonic() - cache_lookup_t0,
            hit=cache_hit,
        )
        if cache_hit:
            diagnostics["stages"] = recorder.stages
            return RenderResult(
                ok=True, output_path=str(cached), mode=mode,
                profile=profile.model_dump(), duration_sec=timeline.duration_sec,
                elapsed_sec=0.0, cache_hit=True, edit_graph_hash=graph_hash,
                diagnostics=_contractualize_diagnostics(
                    mode,
                    profile,
                    {**diagnostics, "cache": {"hit": True}},
                ),
            )

    config = EmitterConfig(profile=profile.model_dump())
    hwaccel_on = _gpu_decode_available() and resolve_backend(encoder_backend) == "gpu"
    workdir.mkdir(parents=True, exist_ok=True)
    xml_path = workdir / f"project_{graph_hash[:12]}.mlt"
    emit_t0 = time.monotonic()
    try:
        xml = emit_timeline(
            plan.melt_timeline,
            config,
            asset_paths=plan.asset_paths,
            hwaccel=hwaccel_on,
        )
        xml_path.write_text(xml)
    except Exception as exc:
        recorder.record(
            "emit_mlt",
            time.monotonic() - emit_t0,
            status="failed",
            error=str(exc),
        )
        diagnostics["stages"] = recorder.stages
        return _fail(
            mode=mode,
            profile=profile,
            output_path=str(xml_path),
            duration_sec=timeline.duration_sec,
            elapsed_sec=time.monotonic() - emit_t0,
            graph_hash=graph_hash,
            error=str(exc),
            diagnostics=diagnostics,
        )
    recorder.record(
        "emit_mlt",
        time.monotonic() - emit_t0,
        bytes=xml_path.stat().st_size,
    )
    output_mp4 = workdir / f"project_{graph_hash[:12]}.mp4"

    spec = resolve_encoder_args(profile, encoder_backend)
    audio_bitrate = profile.ab or ("320k" if mode == "final" else "96k")
    cmds = build_pipe_commands(
        melt_bin, xml_path, output_mp4, profile, spec, plan.overlay_clips,
        audio_bitrate=audio_bitrate, workdir=workdir,
    )
    # Proxy used to hard-cap at 600s, which killed long encodes before moov
    # was written (unreadable MP4). Scale with timeline length; keep a floor.
    melt_timeout = 7200 if mode == "final" else max(600, int(timeline.duration_sec * 3) + 120)
    t0 = time.monotonic()
    try:
        result = run_pipe(cmds, timeout_s=melt_timeout)
    except PipeRunError as exc:
        recorder.record(
            "melt_audio",
            0.0,
            status="failed",
            error=str(exc),
        )
        recorder.skip("melt_video", reason="pipe_failed")
        recorder.skip("ffmpeg_encode", reason="pipe_failed")
        recorder.skip("source_repair", reason="render_pipe_failed")
        diagnostics["pipe_elapsed_sec"] = time.monotonic() - t0
        diagnostics["stages"] = recorder.stages
        return _fail(
            mode=mode, profile=profile, output_path=str(output_mp4),
            duration_sec=timeline.duration_sec, elapsed_sec=time.monotonic() - t0,
            graph_hash=graph_hash, error=str(exc),
            project_dir=project_dir, project_id=project_id, record_failed_snapshot=True,
            diagnostics=diagnostics,
        )
    # hwaccel retry: melt failed with hwaccel XML -> re-emit without + retry once
    if result.returncode != 0 and hwaccel_on and result.melt_rc != 0:
        xml_cpu = emit_timeline(
            plan.melt_timeline, config, asset_paths=plan.asset_paths, hwaccel=False,
        )
        xml_path.write_text(xml_cpu)
        try:
            result = run_pipe(cmds, timeout_s=melt_timeout)
        except PipeRunError as exc:
            recorder.record(
                "melt_audio",
                0.0,
                status="failed",
                error=str(exc),
            )
            recorder.skip("melt_video", reason="pipe_failed")
            recorder.skip("ffmpeg_encode", reason="pipe_failed")
            recorder.skip("source_repair", reason="render_pipe_failed")
            diagnostics["pipe_elapsed_sec"] = time.monotonic() - t0
            diagnostics["stages"] = recorder.stages
            return _fail(
                mode=mode, profile=profile, output_path=str(output_mp4),
                duration_sec=timeline.duration_sec, elapsed_sec=time.monotonic() - t0,
                graph_hash=graph_hash, error=str(exc),
                project_dir=project_dir, project_id=project_id, record_failed_snapshot=True,
                diagnostics=diagnostics,
            )
    elapsed = time.monotonic() - t0
    if result.returncode == 0 and output_mp4.is_file() and output_mp4.stat().st_size > 0:
        repair_t0 = time.monotonic()
        repair_path = output_mp4.with_name(f"{output_mp4.stem}.repaired.mp4")
        try:
            repair = repair_render_output(
                output_mp4,
                repair_path,
                source_baseline,
                protected_spans=[
                    (
                        overlay.position_sec,
                        overlay.position_sec + overlay.duration_sec,
                    )
                    for overlay in plan.overlay_clips
                ],
                repair_intentional_black=(
                    os.environ.get("OPEN_EDIT_REPAIR_INTENTIONAL_BLACK", "0")
                    .strip().lower() not in {"0", "false", "no"}
                ),
            )
        except Exception as exc:
            repair = {"ok": False, "changed": False, "error": str(exc)}
        if repair.get("ok") and repair.get("changed"):
            os.replace(repair_path, output_mp4)
        repair_elapsed = time.monotonic() - repair_t0
        diagnostics["repair"] = {
            key: value
            for key, value in repair.items()
            if key not in {"output_path"}
        }
        diagnostics["repair"]["elapsed_sec"] = repair_elapsed
        recorder.record(
            "source_repair",
            repair_elapsed,
            status="completed" if repair.get("ok") else "failed",
            changed=bool(repair.get("changed")),
        )
    else:
        recorder.skip("source_repair", reason="render_output_unavailable")
    elapsed = time.monotonic() - t0
    diagnostics["pipe_elapsed_sec"] = getattr(result, "elapsed_sec", elapsed)
    audio_bytes = cmds.audio_wav.stat().st_size if cmds.audio_wav.is_file() else 0
    output_bytes = output_mp4.stat().st_size if output_mp4.is_file() else 0
    melt_rc = int(getattr(result, "melt_rc", 0))
    ffmpeg_rc = int(getattr(result, "ffmpeg_rc", 0))
    recorder.record(
        "melt_audio",
        getattr(result, "audio_elapsed_sec", 0.0),
        status="failed" if ffmpeg_rc == -1 else "completed",
        bytes=audio_bytes,
        returncode=(melt_rc if ffmpeg_rc == -1 else 0),
    )
    if ffmpeg_rc == -1:
        recorder.skip("melt_video", reason="audio_pass_failed")
        recorder.skip("ffmpeg_encode", reason="audio_pass_failed")
    else:
        recorder.record(
            "melt_video",
            getattr(result, "melt_elapsed_sec", 0.0),
            status="completed" if melt_rc == 0 else "failed",
            bytes=xml_path.stat().st_size,
            returncode=melt_rc,
        )
        recorder.record(
            "ffmpeg_encode",
            getattr(result, "ffmpeg_elapsed_sec", 0.0),
            status="completed" if ffmpeg_rc == 0 else "failed",
            bytes=output_bytes,
            returncode=ffmpeg_rc,
        )
    diagnostics["stages"] = recorder.stages
    diagnostics["elapsed_sec"] = elapsed

    if result.returncode != 0 or not output_mp4.is_file() or output_mp4.stat().st_size == 0:
        return _fail(
            mode=mode, profile=profile, output_path=str(output_mp4),
            duration_sec=timeline.duration_sec, elapsed_sec=elapsed,
            graph_hash=graph_hash,
            error=(result.stderr or f"render pipe exited {result.returncode}"),
            project_dir=project_dir, project_id=project_id, record_failed_snapshot=True,
            diagnostics=diagnostics,
        )

    cache.put(cache_key, output_mp4)
    record_snapshot(project_dir, project_id, graph_hash, output_mp4, success=True)
    return RenderResult(
        ok=True, output_path=str(output_mp4), mode=mode,
        profile=profile.model_dump(), duration_sec=timeline.duration_sec,
        elapsed_sec=elapsed, cache_hit=False, edit_graph_hash=graph_hash,
        diagnostics=_contractualize_diagnostics(mode, profile, diagnostics),
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
    diagnostics: Optional[dict] = None,
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
    diagnostics = _contractualize_diagnostics(mode, profile, diagnostics)
    return RenderResult(
        ok=False, output_path=output_path, mode=mode,
        profile=profile.model_dump(), duration_sec=duration_sec,
        elapsed_sec=elapsed_sec, edit_graph_hash=graph_hash, error=error,
        diagnostics=diagnostics or {},
    )
