"""Render-only repair for black and frozen source spans.

The source CAS is never rewritten. A baseline pass records defects in the
source timeline, then the completed render is repaired through a streamed
decode/encode pass only when the same defect survives in the output. Repairs
are bounded to detected spans and preserve the audio stream by copying it
from the rendered output.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable

from open_edit.ir.types import Timeline
from open_edit.qc.black_frames import (
    DEFAULT_SCALE_HEIGHT,
    list_black_frames,
)
from open_edit.qc.frozen_frames import list_frozen_frames


# Bump this when render-only repair semantics change. The orchestrator folds
# it into the render-cache key so a corrected repair policy cannot reuse an
# older proxy that was produced with different frame protection rules.
SOURCE_REPAIR_POLICY_VERSION = "source-repair-v4-black-only-default"


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _map_span(
    span: Any,
    *,
    clip_position: float,
    clip_in: float,
    clip_out: float,
    asset_hash: str,
) -> dict[str, Any] | None:
    start = max(float(span.start_sec), clip_in)
    end = min(float(span.end_sec), clip_out)
    if end <= start:
        return None
    return {
        "start_sec": clip_position + (start - clip_in),
        "end_sec": min(
            clip_position + (end - clip_in),
            clip_position + (clip_out - clip_in),
        ),
        "duration_sec": end - start,
        "source_asset_hash": asset_hash,
        "source_start_sec": start,
        "source_end_sec": end,
        "source_known": True,
    }


def collect_source_baseline(
    timeline: Timeline,
    asset_paths: dict[str, str],
) -> dict[str, Any]:
    """Detect and map source defects to their rendered timeline positions."""
    black_by_path: dict[str, list[Any]] = {}
    frozen_by_path: dict[str, list[Any]] = {}
    source_hashes: dict[str, str] = {}
    black_spans: list[dict[str, Any]] = []
    frozen_spans: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    source_end_by_path: dict[str, float] = {}

    # Limit source analysis to the portion actually referenced by the
    # timeline. Long recordings can be many times larger than the preview
    # window, and decoding their unused tail makes baseline collection exceed
    # the detector timeout.
    for track in timeline.tracks:
        if track.kind != "video":
            continue
        for clip in track.clips:
            path_text = asset_paths.get(clip.asset_hash)
            if path_text:
                key = str(Path(path_text))
                source_end_by_path[key] = max(
                    source_end_by_path.get(key, 0.0),
                    float(clip.out_point_sec),
                )

    for track in timeline.tracks:
        if track.kind != "video":
            continue
        for clip in track.clips:
            path_text = asset_paths.get(clip.asset_hash)
            if not path_text:
                continue
            path = Path(path_text)
            key = str(path)
            if key not in black_by_path:
                if not path.is_file():
                    errors.append({
                        "asset_hash": clip.asset_hash,
                        "error": f"source not found: {path}",
                    })
                    black_by_path[key] = []
                    frozen_by_path[key] = []
                    continue
                try:
                    source_hashes[clip.asset_hash] = _hash_file(path)
                    black_result = list_black_frames(
                        str(path),
                        scale_height=DEFAULT_SCALE_HEIGHT,
                        out_sec=source_end_by_path.get(key, 0.0),
                    )
                    frozen_result = list_frozen_frames(
                        str(path),
                        out_sec=source_end_by_path.get(key, 0.0),
                    )
                    black_by_path[key] = (
                        black_result.spans if black_result.ok else []
                    )
                    frozen_by_path[key] = (
                        frozen_result.spans if frozen_result.ok else []
                    )
                    if not black_result.ok and black_result.error:
                        errors.append({
                            "asset_hash": clip.asset_hash,
                            "error": black_result.error,
                        })
                    if not frozen_result.ok and frozen_result.error:
                        errors.append({
                            "asset_hash": clip.asset_hash,
                            "error": frozen_result.error,
                        })
                except (OSError, subprocess.SubprocessError) as exc:
                    black_by_path[key] = []
                    frozen_by_path[key] = []
                    errors.append({
                        "asset_hash": clip.asset_hash,
                        "error": str(exc),
                    })

            for span in black_by_path[key]:
                mapped = _map_span(
                    span,
                    clip_position=clip.position_sec,
                    clip_in=clip.in_point_sec,
                    clip_out=clip.out_point_sec,
                    asset_hash=clip.asset_hash,
                )
                if mapped is not None:
                    black_spans.append(mapped)
            for span in frozen_by_path[key]:
                mapped = _map_span(
                    span,
                    clip_position=clip.position_sec,
                    clip_in=clip.in_point_sec,
                    clip_out=clip.out_point_sec,
                    asset_hash=clip.asset_hash,
                )
                if mapped is not None:
                    frozen_spans.append(mapped)

    return {
        "version": 1,
        "source_hashes": source_hashes,
        "black_frames": black_spans,
        "frozen_frames": frozen_spans,
        "errors": errors,
    }


def _span_frame_range(span: dict[str, Any], fps: float) -> tuple[int, int]:
    start = max(0, int(math.floor(float(span["start_sec"]) * fps)))
    end = max(start + 1, int(math.ceil(float(span["end_sec"]) * fps)))
    return start, end


def _protected_intervals(
    protected_spans: Iterable[dict[str, Any] | tuple[float, float]],
) -> list[tuple[float, float]]:
    """Normalize and merge output intervals that repair must not rewrite."""
    intervals: list[tuple[float, float]] = []
    for span in protected_spans:
        try:
            if isinstance(span, dict):
                start = float(span["start_sec"])
                end = float(span["end_sec"])
            else:
                start, end = (float(span[0]), float(span[1]))
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if math.isfinite(start) and math.isfinite(end) and end > start:
            intervals.append((start, end))
    intervals.sort()
    merged: list[tuple[float, float]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _trim_span(
    span: dict[str, Any],
    start: float,
    end: float,
) -> dict[str, Any]:
    """Copy a repair span while preserving source-coordinate metadata."""
    original_start = float(span["start_sec"])
    original_end = float(span["end_sec"])
    trimmed = dict(span)
    trimmed["start_sec"] = start
    trimmed["end_sec"] = end
    trimmed["duration_sec"] = end - start
    source_start = span.get("source_start_sec")
    source_end = span.get("source_end_sec")
    if source_start is not None and source_end is not None:
        source_start_float = float(source_start)
        source_end_float = float(source_end)
        source_duration = source_end_float - source_start_float
        timeline_duration = original_end - original_start
        if source_duration > 0 and timeline_duration > 0:
            left_ratio = (start - original_start) / timeline_duration
            right_ratio = (end - original_start) / timeline_duration
            trimmed["source_start_sec"] = (
                source_start_float + source_duration * left_ratio
            )
            trimmed["source_end_sec"] = (
                source_start_float + source_duration * right_ratio
            )
    return trimmed


def _subtract_protected_spans(
    spans: Iterable[dict[str, Any]],
    protected: list[tuple[float, float]],
) -> list[dict[str, Any]]:
    """Remove overlay windows from source-repair spans.

    Repair runs after the overlay burn. Rewriting a source-known defect over
    that final output would interpolate neighboring frames and erase any
    Remotion card that happens to sit inside the same time range.
    """
    if not protected:
        return [dict(span) for span in spans]
    result: list[dict[str, Any]] = []
    for span in spans:
        try:
            start = float(span["start_sec"])
            end = float(span["end_sec"])
        except (KeyError, TypeError, ValueError):
            result.append(dict(span))
            continue
        if end <= start:
            continue
        cursor = start
        for protected_start, protected_end in protected:
            if protected_end <= cursor:
                continue
            if protected_start >= end:
                break
            if protected_start > cursor:
                result.append(
                    _trim_span(span, cursor, min(protected_start, end)),
                )
            cursor = max(cursor, protected_end)
            if cursor >= end:
                break
        if cursor < end:
            result.append(_trim_span(span, cursor, end))
    return result


def _overlaps_any(
    span: dict[str, Any],
    candidates: Iterable[dict[str, Any]],
    tolerance_sec: float = 0.05,
) -> bool:
    start = float(span.get("start_sec", 0.0))
    end = float(span.get("end_sec", start))
    for candidate in candidates:
        candidate_start = float(candidate.get("start_sec", 0.0))
        candidate_end = float(candidate.get("end_sec", candidate_start))
        if (
            start <= candidate_end + tolerance_sec
            and end >= candidate_start - tolerance_sec
        ):
            return True
    return False


def _blend(a: bytes, b: bytes, amount: float) -> bytes:
    if len(a) != len(b):
        return a
    return bytes(
        round(left + (right - left) * amount)
        for left, right in zip(a, b)
    )


def _repair_window(
    frames: list[bytes],
    previous: bytes | None,
    following: bytes | None,
    mode: str,
) -> list[bytes]:
    if not frames:
        return []
    before = previous or following
    after = following or previous
    if before is None or after is None:
        return frames
    if mode == "black":
        if previous is not None and following is not None:
            denominator = max(1, len(frames) - 1)
            return [
                _blend(previous, following, index / denominator)
                for index in range(len(frames))
            ]
        return [before for _ in frames]
    count = len(frames)
    return [
        _blend(before, after, (index + 1) / (count + 1))
        for index in range(count)
    ]


def repair_frame_sequence(
    frames: list[bytes],
    *,
    fps: float,
    black_spans: Iterable[dict[str, Any]],
    frozen_spans: Iterable[dict[str, Any]],
) -> list[bytes]:
    """Pure bounded repair helper used by the streaming renderer and tests."""
    modes: dict[int, str] = {}
    for span in black_spans:
        start, end = _span_frame_range(span, fps)
        for index in range(start, min(end, len(frames))):
            modes.setdefault(index, "black")
    for span in frozen_spans:
        start, end = _span_frame_range(span, fps)
        for index in range(start, min(end, len(frames))):
            modes[index] = "frozen"

    repaired = list(frames)
    index = 0
    while index < len(frames):
        mode = modes.get(index)
        if mode is None:
            index += 1
            continue
        end = index
        while end < len(frames) and modes.get(end) == mode:
            end += 1
        window = frames[index:end]
        repaired[index:end] = _repair_window(
            window,
            frames[index - 1] if index else None,
            frames[end] if end < len(frames) else None,
            mode,
        )
        index = end
    return repaired


def _video_layout(video_path: Path) -> tuple[int, int, float]:
    probe = shutil.which("ffprobe")
    if probe is None:
        raise RuntimeError("ffprobe not on PATH")
    proc = subprocess.run(
        [
            probe, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,avg_frame_rate",
            "-of", "json", str(video_path),
        ],
        capture_output=True, text=True, timeout=30, check=True,
    )
    stream = (json.loads(proc.stdout).get("streams") or [{}])[0]
    num, _, denom = str(stream.get("avg_frame_rate") or "30/1").partition("/")
    fps = float(num) / float(denom or "1")
    return int(stream["width"]), int(stream["height"]), fps


def _read_frame(stream: Any, frame_size: int) -> bytes | None:
    data = stream.read(frame_size)
    if not data:
        return None
    if len(data) != frame_size:
        raise RuntimeError("decoder ended with a partial video frame")
    return data


def _repair_stream(
    input_path: Path,
    output_path: Path,
    *,
    width: int,
    height: int,
    fps: float,
    spans: list[tuple[int, int, str]],
) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg not on PATH")
    frame_size = width * height * 3
    decoder = subprocess.Popen(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error",
            "-i", str(input_path), "-map", "0:v:0", "-an",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    encoder = subprocess.Popen(
        [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
            "-i", str(input_path), "-map", "0:v:0", "-map", "1:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "copy", "-shortest",
            str(output_path),
        ],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert decoder.stdout is not None
    assert encoder.stdin is not None
    span_index = 0
    frame_index = 0
    previous: bytes | None = None
    frame = _read_frame(decoder.stdout, frame_size)
    try:
        while frame is not None:
            while span_index < len(spans) and frame_index >= spans[span_index][1]:
                span_index += 1
            if span_index >= len(spans) or frame_index < spans[span_index][0]:
                encoder.stdin.write(frame)
                previous = frame
                frame_index += 1
                frame = _read_frame(decoder.stdout, frame_size)
                continue

            start, end, mode = spans[span_index]
            window: list[bytes] = []
            while frame is not None and frame_index < end:
                window.append(frame)
                frame_index += 1
                frame = _read_frame(decoder.stdout, frame_size)
            following = frame
            for repaired in _repair_window(window, previous, following, mode):
                encoder.stdin.write(repaired)
            if window:
                previous = _repair_window(window, previous, following, mode)[-1]
            # ``frame`` is the first frame after the span and is processed on
            # the next loop iteration without being discarded.
    except (BrokenPipeError, OSError):
        raise RuntimeError("frame repair encoder closed unexpectedly") from None
    finally:
        try:
            encoder.stdin.close()
        except OSError:
            pass
        decoder.stdout.close()
        decoder_rc = decoder.wait(timeout=30)
        encoder_rc = encoder.wait(timeout=30)
    if decoder_rc != 0 or encoder_rc != 0:
        error = (encoder.stderr.read() if encoder.stderr else b"").decode(
            "utf-8", errors="replace",
        ).strip()
        raise RuntimeError(error or "frame repair ffmpeg failed")


def _merge_repair_spans(
    black_spans: Iterable[dict[str, Any]],
    frozen_spans: Iterable[dict[str, Any]],
    fps: float,
) -> list[tuple[int, int, str]]:
    ranges: list[tuple[int, int, str]] = []
    for span in black_spans:
        start, end = _span_frame_range(span, fps)
        ranges.append((start, end, "black"))
    for span in frozen_spans:
        start, end = _span_frame_range(span, fps)
        ranges.append((start, end, "frozen"))
    ranges.sort()
    merged: list[tuple[int, int, str]] = []
    for start, end, mode in ranges:
        if merged and start <= merged[-1][1]:
            old_start, old_end, old_mode = merged[-1]
            merged[-1] = (
                old_start, max(old_end, end),
                "frozen" if "frozen" in (old_mode, mode) else "black",
            )
        else:
            merged.append((start, end, mode))
    return merged


def repair_render_output(
    video_path: str | Path,
    output_path: str | Path,
    source_baseline: dict[str, Any] | None = None,
    *,
    repair_source_black: bool = True,
    repair_source_frozen: bool = False,
    repair_intentional_black: bool = False,
    protected_spans: Iterable[dict[str, Any] | tuple[float, float]] = (),
) -> dict[str, Any]:
    """Repair source-known defects in a rendered output.

    Render-only detectors can flag valid low-motion or dark content after a
    proxy resize/encode. Frozen source spans remain untouched by default
    because interpolating their boundary frames can invent motion and scene
    transitions. Callers that have independently verified a frozen defect can
    opt in with ``repair_source_frozen=True``. ``repair_intentional_black``
    only opts into repairing detected black spans.
    """
    input_path = Path(video_path)
    desired_path = Path(output_path)
    baseline = source_baseline or {}
    protected = _protected_intervals(protected_spans)
    if (
        not repair_intentional_black
        and not (baseline.get("black_frames") or baseline.get("frozen_frames"))
    ):
        return {
            "ok": True,
            "changed": False,
            "output_path": str(input_path),
            "repaired_black_spans": [],
            "repaired_frozen_spans": [],
            "protected_spans": [
                {"start_sec": start, "end_sec": end}
                for start, end in protected
            ],
            "source_hashes": baseline.get("source_hashes") or {},
            "reason": "no_source_baseline_spans",
        }
    black = list(baseline.get("black_frames") or []) if repair_source_black else []
    frozen = (
        list(baseline.get("frozen_frames") or [])
        if repair_source_frozen else []
    )
    detected_black = list_black_frames(str(input_path))
    detected_frozen = list_frozen_frames(str(input_path))
    detected_black_spans = (
        [span.model_dump() for span in detected_black.spans]
        if detected_black.ok else []
    )
    detected_frozen_spans = (
        [span.model_dump() for span in detected_frozen.spans]
        if detected_frozen.ok else []
    )
    if repair_intentional_black:
        if detected_black.ok:
            black.extend(detected_black_spans)
        if repair_source_frozen and detected_frozen.ok:
            frozen.extend(detected_frozen_spans)
    else:
        # A source defect only needs repair when it survived the render. This
        # avoids a full RGB decode/encode pass for a source span that the
        # proxy already rendered cleanly.
        if detected_black.ok:
            black = [
                span for span in black
                if _overlaps_any(
                    span,
                    detected_black_spans + (
                        detected_frozen_spans if detected_frozen.ok else []
                    ),
                )
            ]
        if repair_source_frozen and detected_frozen.ok:
            frozen = [
                span for span in frozen
                if _overlaps_any(
                    span,
                    detected_frozen_spans + (
                        detected_black_spans if detected_black.ok else []
                    ),
                )
            ]
    black = _subtract_protected_spans(black, protected)
    frozen = _subtract_protected_spans(frozen, protected)
    if not black and not frozen:
        return {
            "ok": True,
            "changed": False,
            "output_path": str(input_path),
            "repaired_black_spans": [],
            "repaired_frozen_spans": [],
            "protected_spans": [
                {"start_sec": start, "end_sec": end}
                for start, end in protected
            ],
            "source_hashes": baseline.get("source_hashes") or {},
        }
    try:
        width, height, fps = _video_layout(input_path)
        desired_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=f".{desired_path.stem}.repair-",
            suffix=desired_path.suffix or ".mp4",
            dir=desired_path.parent,
            delete=False,
        ) as tmp:
            temp_path = Path(tmp.name)
        spans = _merge_repair_spans(black, frozen, fps)
        _repair_stream(
            input_path, temp_path, width=width, height=height, fps=fps,
            spans=spans,
        )
        os.replace(temp_path, desired_path)
        return {
            "ok": True,
            "changed": True,
            "output_path": str(desired_path),
            "repaired_black_spans": black,
            "repaired_frozen_spans": frozen,
            "protected_spans": [
                {"start_sec": start, "end_sec": end}
                for start, end in protected
            ],
            "source_hashes": baseline.get("source_hashes") or {},
        }
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        try:
            temp_path.unlink(missing_ok=True)
        except (NameError, OSError):
            pass
        return {
            "ok": False,
            "changed": False,
            "output_path": str(input_path),
            "error": str(exc),
            "protected_spans": [
                {"start_sec": start, "end_sec": end}
                for start, end in protected
            ],
            "source_hashes": baseline.get("source_hashes") or {},
        }
