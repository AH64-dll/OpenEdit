"""Single-frame thumbnail extraction for QC."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


MAX_LONG_EDGE = 480
JPEG_QUALITY = 70
MAX_BYTES = 250_000


class ThumbnailResult(BaseModel):
    ok: bool
    output_path: str
    width: int
    height: int
    file_bytes: int
    timestamp_sec: float
    error: Optional[str] = None


def _probe_dimensions(path: str) -> tuple[int, int]:
    """Return (width, height) via ffprobe. Returns (0, 0) on failure."""
    out = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "default=noprint_wrappers=1:nokey=0",
            path,
        ],
        capture_output=True, text=True, timeout=30,
    )
    w, h = 0, 0
    for line in (out.stdout or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            if k.strip() == "width":
                try:
                    w = int(v.strip())
                except ValueError:
                    pass
            elif k.strip() == "height":
                try:
                    h = int(v.strip())
                except ValueError:
                    pass
    return w, h


def _long_edge_scale(width: int, height: int) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        return 0, 0
    long_edge = max(width, height)
    if long_edge <= MAX_LONG_EDGE:
        return width, height
    factor = MAX_LONG_EDGE / long_edge
    return max(2, int(width * factor) // 2 * 2), max(2, int(height * factor) // 2 * 2)


def get_thumbnail(
    video_path: str, timestamp_sec: float, output_path: str,
) -> ThumbnailResult:
    """Extract a single JPEG frame at `timestamp_sec`."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return ThumbnailResult(
            ok=False, output_path=output_path, width=0, height=0,
            file_bytes=0, timestamp_sec=timestamp_sec,
            error="ffmpeg not on PATH",
        )
    if not Path(video_path).is_file():
        return ThumbnailResult(
            ok=False, output_path=output_path, width=0, height=0,
            file_bytes=0, timestamp_sec=timestamp_sec,
            error=f"video not found: {video_path}",
        )

    src_w, src_h = _probe_dimensions(video_path)
    if src_w == 0 or src_h == 0:
        return ThumbnailResult(
            ok=False, output_path=output_path, width=0, height=0,
            file_bytes=0, timestamp_sec=timestamp_sec,
            error="could not probe source dimensions",
        )
    out_w, out_h = _long_edge_scale(src_w, src_h)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    vf = f"scale={out_w}:{out_h}"
    cmd = [
        ffmpeg, "-y", "-ss", f"{timestamp_sec:.3f}", "-i", video_path,
        "-vframes", "1", "-vf", vf,
        "-q:v", str(JPEG_QUALITY), "-fs", str(MAX_BYTES), output_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0 or not Path(output_path).is_file():
        lines = (proc.stderr or "").strip().splitlines()
        return ThumbnailResult(
            ok=False, output_path=output_path, width=0, height=0,
            file_bytes=0, timestamp_sec=timestamp_sec,
            error=lines[-1] if lines else "ffmpeg failed",
        )
    size = Path(output_path).stat().st_size
    return ThumbnailResult(
        ok=True, output_path=output_path, width=out_w, height=out_h,
        file_bytes=size, timestamp_sec=timestamp_sec,
    )
