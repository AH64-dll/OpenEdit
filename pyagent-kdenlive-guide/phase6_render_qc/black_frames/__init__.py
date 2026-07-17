"""Black-frame detection for QC.

Wraps ffmpeg's ``blackdetect`` filter. A frame is "black" if its average
luma falls below ``threshold`` for at least ``min_duration`` consecutive
seconds.

Per the Phase 6 plan, this is a cheap deterministic check that runs before
any thumbnail or audio sample is requested.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Defaults from the Phase 6 plan.
DEFAULT_BLACK_THRESHOLD = 0.10  # luma 0..1
DEFAULT_BLACK_MIN_SEC = 0.5


@dataclass
class BlackSpan:
    start_sec: float
    end_sec: float
    duration_sec: float


@dataclass
class BlackFramesResult:
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
) -> BlackFramesResult:
    """Return black-frame spans for the [in_sec, out_sec] range."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return BlackFramesResult(False, in_sec, out_sec, threshold, min_sec, [], "ffmpeg not on PATH")
    if not Path(video_path).is_file():
        return BlackFramesResult(False, in_sec, out_sec, threshold, min_sec, [], f"video not found: {video_path}")

    cmd = [ffmpeg, "-hide_banner", "-i", video_path,
           "-vf", f"blackdetect=d={min_sec}:pic_th={threshold}",
           "-an", "-f", "null", "-"]
    if in_sec > 0 or out_sec > 0:
        cmd += ["-ss", f"{in_sec:.3f}"]
    if out_sec > 0:
        cmd += ["-to", f"{(out_sec - in_sec):.3f}"]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        return BlackFramesResult(False, in_sec, out_sec, threshold, min_sec, [],
                                 (proc.stderr or "").strip().splitlines()[-1:][:1] or ["ffmpeg failed"][0])
    spans = _parse_blackdetect(proc.stderr or "", base_offset=in_sec)
    return BlackFramesResult(True, in_sec, out_sec, threshold, min_sec, spans, None)


def _parse_blackdetect(text: str, base_offset: float) -> list[BlackSpan]:
    """Parse blackdetect lines:

        [blackdetect @ 0x...] black_start:12.345 black_end:14.567 black_duration:2.222
    """
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
