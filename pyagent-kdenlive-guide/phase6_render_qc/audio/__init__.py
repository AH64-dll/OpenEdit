"""Audio-level + silence detection for QC.

- ``get_audio_levels`` returns numeric RMS/peak over a time range, in dB.
  Just numbers, never a spectrogram image.
- ``list_silence`` returns ranges where the audio falls below a threshold
  for a minimum duration (uses ffmpeg's silencedetect filter).

Both call ffmpeg with a single pass over the requested range so the cost
is one ffmpeg invocation per tool call.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Defaults — same as the Phase 6 plan suggests. These are conservative
# (a 0.5s silence is often just a breath; we want 1s+ to be flagged).
DEFAULT_SILENCE_DB = -35.0
DEFAULT_SILENCE_MIN_SEC = 1.0


@dataclass
class AudioLevels:
    ok: bool
    in_sec: float
    out_sec: float
    rms_db: float
    peak_db: float
    error: Optional[str] = None


@dataclass
class SilenceSpan:
    start_sec: float
    end_sec: float
    duration_sec: float


@dataclass
class SilenceResult:
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
    video_path: str,
    in_sec: float = 0.0,
    out_sec: float = 0.0,
) -> AudioLevels:
    """Compute RMS + peak dB over the [in_sec, out_sec] range.

    If ``out_sec`` is 0 or negative, the whole file is measured.
    """
    ffmpeg = _ffmpeg()
    if ffmpeg is None:
        return AudioLevels(False, in_sec, out_sec, 0.0, 0.0, "ffmpeg not on PATH")
    if not Path(video_path).is_file():
        return AudioLevels(False, in_sec, out_sec, 0.0, 0.0, f"video not found: {video_path}")

    # astats metadata is printed to stderr at end-of-stream. reset=0 keeps
    # running stats across the whole file; the "Overall" section appears
    # once at the end.
    cmd = [ffmpeg, "-hide_banner", "-i", video_path,
           "-vn", "-af", "astats=metadata=1:reset=0",
           "-f", "null", "-"]
    if in_sec > 0 or out_sec > 0:
        cmd += ["-ss", f"{in_sec:.3f}"]
    if out_sec > 0:
        cmd += ["-to", f"{(out_sec - in_sec):.3f}"]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        return AudioLevels(False, in_sec, out_sec, 0.0, 0.0,
                           (proc.stderr or "").strip().splitlines()[-1:][:1] or ["ffmpeg failed"][0])
    text = proc.stderr or ""
    # astats prints an "Overall" block at end. We accept either an "Overall"
    # value or a per-stream value as fallback.
    rms_db = _parse_overall_db(text, "RMS level")
    peak_db = _parse_overall_db(text, "Peak level")
    if rms_db == 0.0:
        rms_db = _parse_db(text, "RMS level")
    if peak_db == 0.0:
        peak_db = _parse_db(text, "Peak level")
    return AudioLevels(True, in_sec, out_sec, rms_db, peak_db, None)


def list_silence(
    video_path: str,
    in_sec: float = 0.0,
    out_sec: float = 0.0,
    threshold_db: float = DEFAULT_SILENCE_DB,
    min_sec: float = DEFAULT_SILENCE_MIN_SEC,
) -> SilenceResult:
    """Return silence spans where audio falls below ``threshold_db`` for at
    least ``min_sec`` consecutive seconds."""
    ffmpeg = _ffmpeg()
    if ffmpeg is None:
        return SilenceResult(False, in_sec, out_sec, threshold_db, min_sec, [], "ffmpeg not on PATH")
    if not Path(video_path).is_file():
        return SilenceResult(False, in_sec, out_sec, threshold_db, min_sec, [], f"video not found: {video_path}")

    cmd = [ffmpeg, "-hide_banner", "-i", video_path, "-vn",
           "-af", f"silencedetect=noise={threshold_db}dB:d={min_sec}",
           "-f", "null", "-"]
    if in_sec > 0 or out_sec > 0:
        cmd += ["-ss", f"{in_sec:.3f}"]
    if out_sec > 0:
        cmd += ["-to", f"{(out_sec - in_sec):.3f}"]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        return SilenceResult(False, in_sec, out_sec, threshold_db, min_sec, [],
                             (proc.stderr or "").strip().splitlines()[-1:][:1] or ["ffmpeg failed"][0])
    spans = _parse_silence(proc.stderr or "", base_offset=in_sec)
    return SilenceResult(True, in_sec, out_sec, threshold_db, min_sec, spans, None)


def _parse_db(text: str, key: str) -> float:
    m = re.search(rf'{re.escape(key)}=(-?\d+(?:\.\d+)?)', text)
    return float(m.group(1)) if m else 0.0


def _parse_overall_db(text: str, key: str) -> float:
    """Pick the value from the 'Overall' astats section if present."""
    m = re.search(r'Overall[\s\S]*?' + re.escape(key) + r'=(-?\d+(?:\.\d+)?)', text)
    return float(m.group(1)) if m else 0.0


def _parse_silence(text: str, base_offset: float) -> list[SilenceSpan]:
    """Parse silencedetect output: lines like
        [silencedetect @ 0x...] silence_start: 12.345
        [silencedetect @ 0x...] silence_end: 14.567 | silence_duration: 2.222
    """
    starts: list[float] = []
    ends: list[tuple[float, float]] = []
    for line in text.splitlines():
        ms = re.search(r"silence_start:\s*(-?\d+(?:\.\d+)?)", line)
        me = re.search(r"silence_end:\s*(-?\d+(?:\.\d+)?)\s*\|\s*silence_duration:\s*(-?\d+(?:\.\d+)?)", line)
        if ms:
            starts.append(float(ms.group(1)) + base_offset)
        if me:
            ends.append((float(me.group(1)) + base_offset, float(me.group(2))))
    out: list[SilenceSpan] = []
    for s, (e, dur) in zip(starts, ends):
        out.append(SilenceSpan(start_sec=s, end_sec=e, duration_sec=dur))
    return out
