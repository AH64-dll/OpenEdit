"""Fast silence compression via ffconcat inpoint/outpoint stream copy.

Avoids the O(n) mega-filter_complex anti-pattern that stalls on long
videos with hundreds of silence gaps. Uses a single-source ffconcat list
instead of extracting hundreds of temp segment files.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from open_edit.render.ffmpeg_probe import detect_silence_spans, probe_duration

DEFAULT_THRESHOLD_DB = -35.0
DEFAULT_MAX_SILENCE_S = 0.2
DEFAULT_DETECT_MIN_S = 0.2
DEFAULT_WORKERS = 8
MIN_SEGMENT_S = 0.05


def build_keep_ranges(
    duration: float,
    silences: list[tuple[float, float]],
    max_silence_s: float,
) -> list[tuple[float, float]]:
    removals: list[tuple[float, float]] = []
    for start, end in silences:
        gap = end - start
        if gap > max_silence_s:
            removals.append((start + max_silence_s, end))

    if not removals:
        return [(0.0, duration)]

    keep: list[tuple[float, float]] = []
    cursor = 0.0
    for rm_start, rm_end in removals:
        if rm_start > cursor:
            keep.append((cursor, rm_start))
        cursor = max(cursor, rm_end)
    if cursor < duration:
        keep.append((cursor, duration))
    return [(s, e) for s, e in keep if e - s >= MIN_SEGMENT_S]


def _write_ffconcat(ranges: list[tuple[float, float]], input_path: Path, list_path: Path) -> None:
    lines = ["ffconcat version 1.0", ""]
    for start, end in ranges:
        lines.append(f"file '{input_path.resolve()}'")
        lines.append(f"inpoint {start:.6f}")
        lines.append(f"outpoint {end:.6f}")
        lines.append("")
    list_path.write_text("\n".join(lines) + "\n")


def _concat_ranges(
    input_path: Path,
    ranges: list[tuple[float, float]],
    output: Path,
    *,
    audio_only: bool = False,
) -> None:
    list_path = output.parent / ".ffconcat.txt"
    _write_ffconcat(ranges, input_path, list_path)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(list_path),
    ]
    suffix = output.suffix.lower()
    if audio_only or suffix in {".mp3", ".m4a", ".aac", ".wav", ".flac"}:
        if suffix == ".mp3":
            cmd += ["-c:a", "libmp3lame", "-b:a", "192k", "-vn"]
        elif suffix == ".wav":
            cmd += ["-c:a", "pcm_s16le", "-vn"]
        else:
            cmd += ["-c", "copy", "-vn"]
        if suffix == ".mp4":
            cmd += ["-movflags", "+faststart"]
    else:
        cmd += ["-c", "copy", "-movflags", "+faststart"]
    cmd.append(str(output))
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    list_path.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffconcat failed: {proc.stderr.strip()}")


def extract_audio(
    video_path: Path,
    audio_path: Path,
    *,
    codec: str = "mp3",
    bitrate: str = "192k",
) -> Path:
    """Extract audio track from a video file to ``audio_path``."""
    video_path = Path(video_path)
    audio_path = Path(audio_path)
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    if codec == "mp3":
        acodec_args = ["-c:a", "libmp3lame", "-b:a", bitrate]
    elif codec == "aac":
        acodec_args = ["-c:a", "aac", "-b:a", bitrate]
    else:
        acodec_args = ["-c:a", "copy"]
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video_path), "-vn", *acodec_args,
        str(audio_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"audio extract failed: {proc.stderr.strip()}")
    return audio_path


def compress_silence_audio(
    input_path: Path,
    output_path: Path,
    **kwargs: object,
) -> dict:
    """Compress silences in an audio file; output is audio-only."""
    return compress_silence(input_path, output_path, audio_only=True, **kwargs)  # type: ignore[arg-type]


def compress_silence(
    input_path: Path,
    output_path: Path,
    *,
    max_silence_s: float = DEFAULT_MAX_SILENCE_S,
    threshold_db: float = DEFAULT_THRESHOLD_DB,
    detect_min_s: float = DEFAULT_DETECT_MIN_S,
    workers: int = DEFAULT_WORKERS,  # reserved for future parallel strategies
    audio_only: bool = False,
) -> dict:
    """Trim silences longer than ``max_silence_s``; return summary stats."""
    t_total = time.monotonic()
    input_path = Path(input_path)
    output_path = Path(output_path)

    duration = probe_duration(input_path)
    silences = detect_silence_spans(
        input_path, threshold_db=threshold_db, min_s=detect_min_s,
    )
    keep = build_keep_ranges(duration, silences, max_silence_s)
    new_duration = sum(e - s for s, e in keep)
    removed = duration - new_duration

    if removed <= 0:
        shutil.copy2(input_path, output_path)
        return {
            "ok": True,
            "changed": False,
            "input_duration_s": duration,
            "output_duration_s": duration,
            "silence_count": len(silences),
            "segment_count": len(keep),
            "removed_s": 0.0,
            "elapsed_s": time.monotonic() - t_total,
        }

    t_concat = time.monotonic()
    _concat_ranges(input_path, keep, output_path, audio_only=audio_only)
    concat_elapsed = time.monotonic() - t_concat

    out_dur = probe_duration(output_path)
    total_elapsed = time.monotonic() - t_total

    return {
        "ok": True,
        "changed": True,
        "input_duration_s": duration,
        "output_duration_s": out_dur,
        "silence_count": len(silences),
        "segment_count": len(keep),
        "removed_s": removed,
        "elapsed_s": total_elapsed,
        "concat_elapsed_s": concat_elapsed,
    }
