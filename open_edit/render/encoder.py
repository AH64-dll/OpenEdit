"""Video encoder backend selection: GPU (default) or CPU.

Resolves the best available hardware encoder at runtime and exposes a
stable API for melt consumers and ffmpeg overlay passes.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Literal

EncoderBackend = Literal["gpu", "cpu"]

# Preference order when backend=gpu.
_GPU_CANDIDATES: tuple[tuple[str, list[str]], ...] = (
    ("h264_nvenc", ["-preset", "p4", "-cq", "20"]),
    ("h264_vaapi", ["-qp", "20"]),
    ("h264_qsv", ["-preset", "medium", "-global_quality", "20"]),
)


def resolve_backend(requested: str | None = None) -> EncoderBackend:
    """Return ``gpu`` or ``cpu`` from explicit request or env default.

    When ``OPEN_EDIT_RENDER_BACKEND`` is unset, Windows defaults to ``cpu``
    (VAAPI is Linux-only; NVENC/QSV still work if the caller sets ``gpu``).
    """
    if requested is not None and str(requested).strip():
        raw = str(requested).strip().lower()
    else:
        env = os.environ.get("OPEN_EDIT_RENDER_BACKEND")
        if env is None or not str(env).strip():
            raw = "cpu" if sys.platform == "win32" else "gpu"
        else:
            raw = str(env).strip().lower()
    if raw in ("cpu", "software", "libx264"):
        return "cpu"
    return "gpu"


def _ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def _probe_encoder(vcodec: str, extra: list[str]) -> bool:
    """Return True if ffmpeg can encode a trivial frame with ``vcodec``."""
    ffmpeg = _ffmpeg()
    if ffmpeg is None:
        return False
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.04",
        "-frames:v", "1", "-c:v", vcodec, *extra,
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except (subprocess.TimeoutExpired, OSError):
        return False
    return proc.returncode == 0


def detect_gpu_vcodec() -> tuple[str, list[str]] | None:
    """Return the first working GPU encoder and its quality args."""
    for vcodec, extra in _GPU_CANDIDATES:
        if _probe_encoder(vcodec, extra):
            return vcodec, extra
    return None


def resolve_vcodec(backend: str | None = None) -> tuple[str, list[str]]:
    """Return (vcodec, extra_ffmpeg_args) for the requested backend."""
    if resolve_backend(backend) == "cpu":
        return "libx264", ["-preset", "veryfast", "-crf", "20"]
    detected = detect_gpu_vcodec()
    if detected is not None:
        return detected
    return "libx264", ["-preset", "veryfast", "-crf", "20"]


def apply_profile_vcodec(profile_vcodec: str, backend: str | None = None) -> str:
    """Override a RenderProfile vcodec when backend requests GPU."""
    if resolve_backend(backend) == "cpu":
        return "libx264"
    vcodec, _ = resolve_vcodec(backend)
    return vcodec


def ffmpeg_video_args(backend: str | None = None) -> list[str]:
    """ffmpeg ``-c:v`` and quality flags for overlay / post passes."""
    vcodec, extra = resolve_vcodec(backend)
    return ["-c:v", vcodec, *extra]
