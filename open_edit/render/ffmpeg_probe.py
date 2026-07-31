"""Shared ffprobe/ffmpeg helpers used by render and qc.

Single home for silencedetect parsing and duration probing so the two
packages never drift on regexes, thresholds, or probe commands.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

DEFAULT_THRESHOLD_DB = -35.0
DEFAULT_MIN_S = 0.2

_START_RE = re.compile(r"silence_start:\s*(-?\d+(?:\.\d+)?)")
_END_RE = re.compile(
    r"silence_end:\s*(-?\d+(?:\.\d+)?)\s*\|\s*silence_duration:\s*(-?\d+(?:\.\d+)?)"
)


class FFprobeError(ValueError):
    """Raised when an ffmpeg/ffprobe probe exits non-zero (decode failure).

    The message is the last non-empty stderr line (fallback ``"ffmpeg
    failed"``); the full captured stderr is kept on ``.stderr``.
    """

    def __init__(self, message: str, *, stderr: str = ""):
        super().__init__(message)
        self.stderr = stderr


def _last_stderr_line(stderr: str) -> str:
    lines = (stderr or "").strip().splitlines()
    return lines[-1] if lines else ""


def detect_silence_spans(
    path: Path | str,
    threshold_db: float = DEFAULT_THRESHOLD_DB,
    min_s: float = DEFAULT_MIN_S,
    *,
    start_sec: float = 0.0,
    end_sec: float = 0.0,
    timeout: float | None = None,
) -> list[tuple[float, float]]:
    """Detect silence spans via ffmpeg's silencedetect.

    Returns ``(start, end)`` pairs in seconds, offset by ``start_sec`` when a
    time window is given (mirroring ffmpeg's ``-ss`` output seeking).
    """
    cmd = [
        "ffmpeg", "-hide_banner", "-i", str(path), "-vn",
        "-af", f"silencedetect=noise={threshold_db}dB:d={min_s}",
        "-f", "null", "-",
    ]
    if start_sec > 0 or end_sec > 0:
        cmd += ["-ss", f"{start_sec:.3f}"]
    if end_sec > 0:
        cmd += ["-to", f"{(end_sec - start_sec):.3f}"]

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)
    starts: list[float] = []
    spans: list[tuple[float, float]] = []
    for line in proc.stderr.splitlines():
        ms = _START_RE.search(line)
        me = _END_RE.search(line)
        if ms:
            starts.append(float(ms.group(1)) + start_sec)
        if me:
            end = float(me.group(1)) + start_sec
            if starts:
                spans.append((starts.pop(0), end))
    if proc.returncode != 0:
        # Decode failure: never report a partial "0 silence" success.
        raise FFprobeError(
            _last_stderr_line(proc.stderr) or "ffmpeg failed",
            stderr=proc.stderr,
        )
    return spans


def probe_duration(path: Path | str) -> float:
    """Return the container duration of ``path`` in seconds."""
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        text=True,
    ).strip()
    return float(out)
