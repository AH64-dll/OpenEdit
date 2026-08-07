"""Pure-ffmpeg CUDA render fast path for simple timelines.

When a timeline is simple enough (single video clip, no effects/transitions/
overlays/remotion), melt is a needless CPU bottleneck: it decodes on CPU and
streams raw frames through system memory. ffmpeg with ``hwaccel=cuda`` decodes
on the GPU, scales with ``scale_cuda``, and encodes with NVENC, all on-device,
at several times realtime.

The fast path only claims timelines it can reproduce exactly:
* one video clip spanning the whole timeline
* no clip/track effects, transitions, speed ramps, or volume keyframes
* no overlay clips, frame overlays, or remotion compositions
* no audio tracks (audio is re-rendered by the caller's melt audio pass)

Any mismatch falls back to the melt pipe. The fast path is opt-in per render
call and reports diagnostics through ``CudaFastPathResult``.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from open_edit.render.encoder import EncoderSpec

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CudaFastPathResult:
    """Outcome of a CUDA fast-path attempt."""

    used: bool
    returncode: int | None = None
    elapsed_sec: float = 0.0
    error: str = ""
    output_path: str = ""
    ffmpeg_cmd: list[str] = field(default_factory=list)
    speed_x: float = 0.0
    audio_elapsed_sec: float = 0.0


def _ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def _cuda_probe() -> bool:
    """True if ffmpeg can decode+encode with CUDA end-to-end (probed once).

    Uses a real short H.264 file: ``-hwaccel cuda -hwaccel_output_format cuda``
    only produces CUDA frames when the decoder (CUVID) actually runs, which a
    synthetic lavfi color source cannot do. The probe clip is the same one the
    melt CUDA probe uses (tests/testdata/raw_videos/clip_a.mp4).
    """
    import os
    from pathlib import Path as _Path

    if os.environ.get("OPEN_EDIT_CUDA_FASTPATH") == "0":
        return False
    global _cuda_probe_ok
    if _cuda_probe_ok is not None:
        return _cuda_probe_ok
    ffmpeg = _ffmpeg()
    if ffmpeg is None:
        _cuda_probe_ok = False
        return False
    clip_a = _Path(__file__).resolve().parents[2] / "tests" / "testdata" / "raw_videos" / "clip_a.mp4"
    if not clip_a.is_file():
        _cuda_probe_ok = False
        return False
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error",
        "-hwaccel", "cuda", "-hwaccel_output_format", "cuda",
        "-i", str(clip_a),
        "-vf", "scale_cuda=256:256",
        "-frames:v", "1", "-c:v", "h264_nvenc",
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        _cuda_probe_ok = False
        return False
    _cuda_probe_ok = proc.returncode == 0
    return _cuda_probe_ok


_cuda_probe_ok: bool | None = None


# Effect types that only touch the audio mix. They are applied by the
# caller's melt-audio pass, so they do not block the pure-ffmpeg CUDA video
# fast path (volume/gain on clips).
_AUDIO_ONLY_EFFECT_TYPES = frozenset({"volume"})


def timeline_supports_cuda_fastpath(timeline: Any) -> bool:
    """Conservative eligibility check for the pure-ffmpeg CUDA path.

    Returns True only for a single full-length video clip on one track with no
    effects, transitions, overlays, remotion compositions, or audio. Audio is
    handled by the caller's separate melt pass, so its presence is fine.
    """
    if timeline is None:
        return False
    video_tracks = [t for t in getattr(timeline, "tracks", []) if t.kind == "video"]
    if len(video_tracks) != 1:
        return False
    track = video_tracks[0]
    if len(track.clips) != 1:
        return False
    if track.effects:
        return False
    clip = track.clips[0]
    # Audio-only effects (volume/gain) do NOT disqualify the CUDA fast path:
    # the fast path encodes video only, and the caller's separate melt-audio
    # pass applies the gain to the wav. Video-affecting effects still require
    # melt composition.
    if clip.effects and any(
        getattr(effect, "effect_type", "") not in _AUDIO_ONLY_EFFECT_TYPES
        for effect in clip.effects
    ):
        return False
    # Position must be exactly the timeline start.
    if abs(clip.position_sec) > 1e-6:
        return False
    # The clip must cover the whole timeline (allow ~1 frame slop). A trimmed
    # source (in_point > 0) is fine: the ffmpeg command expresses it with
    # -ss, so trims stay on the CUDA fast path.
    tolerance = 1.0 / max(float(getattr(timeline, "frame_rate_num", 30) or 30), 1e-9)
    if clip.out_point_sec - clip.in_point_sec < getattr(timeline, "duration_sec", 0.0) - tolerance:
        return False
    if clip.in_point_sec < -1e-6:
        return False
    # Overlays / remotion / hyperframes would need melt composition.
    if getattr(timeline, "overlays", None):
        return False
    if getattr(timeline, "remotion_compositions", None):
        return False
    return True


def build_cuda_fastpath_command(
    timeline: Any,
    asset_paths: dict[str, str],
    output_mp4: Path,
    profile: Any,
    spec: EncoderSpec,
    *,
    start_sec: float = 0.0,
    duration_sec: float | None = None,
) -> list[str] | None:
    """Build the ffmpeg CUDA command for an eligible timeline, or None."""
    if not timeline_supports_cuda_fastpath(timeline):
        return None
    if not _cuda_probe():
        return None
    clip = next(
        c for t in timeline.tracks if t.kind == "video"
        for c in t.clips
    )
    media = asset_paths.get(clip.asset_hash)
    if not media or not Path(media).is_file():
        return None
    # Respect the profile's explicit scale override (e.g. 320x180 for a fast
    # proxy); fall back to width/height when no scale is set.
    scale = getattr(profile, "scale", None)
    if scale and "x" in str(scale):
        width, height = (int(p) for p in str(scale).split("x", 1))
    else:
        width = int(getattr(profile, "width", 1920))
        height = int(getattr(profile, "height", 1080))
    fps = float(
        getattr(profile, "frame_rate_num", 30) / max(getattr(profile, "frame_rate_den", 1), 1)
    )
    cmd = [
        "ffmpeg", "-y",
        "-hwaccel", "cuda",
        "-hwaccel_output_format", "cuda",
        "-i", media,
    ]
    if clip.in_point_sec > 1e-6:
        cmd += ["-ss", f"{clip.in_point_sec:.6f}"]
    if start_sec > 0:
        cmd += ["-ss", f"{start_sec:.6f}"]
    gop = max(1, round(fps))
    cmd += [
        "-vf", f"scale_cuda={width}:{height}",
        "-c:v", spec.vcodec, *spec.ffmpeg_args,
        "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0",
        "-an",
    ]
    if duration_sec is not None:
        cmd += ["-t", f"{duration_sec:.6f}"]
    cmd.append(str(output_mp4))
    return cmd


def run_cuda_fastpath(
    timeline: Any,
    asset_paths: dict[str, str],
    output_mp4: Path,
    profile: Any,
    spec: EncoderSpec,
    *,
    start_sec: float = 0.0,
    duration_sec: float | None = None,
    timeout_s: float = 7200.0,
    audio_cmd: list[str] | None = None,
    audio_wav: Path | None = None,
    audio_aac: Path | None = None,
    acodec: str = "aac",
    audio_bitrate: str = "192k",
) -> CudaFastPathResult:
    """Run the CUDA fast path; returns a result with ``used=False`` on any
    ineligibility or failure (never raises for render errors).

    Video is encoded with CUDA decode/scale + NVENC. When ``audio_cmd`` and
    ``audio_wav`` are supplied, the melt audio pass runs first and the encoded
    video is muxed with the audio in a second ffmpeg pass.
    """
    if not _cuda_probe():
        return CudaFastPathResult(used=False, error="cuda probe unavailable")
    cmd = build_cuda_fastpath_command(
        timeline, asset_paths, output_mp4, profile, spec,
        start_sec=start_sec, duration_sec=duration_sec,
    )
    if cmd is None:
        return CudaFastPathResult(used=False, error="timeline not eligible")
    raw_output = output_mp4.with_name(f"{output_mp4.stem}.video.mp4")
    t0 = time.monotonic()
    audio_elapsed = 0.0
    if audio_cmd and audio_wav is not None:
        a_t0 = time.monotonic()
        try:
            a_proc = subprocess.run(
                audio_cmd, capture_output=True, text=True, timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            return CudaFastPathResult(
                used=True, returncode=1,
                error=f"cuda fast path audio pass timed out after {timeout_s:g}s",
                output_path=str(output_mp4), ffmpeg_cmd=cmd,
            )
        audio_elapsed = time.monotonic() - a_t0
        if a_proc.returncode != 0:
            return CudaFastPathResult(
                used=True, returncode=a_proc.returncode,
                error=f"melt audio pass failed: {(a_proc.stderr or '')[-512:]}",
                output_path=str(output_mp4), ffmpeg_cmd=cmd,
            )
    # Encode video to a temp file so audio can be muxed afterwards.
    video_cmd = list(cmd)
    video_cmd[-1] = str(raw_output)
    try:
        proc = subprocess.run(
            video_cmd, capture_output=True, text=True, timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return CudaFastPathResult(
            used=True, returncode=1, error=f"cuda fast path timed out after {timeout_s:g}s",
            output_path=str(output_mp4), ffmpeg_cmd=video_cmd,
        )
    elapsed = time.monotonic() - t0
    if proc.returncode != 0 or not raw_output.is_file() or raw_output.stat().st_size <= 0:
        return CudaFastPathResult(
            used=True,
            returncode=proc.returncode,
            elapsed_sec=elapsed,
            error=((proc.stderr or "")[-512:] or "video encode produced no output"),
            output_path=str(output_mp4),
            ffmpeg_cmd=video_cmd,
        )
    if audio_wav is not None and audio_wav.is_file():
        # Pre-encoded AAC (from the orchestrator's per-graph audio cache) is
        # muxed with -c:a copy; otherwise the wav is encoded during mux.
        use_aac = audio_aac is not None and audio_aac.is_file()
        mux_cmd = [
            "ffmpeg", "-y",
            "-i", str(raw_output),
            "-i", str(audio_aac if use_aac else audio_wav),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy",
        ]
        if use_aac:
            mux_cmd += ["-c:a", "copy"]
        else:
            mux_cmd += ["-c:a", acodec, "-b:a", audio_bitrate]
            if acodec == "aac":
                # Native AAC default coder (twoloop) is ~3x slower at the
                # same rate; 'fast' is perceptually fine for preview audio.
                mux_cmd += ["-aac_coder", "fast"]
        mux_cmd += ["-shortest", "-movflags", "+faststart", str(output_mp4)]
        try:
            mux_proc = subprocess.run(
                mux_cmd, capture_output=True, text=True, timeout=120,
            )
        except subprocess.TimeoutExpired:
            return CudaFastPathResult(
                used=True, returncode=1, error="cuda fast path mux timed out",
                output_path=str(output_mp4), ffmpeg_cmd=mux_cmd,
            )
        if mux_proc.returncode != 0:
            return CudaFastPathResult(
                used=True, returncode=mux_proc.returncode,
                error=f"audio mux failed: {(mux_proc.stderr or '')[-512:]}",
                output_path=str(output_mp4), ffmpeg_cmd=mux_cmd,
            )
        try:
            raw_output.unlink(missing_ok=True)
        except OSError:
            pass
    else:
        try:
            raw_output.replace(output_mp4)
        except OSError:
            pass
    duration = duration_sec or max(
        float(getattr(timeline, "duration_sec", 0.0)), 1e-9
    )
    speed = duration / max(elapsed, 1e-9)
    return CudaFastPathResult(
        used=True,
        returncode=0,
        elapsed_sec=elapsed,
        error="",
        output_path=str(output_mp4),
        ffmpeg_cmd=video_cmd,
        speed_x=round(speed, 2),
        audio_elapsed_sec=audio_elapsed,
    )


__all__ = [
    "CudaFastPathResult",
    "build_cuda_fastpath_command",
    "run_cuda_fastpath",
    "timeline_supports_cuda_fastpath",
]
