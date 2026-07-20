"""Silence cutter skill: propose cuts at inter-word silence gaps.

Per phase4-design-revised.md section 4.2 (W3).
"""
from __future__ import annotations

from open_edit.ir.types import Asset, WordAlignment


def find_silence_gaps(
    alignment: list[WordAlignment], threshold_ms: int = 400,
) -> list[tuple[float, float]]:
    """Find inter-word gaps longer than or equal to threshold_ms.

    Returns a list of (gap_start_sec, gap_end_sec) tuples in source time.
    """
    threshold_s = threshold_ms / 1000.0
    gaps: list[tuple[float, float]] = []
    for prev, curr in zip(alignment, alignment[1:]):
        gap = curr.t_start - prev.t_end
        if gap >= threshold_s:
            gaps.append((prev.t_end, curr.t_start))
    return gaps


def propose_cuts(
    asset: Asset, silence_threshold_ms: int = 400,
) -> list[dict]:
    """Return gap-based cut suggestions for `asset`.

    Each suggestion is a dict::

        {"t_start": float, "t_end": float, "suggested_kind": "trim"}

    The agent decides which `clip_id` to attach and whether to apply.
    We don't emit full IR ops here because the skill doesn't know which
    clip covers a given source-time range.
    """
    if not asset.alignment:
        return []
    return [
        {"t_start": t_start, "t_end": t_end, "suggested_kind": "trim"}
        for t_start, t_end in find_silence_gaps(asset.alignment, silence_threshold_ms)
    ]
