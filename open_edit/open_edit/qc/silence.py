"""Audio-level + silence detection for QC."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


DEFAULT_SILENCE_DB = -35.0
DEFAULT_SILENCE_MIN_SEC = 1.0


class AudioLevels(BaseModel):
    ok: bool
    in_sec: float
    out_sec: float
    rms_db: float
    peak_db: float
    error: Optional[str] = None


class SilenceSpan(BaseModel):
    start_sec: float
    end_sec: float
    duration_sec: float


class SilenceResult(BaseModel):
    ok: bool
    in_sec: float
    out_sec: float
    threshold_db: float
    min_sec: float
    spans: list[SilenceSpan]
    error: Optional[str] = None


def _ffmpeg() -> Optional[str]:
    return shutil.which("ffmpeg")


def get_audio_levels(
    video_path: str, in_sec: float = 0.0, out_sec: float = 0.0,
) -> AudioLevels:
    """Compute RMS + peak dB over [in_sec, out_sec]."""
    ffmpeg = _ffmpeg()
    if ffmpeg is None:
        return AudioLevels(ok=False, in_sec=in_sec, out_sec=out_sec, rms_db=0.0, peak_db=0.0, error="ffmpeg not on PATH")
    if not Path(video_path).is_file():
        return AudioLevels(ok=False, in_sec=in_sec, out_sec=out_sec, rms_db=0.0, peak_db=0.0, error=f"video not found: {video_path}")
    if not _has_audio_stream(video_path):
        return AudioLevels(ok=True, in_sec=in_sec, out_sec=out_sec, rms_db=0.0, peak_db=0.0)

    cmd = [ffmpeg, "-hide_banner", "-i", video_path,
           "-vn", "-af", "astats=metadata=1:reset=0", "-f", "null", "-"]
    if in_sec > 0 or out_sec > 0:
        cmd += ["-ss", f"{in_sec:.3f}"]
    if out_sec > 0:
        cmd += ["-to", f"{(out_sec - in_sec):.3f}"]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return AudioLevels(ok=False, in_sec=in_sec, out_sec=out_sec, rms_db=0.0, peak_db=0.0, error="ffmpeg timed out after 60s")
    if proc.returncode != 0:
        return AudioLevels(
            ok=False, in_sec=in_sec, out_sec=out_sec, rms_db=0.0, peak_db=0.0,
            error=_last_stderr_line(proc.stderr) or "ffmpeg failed",
        )
    text = proc.stderr or ""
    rms_db = _parse_overall_db(text, "RMS level")
    peak_db = _parse_overall_db(text, "Peak level")
    if rms_db == 0.0:
        rms_db = _parse_db(text, "RMS level")
    if peak_db == 0.0:
        peak_db = _parse_db(text, "Peak level")
    return AudioLevels(ok=True, in_sec=in_sec, out_sec=out_sec, rms_db=rms_db, peak_db=peak_db)


def list_silence(
    video_path: str, in_sec: float = 0.0, out_sec: float = 0.0,
    threshold_db: float = DEFAULT_SILENCE_DB, min_sec: float = DEFAULT_SILENCE_MIN_SEC,
) -> SilenceResult:
    """Return silence spans where audio falls below threshold_db for at least min_sec."""
    ffmpeg = _ffmpeg()
    if ffmpeg is None:
        return SilenceResult(ok=False, in_sec=in_sec, out_sec=out_sec, threshold_db=threshold_db, min_sec=min_sec, spans=[], error="ffmpeg not on PATH")
    if not Path(video_path).is_file():
        return SilenceResult(ok=False, in_sec=in_sec, out_sec=out_sec, threshold_db=threshold_db, min_sec=min_sec, spans=[], error=f"video not found: {video_path}")
    if not _has_audio_stream(video_path):
        return SilenceResult(ok=True, in_sec=in_sec, out_sec=out_sec, threshold_db=threshold_db, min_sec=min_sec, spans=[])

    cmd = [ffmpeg, "-hide_banner", "-i", video_path, "-vn",
           "-af", f"silencedetect=noise={threshold_db}dB:d={min_sec}",
           "-f", "null", "-"]
    if in_sec > 0 or out_sec > 0:
        cmd += ["-ss", f"{in_sec:.3f}"]
    if out_sec > 0:
        cmd += ["-to", f"{(out_sec - in_sec):.3f}"]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return SilenceResult(ok=False, in_sec=in_sec, out_sec=out_sec, threshold_db=threshold_db, min_sec=min_sec, spans=[], error="ffmpeg timed out after 60s")
    if proc.returncode != 0:
        return SilenceResult(
            ok=False, in_sec=in_sec, out_sec=out_sec, threshold_db=threshold_db, min_sec=min_sec, spans=[],
            error=_last_stderr_line(proc.stderr) or "ffmpeg failed",
        )
    spans = _parse_silence(proc.stderr or "", base_offset=in_sec)
    return SilenceResult(ok=True, in_sec=in_sec, out_sec=out_sec, threshold_db=threshold_db, min_sec=min_sec, spans=spans)


def _has_audio_stream(video_path: str) -> bool:
    """Return True if the file has at least one audio stream."""
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=index",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ],
        capture_output=True, text=True, timeout=30,
    )
    return bool((proc.stdout or "").strip())


def _last_stderr_line(stderr: str) -> str:
    """Return the last non-empty line of stderr, or empty string."""
    lines = (stderr or "").strip().splitlines()
    return lines[-1] if lines else ""


def _parse_db(text: str, key: str) -> float:
    m = re.search(rf'{re.escape(key)}=(-?\d+(?:\.\d+)?)', text)
    return float(m.group(1)) if m else 0.0


def _parse_overall_db(text: str, key: str) -> float:
    m = re.search(r'Overall[\s\S]*?' + re.escape(key) + r'=(-?\d+(?:\.\d+)?)', text)
    return float(m.group(1)) if m else 0.0


def _parse_silence(text: str, base_offset: float) -> list[SilenceSpan]:
    """Parse silencedetect output."""
    starts: list[float] = []
    ends: list[tuple[float, float]] = []
    for line in text.splitlines():
        ms = re.search(r"silence_start:\s*(-?\d+(?:\.\d+)?)", line)
        me = re.search(r"silence_end:\s*(-?\d+(?:\.\d+)?)\s*\|\s*silence_duration:\s*(-?\d+(?:\.\d+)?)", line)
        if ms:
            starts.append(float(ms.group(1)) + base_offset)
        if me:
            ends.append((float(me.group(1)) + base_offset, float(me.group(2))))
    return [
        SilenceSpan(start_sec=s, end_sec=e, duration_sec=dur)
        for s, (e, dur) in zip(starts, ends)
    ]
