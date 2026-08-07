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

import dataclasses
import logging
import math
import os
import shutil
import subprocess
import time
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

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
from open_edit.render.materialize import (
    MaterializeReport,
    RemotionMaterializeError,
    build_materialization_manifest,
    materialization_manifest_path,
    materialize_remotion_compositions,
)
from open_edit.render.hyperframes import (
    HyperFramesRenderError,
    hyperframes_reference_fingerprint,
    materialize_hyperframes_overlays,
)
from open_edit.render.melt_runner import PipeRunError, run_pipe
from open_edit.render.cuda_fastpath import (
    run_cuda_fastpath,
    timeline_supports_cuda_fastpath,
)
from open_edit.render.pipe_builder import OverlayClip, build_pipe_commands
from open_edit.render.profiles import (
    RenderProfile,
    profile_fingerprint,
    profile_with_quality,
    resolve_encoder_args,
)
from open_edit.render.remotion import resolve_alpha_mode
from open_edit.render.remotion.dirty import write_manifest_atomic
from open_edit.render.remotion.frame_feeder import (
    build_frame_pull_clients,
    probe_frame_pull_host,
)
from open_edit.render.remotion.safety import render_reference_fingerprint
from open_edit.render.snapshot_recorder import record_snapshot
from open_edit.render.source_proxy import DEFAULT_SOURCE_PROXY_PROFILE
from open_edit.render.source_repair import (
    SOURCE_REPAIR_POLICY_VERSION,
    collect_source_baseline,
    repair_render_output,
)
from open_edit.render.timeline_plan import (
    EmissionProfile,
    build_render_plan,
    source_media_policy_for,
)
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


def _cuda_result_to_pipe_result(result: object) -> object:
    """Adapt a successful CUDA fast-path result to the PipeResult surface."""
    from open_edit.render.melt_runner import PipeResult

    return PipeResult(
        returncode=0,
        melt_rc=0,
        ffmpeg_rc=0,
        stderr="",
        elapsed_sec=float(getattr(result, "elapsed_sec", 0.0)),
        audio_elapsed_sec=float(getattr(result, "audio_elapsed_sec", 0.0)),
        melt_elapsed_sec=0.0,
        ffmpeg_elapsed_sec=float(getattr(result, "elapsed_sec", 0.0)),
        frames_requested=0,
    )


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def encode_audio_aac_cache(
    wav_path: Path,
    aac_path: Path,
    bitrate: str = "96k",
    timeout_s: float = 600.0,
) -> bool:
    """Encode a wav mix to AAC (fast coder) and cache it under ``aac_path``.

    Returns True when ``aac_path`` is a usable file afterwards. The audio mix
    depends only on the edit-graph hash, so the encode runs once per graph and
    every later render muxes it with ``-c:a copy`` (~40s -> ~3s per render).
    """
    try:
        if aac_path.is_file() and aac_path.stat().st_size > 0:
            return True
        if not wav_path.is_file():
            return False
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(wav_path),
                "-c:a", "aac", "-aac_coder", "fast", "-b:a", bitrate,
                str(aac_path),
            ],
            capture_output=True, text=True, timeout=timeout_s,
        )
        if proc.returncode != 0 or not aac_path.is_file():
            return False
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _bounded_error(value: object, limit: int = 512) -> str:
    return str(value).replace("\x00", " ").replace("\r", " ").replace("\n", " ")[:limit]


def _repair_budget(mode: str, duration_sec: float | None) -> dict[str, object]:
    """Resolve the detector budget without coupling M1 to Task 4 imports."""
    def env_float(name: str, fallback: float | None) -> float | None:
        raw = os.environ.get(name)
        if raw is None:
            return fallback
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return fallback
        if not math.isfinite(value) or value <= 0.0:
            return fallback
        return value

    blackdetect_max = env_float(
        "OPEN_EDIT_QC_BLACKDETECT_MAX_SEC", 900.0,
    )
    total_budget = (
        env_float("OPEN_EDIT_FINAL_QC_BUDGET_SEC", 900.0)
        if mode == "final" else None
    )
    qc_mode = "full" if mode == "final" else "light"
    timeout: float

    # Task 4 supplies the canonical policy resolver. The fallback keeps this
    # lane usable while Task 4 is developed in parallel and mirrors its
    # duration-aware blackdetect calculation.
    try:
        from open_edit.qc.policy import resolve_qc_policy
    except (ImportError, AttributeError):
        resolve_qc_policy = None
    if resolve_qc_policy is not None:
        try:
            policy = resolve_qc_policy(mode, cache_hit=False)
            qc_mode = str(getattr(policy, "mode", qc_mode))
            policy_max = getattr(policy, "blackdetect_max_sec", blackdetect_max)
            if policy_max is not None:
                blackdetect_max = float(policy_max)
            policy_total = getattr(policy, "total_budget_sec", total_budget)
            total_budget = (
                float(policy_total) if policy_total is not None else None
            )
            timeout = float(policy.blackdetect_timeout(duration_sec))
        except (AttributeError, TypeError, ValueError, RuntimeError):
            timeout = 0.0
    else:
        timeout = 0.0

    if timeout <= 0.0 or not math.isfinite(timeout):
        if duration_sec is None or duration_sec <= 0.0:
            timeout = min(60.0, blackdetect_max or 60.0)
        else:
            timeout = max(
                60.0,
                min(blackdetect_max or 60.0, duration_sec * 0.75),
            )
    if total_budget is not None:
        timeout = min(timeout, total_budget)
    timeout = max(0.001, timeout)
    return {
        "qc_policy": qc_mode,
        "total_budget_sec": total_budget,
        "blackdetect_max_sec": blackdetect_max,
        "remaining_budget_sec": timeout,
        "detector_timeout_s": timeout,
    }


def frame_pull_gate(
    mode: str,
    project_path: Path,
    *,
    has_compositions: bool,
) -> dict[str, object]:
    """Resolve the experimental frame-pull gate without changing defaults."""
    requested_engine = os.environ.get(
        "OPEN_EDIT_REMOTION_FRAME_ENGINE",
        "materialize",
    ).strip().lower()
    diagnostics: dict[str, object] = {
        "requested": requested_engine == "pull",
        "requested_engine": requested_engine,
        "enabled": False,
        "frames_requested": 0,
        "elapsed_sec": 0.0,
        "fallback": None,
    }
    if requested_engine == "materialize" or not has_compositions:
        return diagnostics
    if requested_engine != "pull":
        diagnostics.update({
            "error_code": "remotion_frame_pull_invalid_engine",
            "error": _bounded_error(
                "OPEN_EDIT_REMOTION_FRAME_ENGINE must be materialize or pull"
            ),
        })
        return diagnostics
    if mode != "proxy" and not _env_truthy(
        "OPEN_EDIT_ALLOW_EXPERIMENTAL_FRAME_PULL"
    ):
        diagnostics.update({
            "fallback": "materialize",
            "error_code": "remotion_frame_pull_mode_blocked",
            "error": "final export requires OPEN_EDIT_ALLOW_EXPERIMENTAL_FRAME_PULL=1",
        })
        return diagnostics
    try:
        host_ok, host_error = probe_frame_pull_host(project_path)
    except Exception as exc:
        host_ok, host_error = False, _bounded_error(exc)
    if not host_ok:
        diagnostics.update({
            "fallback": "materialize",
            "error_code": "remotion_frame_pull_unavailable",
            "error": _bounded_error(host_error or "frame pull host probe failed"),
        })
        return diagnostics
    diagnostics["enabled"] = True
    return diagnostics


def _frame_pull_fallback_requested() -> bool:
    return (
        os.environ.get("OPEN_EDIT_FRAME_PULL_FALLBACK", "")
        .strip()
        .lower()
        == "materialize"
    )


def _gpu_decode_available() -> bool:
    """True if melt can actually decode with hwaccel=cuda (probed once).

    The probe proves CUDA engages rather than silently falling back to CPU:
    the same short clip is decoded with and without ``hwaccel=cuda``; CUDA is
    only reported available when the CUDA run completes AND is meaningfully
    faster than the CPU run. Without the timing comparison, a missing/broken
    CUDA path would pass the probe via melt's silent CPU fallback.
    """
    global _gpu_decode_ok
    if _gpu_decode_ok is not None:
        return _gpu_decode_ok
    import shutil as _sh
    import subprocess as _sp
    import time as _time

    melt_bin = _sh.which("melt")
    if melt_bin is None:
        _gpu_decode_ok = False
        return False
    clip_a = Path(__file__).resolve().parents[2] / "tests" / "testdata" / "raw_videos" / "clip_a.mp4"
    if not clip_a.is_file():
        _gpu_decode_ok = False
        return False
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

        def _run_cuda(enabled: bool) -> tuple[int, float]:
            xml = mlt if enabled else None
            args = (
                [melt_bin, str(mlt)]
                if enabled
                else [melt_bin, str(clip_a)]
            )
            args += ["-consumer", "null", "s=256x256",
                     "frame_rate_num=30", "frame_rate_den=1"]
            t0 = _time.monotonic()
            try:
                proc = _sp.run(args, capture_output=True, text=True, timeout=60)
            except (OSError, _sp.TimeoutExpired):
                return 1, 0.0
            return proc.returncode, _time.monotonic() - t0

        rc_cuda, t_cuda = _run_cuda(True)
        if rc_cuda != 0:
            _gpu_decode_ok = False
            return False
        # Only run the CPU comparison when CUDA succeeded; a broken CUDA
        # path that fell back to CPU would otherwise be reported as working.
        _rc_cpu, t_cpu = _run_cuda(False)
        _gpu_decode_ok = t_cuda > 0 and t_cuda < max(0.7, t_cpu * 0.6)
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
    force_remotion: bool = False,
    remotion_uids: Collection[str] = (),
    nice_level: int = 10,
    encoder_backend: Optional[str] = None,
    emission_profile: EmissionProfile | None = None,
) -> RenderResult:
    """Render a project to an MP4.

    project_dir: directory containing `.open_edit/edit_graph.db`
    workdir: directory for the rendered MP4 (and the cache)

    If profile_name is None, the profile is auto-selected from mode:
    proxy -> fast_proxy (640x360), final -> 1080p30.
    """
    requested_emission_profile: EmissionProfile = (
        emission_profile
        or ("final" if mode == "final" else "review-artifact")
    )
    source_media_policy = source_media_policy_for(requested_emission_profile)
    if mode == "final" and source_media_policy != "original":
        raise ValueError(
            "final emission requires the original source-media policy"
        )

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
    frame_pull = frame_pull_gate(
        mode,
        project_dir,
        has_compositions=bool(timeline.remotion_compositions),
    )

    cache_lookup_t0 = time.monotonic()
    fingerprint = profile_fingerprint(profile, encoder_backend)
    source_proxy_profile_fingerprint = (
        DEFAULT_SOURCE_PROXY_PROFILE.fingerprint()
        if source_media_policy == "proxy"
        else ""
    )
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
    hyperframes_fingerprint = hyperframes_reference_fingerprint(
        timeline,
        project_dir,
        mode=mode,
        width=profile.width,
        height=profile.height,
        fps=profile.frame_rate_num / max(profile.frame_rate_den, 1),
    )
    content_fingerprint = f"{content_fingerprint}|hyperframes={hyperframes_fingerprint}"
    diagnostics = {
        "stages": recorder.stages,
        "profile": {
            "name": profile.name,
            "width": profile.width,
            "height": profile.height,
            "quality": profile.quality or "fast",
            "audio_bitrate": profile.ab or ("320k" if mode == "final" else "96k"),
            "fingerprint": fingerprint,
            "encoder_backend": resolve_backend(encoder_backend),
        },
        "content_fingerprint": content_fingerprint,
        "alpha_mode": ",".join(alpha_modes) or "opaque",
        "remotion_frame_pull": frame_pull,
        "emission_profile": requested_emission_profile,
        "source_media_policy": source_media_policy,
        "emission_profile_fingerprint": (
            source_proxy_profile_fingerprint or requested_emission_profile
        ),
        "source_proxy_profile_fingerprint": source_proxy_profile_fingerprint or None,
        "source_proxy_hits": {},
        "source_proxy_fallbacks": {},
        "decode_backend": (
            "cuda" if _gpu_decode_available() and resolve_backend(encoder_backend) == "gpu" else "cpu"
        ),
    }
    whole_file_repair = requested_emission_profile in {
        "final", "review-artifact",
    }
    # Previews (review-artifact / proxy) skip the repair machinery entirely:
    # the black/frozen detectors + re-encode are a deliverable-QC concern, and
    # even verify-only detection costs minutes on a 37-min source. Deliverables
    # (final) keep full repair. OPEN_EDIT_REPAIR=1 re-enables detect+re-encode
    # on previews; OPEN_EDIT_REPAIR_DETECT=1 runs detection-only (report only).
    repair_reencode = whole_file_repair and (
        requested_emission_profile == "final"
        or _env_truthy("OPEN_EDIT_REPAIR")
    )
    repair_detect = whole_file_repair and (
        requested_emission_profile == "final"
        or _env_truthy("OPEN_EDIT_REPAIR")
        or _env_truthy("OPEN_EDIT_REPAIR_DETECT")
    )
    repair_intentional_black = _env_truthy(
        "OPEN_EDIT_REPAIR_INTENTIONAL_BLACK",
    )
    repair_budget = (
        _repair_budget(mode, timeline.duration_sec)
        if whole_file_repair else {}
    )
    diagnostics["repair_policy"] = {
        "version": SOURCE_REPAIR_POLICY_VERSION,
        "emission_profile": requested_emission_profile,
        "source_media_policy": source_media_policy,
        "enabled": whole_file_repair,
        "reencode": repair_reencode,
        "detect": repair_detect,
        "executed": False,
        "repair_source_black": True,
        "repair_source_frozen": False,
        "repair_intentional_black": repair_intentional_black,
        "skip_if_no_source_defects": True,
        "reason": (
            "whole_file_emission"
            if whole_file_repair else "emission_profile_not_whole_file"
        ),
        **repair_budget,
    }
    if mode == "final":
        # Final QC is attached by the host job/CLI after this whole-file
        # render; keep its required policy explicit in render diagnostics.
        diagnostics["qc_policy"] = "full"
        diagnostics["final_qc_required"] = True

    cache = RenderCache(workdir / "render_cache")
    # Source repair runs after overlays are burned. Include its policy version
    # so a corrected overlay-protection rule cannot serve an older proxy.
    cache_content_fingerprint = (
        f"{content_fingerprint}|{SOURCE_REPAIR_POLICY_VERSION}"
    )
    if source_proxy_profile_fingerprint:
        cache_content_fingerprint = (
            f"{cache_content_fingerprint}|emission={requested_emission_profile}"
            f"|source_proxy={source_proxy_profile_fingerprint}"
        )
    diagnostics["cache_content_fingerprint"] = cache_content_fingerprint
    cache_key = render_cache_key(
        graph_hash, fingerprint, cache_content_fingerprint,
    )
    remotion_invalidation_requested = force_remotion or bool(remotion_uids)
    if force or remotion_invalidation_requested:
        cached = None
        reason = "force_requested" if force else "force_remotion_requested"
        recorder.skip("render_cache_lookup", reason=reason)
    else:
        cached = cache.get(cache_key)
        cache_hit = bool(cached and cache.is_fresh(cached))
        recorder.record(
            "render_cache_lookup",
            time.monotonic() - cache_lookup_t0,
            hit=cache_hit,
        )
        if cache_hit:
            recorder.skip("remotion_materialize", reason="deliverable_cache_hit")
            frame_pull["enabled"] = False
            if frame_pull.get("requested"):
                frame_pull["fallback"] = "deliverable_cache_hit"
            diagnostics["repair_policy"]["reason"] = "deliverable_cache_hit"
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

    diagnostics["cache"] = {"hit": False}
    unmaterialized_timeline = timeline
    hyperframes_result = None
    if timeline.overlays:
        hyperframes_t0 = time.monotonic()
        try:
            hyperframes_result = materialize_hyperframes_overlays(
                timeline,
                project_dir,
                mode=mode,
                width=profile.width,
                height=profile.height,
                fps=profile.frame_rate_num / max(profile.frame_rate_den, 1),
            )
            recorder.record(
                "hyperframes_materialize",
                time.monotonic() - hyperframes_t0,
                cache_hit=bool(hyperframes_result and hyperframes_result.cache_hit),
                content_hash=hyperframes_result.content_hash if hyperframes_result else "",
            )
            diagnostics["hyperframes"] = {
                "output_path": str(hyperframes_result.output_path) if hyperframes_result else "",
                "cache_hit": bool(hyperframes_result and hyperframes_result.cache_hit),
                "content_hash": hyperframes_result.content_hash if hyperframes_result else "",
            }
        except HyperFramesRenderError as exc:
            recorder.record(
                "hyperframes_materialize",
                time.monotonic() - hyperframes_t0,
                status="failed",
                error=str(exc),
            )
            diagnostics["stages"] = recorder.stages
            return _fail(
                mode=mode,
                profile=profile,
                output_path="",
                duration_sec=timeline.duration_sec,
                elapsed_sec=time.monotonic() - hyperframes_t0,
                graph_hash=graph_hash,
                error=str(exc),
                diagnostics=diagnostics,
            )
    else:
        recorder.skip("hyperframes_materialize", reason="no_html_overlays")
    manifest_path = materialization_manifest_path(
        project_dir, mode, fingerprint,
    )
    materialize_report = MaterializeReport()
    frame_pull_enabled = bool(frame_pull.get("enabled"))
    if frame_pull_enabled:
        materialize_elapsed = 0.0
        recorder.skip("remotion_materialize", reason="frame_pull_enabled")
    else:
        # Materialize Remotion compositions to CAS clips only after the
        # whole-file deliverable cache has missed. Fail hard on any miss.
        materialize_t0 = time.monotonic()
        try:
            timeline = materialize_remotion_compositions(
                timeline,
                project_dir,
                mode=mode,
                manifest_path=manifest_path,
                force_remotion=force_remotion,
                force_uids=remotion_uids,
                report=materialize_report,
                profile_fingerprint=fingerprint,
            )
        except RemotionMaterializeError as exc:
            materialize_elapsed = time.monotonic() - materialize_t0
            recorder.record(
                "remotion_materialize",
                materialize_elapsed,
                status="failed",
                bytes=0,
                error=str(exc),
                worker_count=materialize_report.worker_count,
                cache_hits=materialize_report.cache_hits,
                cache_misses=materialize_report.cache_misses,
                reused_manifest_entries=materialize_report.reused_manifest_entries,
                rendered_uids=materialize_report.rendered_uids,
                dirty_uids=materialize_report.dirty_uids,
            )
            diagnostics["stages"] = recorder.stages
            return _fail(
                mode=mode, profile=profile, output_path="",
                duration_sec=timeline.duration_sec, elapsed_sec=0.0,
                graph_hash=graph_hash, error=str(exc),
                diagnostics=diagnostics,
            )
        materialize_elapsed = time.monotonic() - materialize_t0

    plan_t0 = time.monotonic()
    try:
        plan = build_render_plan(
            timeline,
            applied_ops,
            AssetStore(project_dir / ".open_edit" / "assets"),
            mode,
            frame_engine="pull" if frame_pull_enabled else "materialize",
            frame_profile=profile,
            emission_profile=requested_emission_profile,
        )
    except Exception as exc:
        if not frame_pull_enabled:
            recorder.record(
                "remotion_materialize",
                materialize_elapsed,
                bytes=0,
                worker_count=materialize_report.worker_count,
                cache_hits=materialize_report.cache_hits,
                cache_misses=materialize_report.cache_misses,
                reused_manifest_entries=materialize_report.reused_manifest_entries,
                rendered_uids=materialize_report.rendered_uids,
                dirty_uids=materialize_report.dirty_uids,
            )
        recorder.record(
            "build_render_plan",
            time.monotonic() - plan_t0,
            status="failed",
            error=str(exc),
        )
        diagnostics["stages"] = recorder.stages
        return _fail(
            mode=mode,
            profile=profile,
            output_path="",
            duration_sec=timeline.duration_sec,
            elapsed_sec=time.monotonic() - plan_t0,
            graph_hash=graph_hash,
            error=str(exc),
            diagnostics=diagnostics,
        )
    if hyperframes_result is not None:
        plan.overlay_clips.append(OverlayClip(
            position_sec=0.0,
            duration_sec=timeline.duration_sec,
            media_path=hyperframes_result.output_path,
            label="hyperframes",
            alpha=True,
        ))
        plan.overlay_clips.sort(key=lambda overlay: overlay.position_sec)
    recorder.record("build_render_plan", time.monotonic() - plan_t0)
    diagnostics["emission_profile"] = plan.emission_profile
    diagnostics["source_media_policy"] = plan.source_media_policy
    diagnostics["source_proxy_hits"] = dict(plan.source_proxy_hits)
    diagnostics["source_proxy_fallbacks"] = dict(plan.source_proxy_fallbacks)
    if whole_file_repair and repair_detect:
        source_baseline = collect_source_baseline(
            plan.melt_timeline, plan.asset_paths,
            cache_dir=workdir / "render_cache",
        )
    else:
        source_baseline = {
            "version": 1,
            "source_hashes": {},
            "black_frames": [],
            "frozen_frames": [],
            "errors": [],
            "reason": (
                "emission_profile_not_whole_file"
                if not whole_file_repair
                else "repair_detect_disabled_for_preview"
            ),
        }
    materialized_bytes = sum(
        getattr(ov, "media_path").stat().st_size
        for ov in plan.overlay_clips
        if getattr(ov, "media_path", None) is not None
        and getattr(ov, "media_path").is_file()
    )
    if not frame_pull_enabled:
        recorder.record(
            "remotion_materialize",
            materialize_elapsed,
            bytes=materialized_bytes,
            worker_count=materialize_report.worker_count,
            cache_hits=materialize_report.cache_hits,
            cache_misses=materialize_report.cache_misses,
            reused_manifest_entries=materialize_report.reused_manifest_entries,
            rendered_uids=materialize_report.rendered_uids,
            dirty_uids=materialize_report.dirty_uids,
        )
    diagnostics["source_baseline"] = source_baseline

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
        frame_engine="pull" if frame_pull_enabled else "materialize",
    )
    # Proxy used to hard-cap at 600s, which killed long encodes before moov
    # was written (unreadable MP4). Scale with timeline length; keep a floor.
    melt_timeout = 7200 if mode == "final" else max(600, int(timeline.duration_sec * 3) + 120)

    # Audio mix cache: the wav depends only on the edit graph, so identical
    # re-renders (or proxy-after-final) reuse it instead of re-running the
    # 15-20s melt-audio pass.
    audio_cache_dir = workdir / "render_cache" / "audio"
    audio_cache_dir.mkdir(parents=True, exist_ok=True)
    audio_cache_path = audio_cache_dir / f"{graph_hash}.wav"

    def _switch_to_materialize() -> None:
        nonlocal cmds, frame_pull_enabled, materialize_elapsed
        nonlocal plan, source_baseline, timeline
        if not frame_pull_enabled:
            return
        frame_pull_enabled = False
        frame_pull["enabled"] = False
        frame_pull["fallback"] = "materialize"
        fallback_t0 = time.monotonic()
        materialize_t0 = fallback_t0
        try:
            timeline = materialize_remotion_compositions(
                unmaterialized_timeline,
                project_dir,
                mode=mode,
                manifest_path=manifest_path,
                force_remotion=force_remotion,
                force_uids=remotion_uids,
                report=materialize_report,
                profile_fingerprint=fingerprint,
            )
        except Exception as exc:
            frame_pull["fallback_error"] = _bounded_error(exc)
            raise
        materialize_elapsed = time.monotonic() - materialize_t0
        recorder.record(
            "remotion_materialize",
            materialize_elapsed,
            bytes=0,
            worker_count=materialize_report.worker_count,
            cache_hits=materialize_report.cache_hits,
            cache_misses=materialize_report.cache_misses,
            reused_manifest_entries=materialize_report.reused_manifest_entries,
            rendered_uids=materialize_report.rendered_uids,
            dirty_uids=materialize_report.dirty_uids,
        )
        plan = build_render_plan(
            timeline,
            applied_ops,
            AssetStore(project_dir / ".open_edit" / "assets"),
            mode,
            frame_engine="materialize",
            frame_profile=profile,
            emission_profile=requested_emission_profile,
        )
        if whole_file_repair:
            source_baseline = collect_source_baseline(
                plan.melt_timeline,
                plan.asset_paths,
                cache_dir=workdir / "render_cache",
            )
        else:
            source_baseline = {
                "version": 1,
                "source_hashes": {},
                "black_frames": [],
                "frozen_frames": [],
                "errors": [],
                "reason": "emission_profile_not_whole_file",
            }
        cmds = build_pipe_commands(
            melt_bin,
            xml_path,
            output_mp4,
            profile,
            spec,
            plan.overlay_clips,
            audio_bitrate=audio_bitrate,
            workdir=workdir,
            frame_engine="materialize",
        )
        frame_pull["fallback_elapsed_sec"] = time.monotonic() - fallback_t0

    def _run_render_pipe():
        # ---- Audio mix cache: skip melt-audio when an identical graph's mix
        # ---- already exists (the wav depends only on the edit graph).
        wav_hit = audio_cache_path.is_file() and audio_cache_path.stat().st_size > 0
        melt_audio_cmd = cmds.melt_audio_cmd
        if wav_hit:
            try:
                shutil.copyfile(audio_cache_path, cmds.audio_wav)
                melt_audio_cmd = []
                diagnostics.setdefault("audio_cache", {})["hit"] = True
            except OSError:
                wav_hit = False
        if not wav_hit:
            diagnostics.setdefault("audio_cache", {})["hit"] = False

        # ---- AAC cache: the audio encode depends only on the wav (graph
        # ---- hash), so encode it ONCE per graph and mux with -c:a copy on
        # ---- every later render. Cuts ~40s (native AAC twoloop) or ~12s
        # ---- (fast coder) out of every non-cached render after the first.
        audio_aac_cache = audio_cache_dir / f"{graph_hash}.m4a"
        audio_aac_path: Path | None = None
        if cmds.audio_wav.is_file():
            aac_hit = audio_aac_cache.is_file() and audio_aac_cache.stat().st_size > 0
            if not aac_hit:
                aac_t0 = time.monotonic()
                aac_hit = encode_audio_aac_cache(
                    cmds.audio_wav, audio_aac_cache, audio_bitrate,
                )
                if aac_hit:
                    diagnostics.setdefault("audio_cache", {})["aac_elapsed_sec"] = (
                        time.monotonic() - aac_t0
                    )
            if aac_hit:
                audio_aac_path = audio_aac_cache
            diagnostics.setdefault("audio_cache", {})["aac_hit"] = bool(aac_hit)

        if not frame_pull_enabled:
            # Try the pure-ffmpeg CUDA fast path first when the timeline is
            # simple enough; fall back to the melt pipe on any ineligibility
            # or failure. Only whole-file emissions qualify (no trimming).
            if (
                requested_emission_profile in {"final", "review-artifact"}
                and hwaccel_on
                and not plan.overlay_clips
                and not plan.frame_overlays
                and timeline_supports_cuda_fastpath(plan.melt_timeline)
            ):
                cuda_result = run_cuda_fastpath(
                    plan.melt_timeline,
                    plan.asset_paths,
                    output_mp4,
                    profile,
                    spec,
                    timeout_s=melt_timeout,
                    audio_cmd=melt_audio_cmd,
                    audio_wav=cmds.audio_wav,
                    audio_aac=audio_aac_path,
                    acodec=profile.acodec,
                    audio_bitrate=audio_bitrate,
                )
                if cuda_result.used and cuda_result.returncode == 0:
                    diagnostics["cuda_fastpath"] = {
                        "used": True,
                        "elapsed_sec": cuda_result.elapsed_sec,
                        "speed_x": cuda_result.speed_x,
                        "output_path": cuda_result.output_path,
                    }
                    return _cuda_result_to_pipe_result(cuda_result)
                diagnostics["cuda_fastpath"] = {
                    "used": bool(cuda_result.used),
                    "error": cuda_result.error,
                    "returncode": cuda_result.returncode,
                    "elapsed_sec": cuda_result.elapsed_sec,
                }
                if cuda_result.used and cuda_result.returncode != 0:
                    # A failed fast path must not mask a good melt fallback.
                    log.warning(
                        "cuda fast path failed (rc=%s), falling back to melt: %s",
                        cuda_result.returncode, cuda_result.error[-200:],
                    )
            return run_pipe(cmds, timeout_s=melt_timeout)
        clients = build_frame_pull_clients(
            project_dir,
            plan.frame_overlays,
            timeout_s=min(30.0, float(melt_timeout)),
        )
        return run_pipe(
            cmds,
            timeout_s=melt_timeout,
            frame_clients=clients,
        )

    def _record_frame_pull_result(
        result: object | None = None,
        error: object | None = None,
    ) -> None:
        if not frame_pull_enabled:
            return
        if result is not None:
            frame_pull["frames_requested"] = int(
                getattr(result, "frames_requested", 0)
            )
            frame_pull["elapsed_sec"] = float(
                getattr(result, "frame_elapsed_sec", 0.0)
            )
        if error is not None:
            frame_pull["error_code"] = "remotion_frame_pull_failed"
            frame_pull["error"] = _bounded_error(error)

    t0 = time.monotonic()
    try:
        result = _run_render_pipe()
    except PipeRunError as exc:
        _record_frame_pull_result(error=exc)
        if frame_pull_enabled and _frame_pull_fallback_requested():
            try:
                _switch_to_materialize()
                result = _run_render_pipe()
                _record_frame_pull_result(result=result)
            except Exception as fallback_exc:
                _record_frame_pull_result(error=fallback_exc)
                recorder.record(
                    "melt_audio",
                    0.0,
                    status="failed",
                    error=str(fallback_exc),
                )
                recorder.skip("melt_video", reason="pipe_failed")
                recorder.skip("ffmpeg_encode", reason="pipe_failed")
                recorder.skip("source_repair", reason="render_pipe_failed")
                diagnostics["pipe_elapsed_sec"] = time.monotonic() - t0
                diagnostics["stages"] = recorder.stages
                return _fail(
                    mode=mode,
                    profile=profile,
                    output_path=str(output_mp4),
                    duration_sec=timeline.duration_sec,
                    elapsed_sec=time.monotonic() - t0,
                    graph_hash=graph_hash,
                    error=str(fallback_exc),
                    project_dir=project_dir,
                    project_id=project_id,
                    record_failed_snapshot=True,
                    diagnostics=diagnostics,
                )
        else:
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
                mode=mode,
                profile=profile,
                output_path=str(output_mp4),
                duration_sec=timeline.duration_sec,
                elapsed_sec=time.monotonic() - t0,
                graph_hash=graph_hash,
                error=str(exc),
                project_dir=project_dir,
                project_id=project_id,
                record_failed_snapshot=True,
                diagnostics=diagnostics,
            )
    _record_frame_pull_result(result=result)
    if (
        frame_pull_enabled
        and result.returncode != 0
        and _frame_pull_fallback_requested()
    ):
        try:
            _switch_to_materialize()
            result = _run_render_pipe()
            _record_frame_pull_result(result=result)
        except Exception as exc:
            _record_frame_pull_result(error=exc)
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
                mode=mode,
                profile=profile,
                output_path=str(output_mp4),
                duration_sec=timeline.duration_sec,
                elapsed_sec=time.monotonic() - t0,
                graph_hash=graph_hash,
                error=str(exc),
                project_dir=project_dir,
                project_id=project_id,
                record_failed_snapshot=True,
                diagnostics=diagnostics,
            )
    # hwaccel retry: melt failed with hwaccel XML -> re-emit without + retry once
    if result.returncode != 0 and hwaccel_on and result.melt_rc != 0:
        xml_cpu = emit_timeline(
            plan.melt_timeline, config, asset_paths=plan.asset_paths, hwaccel=False,
        )
        xml_path.write_text(xml_cpu)
        try:
            result = _run_render_pipe()
        except PipeRunError as exc:
            _record_frame_pull_result(error=exc)
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
        _record_frame_pull_result(result=result)
    elapsed = time.monotonic() - t0
    if result.returncode == 0 and output_mp4.is_file() and output_mp4.stat().st_size > 0:
        protected_spans = [
            (
                overlay.position_sec,
                overlay.position_sec + overlay.duration_sec,
            )
            for overlay in plan.overlay_clips
        ]
        repair_t0 = time.monotonic()
        repair_path = output_mp4.with_name(f"{output_mp4.stem}.repaired.mp4")
        if whole_file_repair and repair_detect:
            diagnostics["repair_policy"]["executed"] = True
            try:
                repair = repair_render_output(
                    output_mp4,
                    repair_path,
                    source_baseline,
                    protected_spans=protected_spans,
                    repair_intentional_black=repair_intentional_black,
                    detector_timeout_s=repair_budget.get("detector_timeout_s"),
                    skip_if_no_source_defects=True,
                    reencode=repair_reencode,
                )
            except Exception as exc:
                repair = {"ok": False, "changed": False, "error": str(exc)}
        else:
            repair = {
                "ok": True,
                "changed": False,
                "output_path": str(output_mp4),
                "reason": "emission_profile_not_whole_file",
                "protected_spans": [],
                "policy_version": SOURCE_REPAIR_POLICY_VERSION,
            }
        if repair.get("ok") and repair.get("changed"):
            os.replace(repair_path, output_mp4)
        repair_elapsed = time.monotonic() - repair_t0
        repair_diagnostics = {
            key: value
            for key, value in repair.items()
            if key not in {"output_path"}
        }
        repair_diagnostics.setdefault(
            "detector_timeout_s", repair_budget.get("detector_timeout_s"),
        )
        repair_diagnostics.setdefault("detector_windows", [])
        repair_diagnostics.setdefault("detector_errors", [])
        repair_diagnostics["elapsed_sec"] = repair_elapsed
        diagnostics["repair"] = repair_diagnostics
        diagnostics["repair_policy"].update({
            "changed": bool(repair.get("changed")),
            "protected_spans": repair.get("protected_spans", protected_spans),
            "timeout": {
                "detector_timeout_s": repair_diagnostics.get(
                    "detector_timeout_s",
                ),
                "remaining_budget_sec": repair_budget.get(
                    "remaining_budget_sec",
                ),
                "detector_windows": repair_diagnostics.get(
                    "detector_windows", [],
                ),
                "detector_errors": repair_diagnostics.get(
                    "detector_errors", [],
                ),
            },
        })
        if whole_file_repair:
            recorder.record(
                "source_repair",
                repair_elapsed,
                status="completed" if repair.get("ok") else "failed",
                changed=bool(repair.get("changed")),
            )
        else:
            recorder.skip(
                "source_repair",
                reason="emission_profile_not_whole_file",
            )
    else:
        diagnostics["repair_policy"]["reason"] = "render_output_unavailable"
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
    # Write-back the audio mix for identical-graph reuse (skip when the wav
    # was already a cache hit).
    if not diagnostics.get("audio_cache", {}).get("hit") and cmds.audio_wav.is_file():
        try:
            shutil.copyfile(cmds.audio_wav, audio_cache_path)
            diagnostics.setdefault("audio_cache", {})["cached"] = True
        except OSError as exc:
            diagnostics.setdefault("audio_cache", {})["writeback_error"] = str(exc)[:200]
    if not frame_pull_enabled:
        try:
            successful_manifest = build_materialization_manifest(
                unmaterialized_timeline,
                materialize_report,
                mode=mode,
                profile_fingerprint=fingerprint,
                graph_hash=graph_hash,
            )
            write_manifest_atomic(manifest_path, successful_manifest)
            diagnostics["materialization_manifest"] = str(manifest_path)
        except Exception as exc:
            # The deliverable is already safely cached; a manifest write failure
            # only disables the next run's direct composition reuse.
            diagnostics["materialization_manifest_error"] = str(exc)[:500]
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
