"""Video encoder backend selection: GPU (default) or CPU.

Resolves the best available hardware encoder at runtime and exposes a
stable API for melt consumers and ffmpeg overlay passes.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import Literal

EncoderBackend = Literal["gpu", "cpu"]

# Preference order when backend=gpu.
_GPU_CANDIDATES: tuple[tuple[str, list[str]], ...] = (
    ("h264_nvenc", ["-preset", "p4", "-rc", "constqp", "-cq", "20", "-profile:v", "high"]),
    ("h264_amf", ["-quality", "balanced", "-rc", "cqp", "-qp_i", "20", "-qp_p", "20"]),
    ("h264_qsv", ["-preset", "medium", "-global_quality", "20"]),
    ("h264_vaapi", ["-qp", "20"]),
)

_GPU_FINAL: tuple[tuple[str, list[str]], ...] = (
    (
        "h264_nvenc",
        [
            "-preset", "p5",
            "-rc", "vbr",
            "-b:v", "10M",
            "-maxrate", "14M",
            "-bufsize", "20M",
            "-profile:v", "high",
            "-bf", "2",
        ],
    ),
    ("h264_amf", ["-quality", "quality", "-rc", "vbr_peak", "-b:v", "10M", "-maxrate", "14M"]),
    ("h264_qsv", ["-preset", "medium", "-global_quality", "18"]),
    ("h264_vaapi", ["-qp", "18"]),
)


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


def detect_gpu_vcodec(*, final: bool = False) -> tuple[str, list[str]] | None:
    """Return the first working GPU encoder and its quality args."""
    candidates = _GPU_FINAL if final else _GPU_CANDIDATES
    for vcodec, extra in candidates:
        if _probe_encoder(vcodec, extra):
            return vcodec, extra
    return None


def resolve_vcodec(backend: str | None = None, *, final: bool = False) -> tuple[str, list[str]]:
    """Return (vcodec, extra_ffmpeg_args) for the requested backend."""
    if resolve_backend(backend) == "cpu":
        if final:
            return "libx264", ["-preset", "medium", "-crf", "18", "-profile:v", "high"]
        return "libx264", ["-preset", "veryfast", "-crf", "20"]
    detected = detect_gpu_vcodec(final=final)
    if detected is not None:
        return detected
    if final:
        return "libx264", ["-preset", "medium", "-crf", "18", "-profile:v", "high"]
    return "libx264", ["-preset", "veryfast", "-crf", "20"]


def apply_profile_vcodec(profile_vcodec: str, backend: str | None = None) -> str:
    """Override a RenderProfile vcodec when backend requests GPU."""
    if resolve_backend(backend) == "cpu":
        return "libx264"
    vcodec, _ = resolve_vcodec(backend)
    return vcodec


def ffmpeg_video_args(backend: str | None = None, *, final: bool = False) -> list[str]:
    """ffmpeg ``-c:v`` and quality flags for overlay / post passes."""
    vcodec, extra = resolve_vcodec(backend, final=final)
    return ["-c:v", vcodec, *extra]
