"""Silence cutter skill: propose cuts at inter-word silence gaps.

Per phase4-design-revised.md section 4.2 (W3).

The skill detects silence gaps (leading, inter-word, and trailing) and
returns *policy-filtered* cut suggestions. The policy layer keeps
breaths, merges gaps separated by a tiny speech fragment, and refuses
to produce sub-min speech fragments — so naive application no longer
fragments speech into ~2s clips.

Filler words ("um", "uh") and repeated phrases are speech, not silence,
and are NOT detected here. Removing them requires transcript-text
analysis (see ``narrative_analyzer``); this skill only handles acoustic
silence.
"""
from __future__ import annotations

from typing import Optional

from open_edit.ir.types import Asset, WordAlignment


def find_silence_gaps(
    alignment: list[WordAlignment],
    threshold_ms: int = 400,
    *,
    asset_duration_s: Optional[float] = None,
) -> list[tuple[float, float]]:
    """Find silence gaps longer than or equal to ``threshold_ms``.

    Detects three kinds of silence:

    - **Leading**: ``[0, alignment[0].t_start]``.
    - **Inter-word**: ``[prev.t_end, curr.t_start]`` for each adjacent
      word pair where the gap is at least ``threshold_ms``.
    - **Trailing**: ``[alignment[-1].t_end, asset_duration_s]`` — only
      when ``asset_duration_s`` is provided. Without it, trailing
      silence is skipped (the skill has no way to know the asset's
      duration from the alignment alone).

    Returns a list of ``(gap_start_sec, gap_end_sec)`` tuples in
    increasing source-time order.
    """
    if not alignment:
        return []
    threshold_s = threshold_ms / 1000.0
    gaps: list[tuple[float, float]] = []

    # Leading silence.
    leading = alignment[0].t_start
    if leading >= threshold_s:
        gaps.append((0.0, alignment[0].t_start))

    # Inter-word gaps.
    for prev, curr in zip(alignment, alignment[1:]):
        gap = curr.t_start - prev.t_end
        if gap >= threshold_s:
            gaps.append((prev.t_end, curr.t_start))

    # Trailing silence (only if the asset duration is known).
    if asset_duration_s is not None and asset_duration_s > alignment[-1].t_end:
        trailing = asset_duration_s - alignment[-1].t_end
        if trailing >= threshold_s:
            gaps.append((alignment[-1].t_end, asset_duration_s))

    return gaps


def propose_cuts(
    asset: Asset,
    silence_threshold_ms: int = 400,
    *,
    keep_breath_ms: int = 600,
    min_segment_s: float = 2.0,
) -> list[dict]:
    """Return policy-filtered cut suggestions for ``asset``.

    Each suggestion is a dict::

        {"t_start": float, "t_end": float, "suggested_kind": "trim"}

    The agent decides which ``clip_id`` to attach and whether to apply.
    The skill does not emit IR ops because it does not know which clip
    covers a given source-time range.

    Policy layers applied on top of :func:`find_silence_gaps`:

    1. **Breath-keep** — gaps shorter than ``keep_breath_ms`` are
       treated as breaths and NOT proposed as cuts. Set
       ``keep_breath_ms <= silence_threshold_ms`` to disable.
    2. **Tiny-fragment merge** — two consecutive cuts separated by a
       speech fragment shorter than ``min_segment_s`` are merged into a
       single wider cut (the tiny speech fragment is removed along with
       the surrounding silence). This prevents leaving a 0.3s sliver of
       speech between two cuts.
    3. **Boundary min-segment** — a leading cut that would leave the
       first speech fragment shorter than ``min_segment_s`` is dropped;
       same for a trailing cut. Interior fragments are already
       protected by the merge step.

    The defaults (``keep_breath_ms=600``, ``min_segment_s=2.0``) are
    tuned for talking-head YouTube edits and prevent the over-cutting
    that naive ``gap >= 400ms -> cut`` produces.
    """
    if not asset.alignment:
        return []

    words = asset.alignment
    speech_start = words[0].t_start
    speech_end = words[-1].t_end
    asset_duration = _asset_duration_s(asset)
    if asset_duration is None:
        # Without an explicit duration we cannot detect trailing
        # silence; fall back to the last word's end so the rest of the
        # pipeline still works.
        asset_duration = speech_end

    raw_gaps = find_silence_gaps(
        words, silence_threshold_ms, asset_duration_s=asset_duration,
    )
    if not raw_gaps:
        return []

    # 1. Breath filter.
    keep_breath_s = keep_breath_ms / 1000.0
    candidates = [g for g in raw_gaps if (g[1] - g[0]) >= keep_breath_s]
    if not candidates:
        return []

    # 2. Tiny-fragment merge.
    merged: list[list[float]] = []
    for c_start, c_end in candidates:
        if merged:
            prev_end = merged[-1][1]
            speech_between = c_start - prev_end
            if 0 < speech_between < min_segment_s:
                merged[-1][1] = c_end
                continue
        merged.append([c_start, c_end])

    # 3. Boundary min-segment protection.
    final: list[tuple[float, float]] = []
    for i, cut in enumerate(merged):
        c_start, c_end = cut
        prev_anchor = final[-1][1] if final else speech_start
        pre_len = c_start - prev_anchor
        is_last = i == len(merged) - 1
        post_len = (speech_end - c_end) if is_last else None
        if not final and pre_len < min_segment_s:
            # Leading cut would leave the first fragment too short.
            continue
        if is_last and post_len is not None and post_len < min_segment_s:
            # Trailing cut would leave the last fragment too short.
            continue
        final.append((c_start, c_end))

    return [
        {"t_start": s, "t_end": e, "suggested_kind": "trim"}
        for s, e in final
    ]


def _asset_duration_s(asset: Asset) -> Optional[float]:
    """Best-effort lookup of the asset's duration in seconds.

    Tries the common attribute names used across Asset versions. Returns
    ``None`` if no positive numeric duration is exposed, in which case
    trailing-silence detection is skipped.
    """
    for attr in ("duration", "duration_sec", "duration_s"):
        v = getattr(asset, attr, None)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    return None
