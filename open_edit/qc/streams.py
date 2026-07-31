"""Stream-level probing for QC (streams / duration / audio_sync checks).

Single ffprobe JSON call returns stream counts, per-stream durations and
the container duration so the gate can run the documented ``streams``,
``duration`` and ``audio_sync`` checks without three separate probes.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class StreamsInfo(BaseModel):
    ok: bool
    video_streams: int
    audio_streams: int
    video_duration_s: Optional[float] = None
    audio_duration_s: Optional[float] = None
    container_duration_s: Optional[float] = None
    codec_types: list[str] = []
    error: Optional[str] = None


def _as_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def probe_streams(video_path: str) -> StreamsInfo:
    """Return stream counts + durations for ``video_path`` via one ffprobe call."""
    if not Path(video_path).is_file():
        return StreamsInfo(
            ok=False, video_streams=0, audio_streams=0,
            error=f"video not found: {video_path}",
        )
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "stream=codec_type,duration",
                "-show_entries", "format=duration",
                "-of", "json", video_path,
            ],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return StreamsInfo(
            ok=False, video_streams=0, audio_streams=0,
            error=f"ffprobe failed: {exc}",
        )
    if proc.returncode != 0:
        lines = (proc.stderr or "").strip().splitlines()
        return StreamsInfo(
            ok=False, video_streams=0, audio_streams=0,
            error=lines[-1] if lines else "ffprobe failed",
        )
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return StreamsInfo(
            ok=False, video_streams=0, audio_streams=0,
            error="ffprobe emitted non-JSON output",
        )

    streams = data.get("streams", []) if isinstance(data, dict) else []
    video = [s for s in streams if isinstance(s, dict) and s.get("codec_type") == "video"]
    audio = [s for s in streams if isinstance(s, dict) and s.get("codec_type") == "audio"]

    video_dur = _as_float(video[0].get("duration")) if video else None
    audio_dur = _as_float(audio[0].get("duration")) if audio else None
    fmt = data.get("format", {}) if isinstance(data, dict) else {}
    container_dur = _as_float(fmt.get("duration"))

    return StreamsInfo(
        ok=True,
        video_streams=len(video),
        audio_streams=len(audio),
        video_duration_s=video_dur,
        audio_duration_s=audio_dur,
        container_duration_s=container_dur,
        codec_types=[s.get("codec_type", "?") for s in streams if isinstance(s, dict)],
    )
