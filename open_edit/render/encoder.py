"""Video encoder backend selection: GPU (default) or CPU.

Resolves the best available hardware encoder at runtime and exposes a
stable API for melt consumers and ffmpeg overlay passes.

``select_encoder`` is the single source for per-encoder quality args:
one policy, rendered in both arg dialects (melt ``key=value`` consumer
args and ffmpeg flags). ``profiles`` consumes ``EncoderSpec.melt_args``
and ``graphics_overlay`` consumes ``EncoderSpec.ffmpeg_args``.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Literal

EncoderBackend = Literal["gpu", "cpu"]

# GPU encoders probed in preference order when backend=gpu.
_GPU_ORDER: tuple[str, ...] = ("h264_nvenc", "h264_amf", "h264_qsv", "h264_vaapi")


@dataclass(frozen=True)
class EncoderSpec:
    """Quality args for one encoder, rendered in both arg dialects.

    ``melt_args`` are ``key=value`` consumer args; ``ffmpeg_args`` are
    ffmpeg flags (without ``-c:v``). Each dialect keeps its own value
    spellings for the same policy (e.g. melt ``b=10M`` vs ffmpeg
    ``-b:v 10M``, melt proxy ``cq=23`` vs ffmpeg preview ``-cq 20``).
    """
    vcodec: str
    melt_args: tuple[str, ...]
    ffmpeg_args: tuple[str, ...]


# key: (vcodec, final) -> EncoderSpec. final=True is the deliverable
# render; final=False is the fast proxy/preview pass.
_SPECS: dict[tuple[str, bool], EncoderSpec] = {
    ("h264_nvenc", False): EncoderSpec(
        "h264_nvenc",
        melt_args=("rc=constqp", "cq=23", "preset=p4"),
        ffmpeg_args=("-preset", "p4", "-rc", "constqp", "-cq", "20", "-profile:v", "high"),
    ),
    ("h264_nvenc", True): EncoderSpec(
        "h264_nvenc",
        melt_args=("rc=vbr", "b=10M", "maxrate=14M", "bufsize=20M", "preset=p5", "bf=2"),
        ffmpeg_args=(
            "-preset", "p5",
            "-rc", "vbr",
            "-b:v", "10M",
            "-maxrate", "14M",
            "-bufsize", "20M",
            "-profile:v", "high",
            "-bf", "2",
        ),
    ),
    ("h264_amf", False): EncoderSpec(
        "h264_amf",
        melt_args=(),
        ffmpeg_args=("-quality", "balanced", "-rc", "cqp", "-qp_i", "20", "-qp_p", "20"),
    ),
    ("h264_amf", True): EncoderSpec(
        "h264_amf",
        melt_args=("quality=quality", "rc=vbr_peak", "b=10M", "maxrate=14M"),
        ffmpeg_args=("-quality", "quality", "-rc", "vbr_peak", "-b:v", "10M", "-maxrate", "14M"),
    ),
    ("h264_qsv", False): EncoderSpec(
        "h264_qsv",
        melt_args=(),
        ffmpeg_args=("-preset", "medium", "-global_quality", "20"),
    ),
    ("h264_qsv", True): EncoderSpec(
        "h264_qsv",
        melt_args=("global_quality=18", "preset=medium"),
        ffmpeg_args=("-preset", "medium", "-global_quality", "18"),
    ),
    ("h264_vaapi", False): EncoderSpec(
        "h264_vaapi",
        melt_args=(),
        ffmpeg_args=("-qp", "20"),
    ),
    ("h264_vaapi", True): EncoderSpec(
        "h264_vaapi",
        melt_args=("crf=18",),
        ffmpeg_args=("-qp", "18"),
    ),
    ("libx264", False): EncoderSpec(
        "libx264",
        melt_args=("crf=23", "preset=veryfast"),
        ffmpeg_args=("-preset", "veryfast", "-crf", "20"),
    ),
    ("libx264", True): EncoderSpec(
        "libx264",
        melt_args=("crf=18", "preset=medium", "vb=0", "profile=high"),
        ffmpeg_args=("-preset", "medium", "-crf", "18", "-profile:v", "high"),
    ),
}


def resolve_backend(requested: str | None = None) -> EncoderBackend:
    """Return ``gpu`` or ``cpu`` from explicit request or env default.

    Default is ``gpu`` (NVENC/AMF/QSV when available). Set
    ``OPEN_EDIT_RENDER_BACKEND=cpu`` to force software encoding.
    """
    if requested is not None and str(requested).strip():
        raw = str(requested).strip().lower()
    else:
        env = os.environ.get("OPEN_EDIT_RENDER_BACKEND")
        if env is None or not str(env).strip():
            raw = "gpu"
        else:
            raw = str(env).strip().lower()
    if raw in ("cpu", "software", "libx264"):
        return "cpu"
    return "gpu"


def _ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def _probe_encoder(vcodec: str, extra: list[str]) -> bool:
    """Return True if ffmpeg can encode a trivial frame with ``vcodec``.

    NVENC rejects frames smaller than ~128px, so the probe uses 256x256.
    """
    ffmpeg = _ffmpeg()
    if ffmpeg is None:
        return False
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.04",
        "-frames:v", "1", "-c:v", vcodec, *extra,
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except (subprocess.TimeoutExpired, OSError):
        return False
    return proc.returncode == 0


def select_encoder(backend: str | None = None, *, final: bool = False) -> EncoderSpec:
    """Resolve the requested backend to an ``EncoderSpec``.

    GPU backends probe the available hardware encoder at runtime and
    fall back to libx264 when none is present; CPU always yields
    libx264. ``final`` selects the deliverable (True) or proxy (False)
    quality policy.
    """
    if resolve_backend(backend) == "cpu":
        return _SPECS[("libx264", final)]
    for vcodec in _GPU_ORDER:
        spec = _SPECS[(vcodec, final)]
        if _probe_encoder(vcodec, list(spec.ffmpeg_args)):
            return spec
    return _SPECS[("libx264", final)]


def detect_gpu_vcodec(*, final: bool = False) -> tuple[str, list[str]] | None:
    """Return the first working GPU encoder and its quality args."""
    for vcodec in _GPU_ORDER:
        spec = _SPECS[(vcodec, final)]
        if _probe_encoder(vcodec, list(spec.ffmpeg_args)):
            return vcodec, list(spec.ffmpeg_args)
    return None


def resolve_vcodec(backend: str | None = None, *, final: bool = False) -> tuple[str, list[str]]:
    """Return (vcodec, extra_ffmpeg_args) for the requested backend."""
    spec = select_encoder(backend, final=final)
    return spec.vcodec, list(spec.ffmpeg_args)


def apply_profile_vcodec(profile_vcodec: str, backend: str | None = None) -> str:
    """Override a RenderProfile vcodec when backend requests GPU."""
    return select_encoder(backend, final=False).vcodec


def ffmpeg_video_args(backend: str | None = None, *, final: bool = False) -> list[str]:
    """ffmpeg ``-c:v`` and quality flags for overlay / post passes."""
    spec = select_encoder(backend, final=final)
    return ["-c:v", spec.vcodec, *spec.ffmpeg_args]
