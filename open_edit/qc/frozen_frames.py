"""Frozen-frame detection for QC.

Wraps ffmpeg's ``freezedetect`` filter. A segment is "frozen" when
consecutive decoded frames are identical (unchanged within a noise
floor) for at least ``min_sec`` consecutive seconds. The stream is
downscaled to ``scale_height`` before detection so a full decode stays
cheap on long renders. Deterministic: same input → same spans.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from open_edit.render.ffmpeg_probe import probe_duration


DEFAULT_FREEZE_MIN_SEC = 1.0
DEFAULT_FREEZE_NOISE_DB = -50.0
DEFAULT_SCALE_HEIGHT = 360

_FREEZE_START_RE = re.compile(r"freeze_start:\s*(-?\d+(?:\.\d+)?)")
_FREEZE_END_RE = re.compile(r"freeze_end:\s*(-?\d+(?:\.\d+)?)")
_FREEZE_DUR_RE = re.compile(r"freeze_duration:\s*(-?\d+(?:\.\d+)?)")


class FrozenSpan(BaseModel):
    start_sec: float
    end_sec: float
    duration_sec: float


class FrozenFramesResult(BaseModel):
    ok: bool
    min_sec: float
    noise_db: float
    spans: list[FrozenSpan]
    error: Optional[str] = None


def list_frozen_frames(
    video_path: str,
    min_sec: float = DEFAULT_FREEZE_MIN_SEC,
    noise_db: float = DEFAULT_FREEZE_NOISE_DB,
    scale_height: int = DEFAULT_SCALE_HEIGHT,
    in_sec: float = 0.0,
    out_sec: float = 0.0,
    timeout_s: float | None = None,
) -> FrozenFramesResult:
    """Return frozen-frame spans for a source range.

    The optional range is useful for source baselines: a timeline should not
    decode the tail of a long asset that is not used by the edit. Returned
    timestamps remain relative to the original source.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return FrozenFramesResult(
            ok=False, min_sec=min_sec, noise_db=noise_db, spans=[],
            error="ffmpeg not on PATH",
        )
    if not Path(video_path).is_file():
        return FrozenFramesResult(
            ok=False, min_sec=min_sec, noise_db=noise_db, spans=[],
            error=f"video not found: {video_path}",
        )

    vf = (
        f"scale=-2:{int(scale_height)}:flags=bicubic,"
        f"freezedetect=n={noise_db}dB:d={min_sec}"
    )
    if out_sec > 0 and out_sec <= in_sec:
        return FrozenFramesResult(
            ok=False, min_sec=min_sec, noise_db=noise_db, spans=[],
            error=f"invalid range: out_sec={out_sec} must be > in_sec={in_sec}",
        )
    cmd = [ffmpeg, "-hide_banner", "-i", video_path]
    if in_sec > 0:
        cmd += ["-ss", f"{in_sec:.3f}"]
    if out_sec > 0:
        cmd += ["-t", f"{(out_sec - in_sec):.3f}"]
    cmd += ["-vf", vf, "-an", "-f", "null", "-"]
    timeout = 120.0 if timeout_s is None else max(0.001, float(timeout_s))
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return FrozenFramesResult(
            ok=False, min_sec=min_sec, noise_db=noise_db, spans=[],
            error=f"ffmpeg timed out after {timeout:g}s",
        )
    if proc.returncode != 0:
        lines = (proc.stderr or "").strip().splitlines()
        return FrozenFramesResult(
            ok=False, min_sec=min_sec, noise_db=noise_db, spans=[],
            error=lines[-1] if lines else "ffmpeg failed",
        )
    try:
        total_duration = (
            out_sec if out_sec > 0 else probe_duration(video_path)
        )
    except Exception:
        total_duration = None
    return FrozenFramesResult(
        ok=True, min_sec=min_sec, noise_db=noise_db,
        spans=_parse_freezedetect(proc.stderr or "", total_duration=total_duration),
    )


def _parse_freezedetect(text: str, total_duration: float | None = None) -> list[FrozenSpan]:
    """Parse freezedetect lines from ffmpeg's stderr.

    freezedetect emits a ``freeze_start`` line, then a
    ``freeze_duration``/``freeze_end`` pair when the freeze ends. A
    freeze that runs to EOF emits no ``freeze_end``; ``total_duration``
    (probed video duration) is used as the span end so the trailing
    freeze does not collapse to duration 0.
    """
    starts: list[float] = []
    durations: list[float] = []
    ends: list[float] = []
    for line in text.splitlines():
        ms = _FREEZE_START_RE.search(line)
        me = _FREEZE_END_RE.search(line)
        md = _FREEZE_DUR_RE.search(line)
        if ms:
            starts.append(float(ms.group(1)))
        if md:
            durations.append(float(md.group(1)))
        if me:
            ends.append(float(me.group(1)))
    spans: list[FrozenSpan] = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else None
        d = durations[i] if i < len(durations) else None
        if e is None and d is not None:
            e = s + d
        if e is None:
            e = total_duration if total_duration is not None and total_duration > s else s
        spans.append(FrozenSpan(
            start_sec=s, end_sec=e,
            duration_sec=(d if d is not None else e - s),
        ))
    return spans
