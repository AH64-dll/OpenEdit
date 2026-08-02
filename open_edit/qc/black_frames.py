"""Black-frame detection for QC.

Wraps ffmpeg's blackdetect filter. A frame is "black" if its average luma
falls below ``threshold`` for at least ``min_duration`` consecutive seconds.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


DEFAULT_BLACK_THRESHOLD = 0.10
DEFAULT_BLACK_MIN_SEC = 0.5
DEFAULT_PICTURE_BLACK_RATIO = 0.98
DEFAULT_SCALE_HEIGHT = 360


class BlackSpan(BaseModel):
    start_sec: float
    end_sec: float
    duration_sec: float


class BlackFramesResult(BaseModel):
    ok: bool
    in_sec: float
    out_sec: float
    threshold: float
    min_sec: float
    spans: list[BlackSpan]
    error: Optional[str] = None


def list_black_frames(
    video_path: str,
    in_sec: float = 0.0,
    out_sec: float = 0.0,
    threshold: float = DEFAULT_BLACK_THRESHOLD,
    min_sec: float = DEFAULT_BLACK_MIN_SEC,
    scale_height: int | None = None,
    timeout_s: float | None = None,
) -> BlackFramesResult:
    """Return black-frame spans for the [in_sec, out_sec] range.

    ``scale_height`` can be used for long, high-resolution sources where
    decoding the full raster just to classify black frames is unnecessarily
    expensive. The timeline baseline uses the same 360px analysis size as
    frozen-frame detection, while callers that need the original behavior can
    leave it unset.
    """
    if out_sec > 0 and out_sec <= in_sec:
        return BlackFramesResult(
            ok=False, in_sec=in_sec, out_sec=out_sec,
            threshold=threshold, min_sec=min_sec, spans=[],
            error=f"invalid range: out_sec={out_sec} must be > in_sec={in_sec}",
        )
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return BlackFramesResult(
            ok=False, in_sec=in_sec, out_sec=out_sec,
            threshold=threshold, min_sec=min_sec, spans=[],
            error="ffmpeg not on PATH",
        )
    if not Path(video_path).is_file():
        return BlackFramesResult(
            ok=False, in_sec=in_sec, out_sec=out_sec,
            threshold=threshold, min_sec=min_sec, spans=[],
            error=f"video not found: {video_path}",
        )

    filters: list[str] = []
    if scale_height is not None:
        filters.append(
            f"scale=-2:{int(scale_height)}:flags=bicubic"
        )
    filters.append(
        "blackdetect="
        f"d={min_sec}:pix_th={threshold}:pic_th={DEFAULT_PICTURE_BLACK_RATIO}"
    )
    cmd = [ffmpeg, "-hide_banner", "-i", video_path]
    if in_sec > 0:
        cmd += ["-ss", f"{in_sec:.3f}"]
    if out_sec > 0:
        cmd += ["-t", f"{(out_sec - in_sec):.3f}"]
    cmd += ["-vf", ",".join(filters), "-an", "-f", "null", "-"]

    timeout = 60.0 if timeout_s is None else max(0.001, float(timeout_s))
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return BlackFramesResult(
            ok=False, in_sec=in_sec, out_sec=out_sec,
            threshold=threshold, min_sec=min_sec, spans=[],
            error=f"ffmpeg timed out after {timeout:g}s",
        )
    if proc.returncode != 0:
        lines = (proc.stderr or "").strip().splitlines()
        return BlackFramesResult(
            ok=False, in_sec=in_sec, out_sec=out_sec,
            threshold=threshold, min_sec=min_sec, spans=[],
            error=lines[-1] if lines else "ffmpeg failed",
        )
    spans = _parse_blackdetect(proc.stderr or "", base_offset=in_sec)
    return BlackFramesResult(
        ok=True, in_sec=in_sec, out_sec=out_sec,
        threshold=threshold, min_sec=min_sec, spans=spans,
    )


def _parse_blackdetect(text: str, base_offset: float) -> list[BlackSpan]:
    """Parse blackdetect lines from ffmpeg's stderr."""
    spans: list[BlackSpan] = []
    for m in re.finditer(
        r"black_start:(-?\d+(?:\.\d+)?)\s+black_end:(-?\d+(?:\.\d+)?)\s+black_duration:(-?\d+(?:\.\d+)?)",
        text,
    ):
        s = float(m.group(1)) + base_offset
        e = float(m.group(2)) + base_offset
        d = float(m.group(3))
        spans.append(BlackSpan(start_sec=s, end_sec=e, duration_sec=d))
    return spans
