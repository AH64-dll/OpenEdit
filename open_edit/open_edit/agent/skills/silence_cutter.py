"""Silence cutter skill: propose cuts at silence gaps.

Per phase4-design-revised.md section 4.2 (W3).

Detects three kinds of silence:
- leading silence:  [0.0, first_word.t_start]
- inter-word gaps:  [prev_word.t_end, next_word.t_start]
- trailing silence: [last_word.t_end, asset.duration_sec]

Adjacent gaps separated by a speech segment shorter than ``min_segment_s``
are merged, so very short speech fragments are not proposed as cuts (this
prevents the "hyper-choppy" edit that fragments speech into sub-2s clips).
"""
from __future__ import annotations

from open_edit.ir.types import Asset, WordAlignment


def find_silence_gaps(
    alignment: list[WordAlignment],
    threshold_ms: int = 400,
    duration: float | None = None,
    min_segment_s: float = 0.0,
) -> list[tuple[float, float]]:
    """Find silence intervals >= ``threshold_ms`` in source time.

    Returns a list of (gap_start_sec, gap_end_sec) tuples. Includes leading
    and trailing silence (when ``duration`` is provided) in addition to
    inter-word gaps. When ``min_segment_s`` > 0, gaps separated by a speech
    segment shorter than that are merged into one larger gap.

    Args:
        alignment: word-level alignment.
        threshold_ms: minimum silence length to report.
        duration: asset duration in seconds (enables trailing-silence detection).
        min_segment_s: merge gaps whose separating speech is shorter than this.
    """
    if not alignment:
        return []
    threshold_s = threshold_ms / 1000.0
    gaps: list[tuple[float, float]] = []

    first = alignment[0]
    last = alignment[-1]

    # Leading silence [0, first word start]
    if first.t_start >= threshold_s:
        gaps.append((0.0, first.t_start))

    # Inter-word gaps
    for prev, curr in zip(alignment, alignment[1:]):
        gap = curr.t_start - prev.t_end
        if gap >= threshold_s:
            gaps.append((prev.t_end, curr.t_start))

    # Trailing silence [last word end, duration]
    if duration is not None and duration - last.t_end >= threshold_s:
        gaps.append((last.t_end, duration))

    # Merge gaps separated by speech shorter than min_segment_s
    if min_segment_s > 0.0 and len(gaps) > 1:
        merged: list[tuple[float, float]] = [gaps[0]]
        for g in gaps[1:]:
            if g[0] - merged[-1][1] < min_segment_s:
                merged[-1] = (merged[-1][0], g[1])
            else:
                merged.append(g)
        gaps = merged

    return gaps


def propose_cuts(
    asset: Asset,
    silence_threshold_ms: int = 400,
    min_segment_s: float = 0.0,
) -> list[dict]:
    """Return gap-based cut suggestions for `asset`.

    Each suggestion is a dict::

        {"t_start": float, "t_end": float, "suggested_kind": "trim"}

    The agent decides which `clip_id` to attach and whether to apply.
    We don't emit full IR ops here because the skill doesn't know which
    clip covers a given source-time range.

    Args:
        asset: the asset to analyze (must have word-level ``alignment``).
        silence_threshold_ms: minimum silence length to report.
        min_segment_s: merge gaps separated by speech shorter than this,
            protecting short speech fragments from being cut.
    """
    if not asset.alignment:
        return []
    gaps = find_silence_gaps(
        asset.alignment,
        threshold_ms=silence_threshold_ms,
        duration=getattr(asset, "duration_sec", None),
        min_segment_s=min_segment_s,
    )
    return [
        {"t_start": t_start, "t_end": t_end, "suggested_kind": "trim"}
        for t_start, t_end in gaps
    ]
