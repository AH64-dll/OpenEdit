"""Frame-level QC: thumbnails and small crops.

The contract (per Phase 6 plan §QC tools):
- A single capped frame, ≤480px on the long edge, JPEG quality ~70.
- Enough for "yes, there's a title card here" or "yes, this is a dissolve,
  not a hard cut" — never enough to burn tokens on.

The output file size cap is enforced via ``-fs`` (max output size in
bytes) as a belt-and-braces guarantee in case the encoder ignores the
quality setting.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Caps from the Phase 6 plan.
MAX_LONG_EDGE = 480
JPEG_QUALITY = 70
MAX_BYTES = 250_000  # 250 KB — well below what even a 1080p frame at q70 hits


@dataclass
class ThumbnailResult:
    ok: bool
    output_path: str
    width: int
    height: int
    file_bytes: int
    timestamp_sec: float
    error: Optional[str] = None


def _ensure_ffmpeg() -> Optional[str]:
    return shutil.which("ffmpeg")


def _probe(path: str) -> dict:
    """Tiny ffprobe wrapper — only width/height/rate are needed."""
    out = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,avg_frame_rate",
            "-of", "default=noprint_wrappers=1:nokey=0",
            path,
        ],
        capture_output=True, text=True, timeout=30,
    )
    info: dict = {}
    for line in (out.stdout or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            info[k.strip()] = v.strip()
    return info


def _long_edge_scale(width: int, height: int) -> tuple[int, int]:
    """Scale so the long edge is at most MAX_LONG_EDGE, preserving aspect."""
    if width <= 0 or height <= 0:
        return 0, 0
    long_edge = max(width, height)
    if long_edge <= MAX_LONG_EDGE:
        return width, height
    factor = MAX_LONG_EDGE / long_edge
    new_w = max(2, int(width * factor) // 2 * 2)
    new_h = max(2, int(height * factor) // 2 * 2)
    return new_w, new_h


def get_thumbnail(
    video_path: str,
    timestamp_sec: float,
    output_path: str,
) -> ThumbnailResult:
    """Extract a single JPEG frame at ``timestamp_sec``.

    Caps the long edge at ``MAX_LONG_EDGE`` and the file size at
    ``MAX_BYTES``. If the source is taller than wide, the long edge is the
    height; if wider, the width.
    """
    ffmpeg = _ensure_ffmpeg()
    if ffmpeg is None:
        return ThumbnailResult(False, output_path, 0, 0, 0, timestamp_sec, "ffmpeg not on PATH")
    if not Path(video_path).is_file():
        return ThumbnailResult(False, output_path, 0, 0, 0, timestamp_sec, f"video not found: {video_path}")

    info = _probe(video_path)
    try:
        src_w = int(info.get("width", 0))
        src_h = int(info.get("height", 0))
    except (TypeError, ValueError):
        src_w = src_h = 0
    if src_w == 0 or src_h == 0:
        return ThumbnailResult(False, output_path, 0, 0, 0, timestamp_sec, "could not probe source dimensions")
    out_w, out_h = _long_edge_scale(src_w, src_h)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    vf = f"scale={out_w}:{out_h}"
    cmd = [
        ffmpeg, "-y",
        "-ss", f"{timestamp_sec:.3f}",
        "-i", video_path,
        "-vframes", "1",
        "-vf", vf,
        "-q:v", str(JPEG_QUALITY),  # mjpeg q-scale (lower = better; ~70 maps to mid-low)
        "-fs", str(MAX_BYTES),
        output_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0 or not Path(output_path).is_file():
        return ThumbnailResult(False, output_path, 0, 0, 0, timestamp_sec,
                               (proc.stderr or "").strip().splitlines()[-1:][:1] or ["ffmpeg failed"][0])
    size = Path(output_path).stat().st_size
    return ThumbnailResult(True, output_path, out_w, out_h, size, timestamp_sec, None)


def get_qc_crop(
    video_path: str,
    timestamp_sec: float,
    region: dict,
    output_path: str,
) -> ThumbnailResult:
    """Extract a small crop of the frame at ``timestamp_sec``.

    ``region`` is a dict with keys ``x``, ``y``, ``w``, ``h`` in source
    pixels. The crop is then scaled to the same ≤480px long-edge cap as
    ``get_thumbnail`` so a tiny region becomes a useful, viewable image.
    """
    ffmpeg = _ensure_ffmpeg()
    if ffmpeg is None:
        return ThumbnailResult(False, output_path, 0, 0, 0, timestamp_sec, "ffmpeg not on PATH")
    if not Path(video_path).is_file():
        return ThumbnailResult(False, output_path, 0, 0, 0, timestamp_sec, f"video not found: {video_path}")
    for k in ("x", "y", "w", "h"):
        if k not in region:
            return ThumbnailResult(False, output_path, 0, 0, 0, timestamp_sec, f"region missing '{k}'")

    info = _probe(video_path)
    try:
        src_w = int(info.get("width", 0))
        src_h = int(info.get("height", 0))
    except (TypeError, ValueError):
        src_w = src_h = 0
    if src_w == 0 or src_h == 0:
        return ThumbnailResult(False, output_path, 0, 0, 0, timestamp_sec, "could not probe source dimensions")

    x = max(0, int(region["x"]))
    y = max(0, int(region["y"]))
    w = max(2, int(region["w"]))
    h = max(2, int(region["h"]))
    # Clamp to source.
    if x + w > src_w:
        w = max(2, src_w - x)
    if y + h > src_h:
        h = max(2, src_h - y)

    out_w, out_h = _long_edge_scale(w, h)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    vf = f"crop={w}:{h}:{x}:{y},scale={out_w}:{out_h}"
    cmd = [
        ffmpeg, "-y",
        "-ss", f"{timestamp_sec:.3f}",
        "-i", video_path,
        "-vframes", "1",
        "-vf", vf,
        "-q:v", str(JPEG_QUALITY),
        "-fs", str(MAX_BYTES),
        output_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0 or not Path(output_path).is_file():
        return ThumbnailResult(False, output_path, 0, 0, 0, timestamp_sec,
                               (proc.stderr or "").strip().splitlines()[-1:][:1] or ["ffmpeg failed"][0])
    size = Path(output_path).stat().st_size
    return ThumbnailResult(True, output_path, out_w, out_h, size, timestamp_sec, None)
