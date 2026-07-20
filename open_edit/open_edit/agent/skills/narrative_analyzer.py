"""Narrative analyzer skill: classify transcript segments into 7 beat types.

Per phase4-design-revised.md section 4.1 (W4).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from open_edit.ir.types import Asset, WordAlignment


BEAT_TYPES = ("hook", "turn", "scope", "mechanism", "cost", "tease", "button")


class NarrativeSegment(BaseModel):
    beat_type: Literal["hook", "turn", "scope", "mechanism", "cost", "tease", "button"]
    t_start: float
    t_end: float
    text: str
    suggested_visual_concept: str = ""


def analyze(asset: Asset, use_llm: bool = True) -> list[NarrativeSegment]:
    """Analyze the asset's transcript and return narrative segments.

    With use_llm=True, calls the LLM to classify beats.
    With use_llm=False, falls back to a simple rule-based segmentation
    that produces one segment per ~5 seconds of transcript, classified
    by position (first -> hook, last -> button, middle -> mechanism).
    """
    if not asset.alignment:
        return []
    if use_llm:
        return _analyze_with_llm(asset)
    return _analyze_rule_based(asset)


def _analyze_rule_based(asset: Asset) -> list[NarrativeSegment]:
    """Simple rule-based fallback: segment by 5s windows, classify by position."""
    segments = []
    alignment = asset.alignment
    window_s = 5.0
    if not alignment:
        return []
    t_start_anchor = alignment[0].t_start
    t_end_anchor = alignment[-1].t_end
    duration = t_end_anchor - t_start_anchor
    if duration == 0:
        return []
    n_windows = max(1, int(duration / window_s))
    window_size = duration / n_windows
    for i in range(n_windows):
        w_start = t_start_anchor + i * window_size
        w_end = t_start_anchor + (i + 1) * window_size
        words_in_window = [w for w in alignment if w.t_start >= w_start and w.t_end <= w_end]
        if not words_in_window:
            continue
        text = " ".join(w.word for w in words_in_window)
        if i == 0:
            beat = "hook"
        elif i == n_windows - 1:
            beat = "button"
        elif i == 1:
            beat = "turn"
        elif i == 2:
            beat = "scope"
        else:
            beat = "mechanism"
        segments.append(NarrativeSegment(
            beat_type=beat, t_start=w_start, t_end=w_end, text=text,
        ))
    return segments


def _analyze_with_llm(asset: Asset) -> list[NarrativeSegment]:
    """Call the LLM to classify beats.

    Implementation note: the actual LLM call is out of scope for v1; this
    function is a stub that returns the rule-based result with a warning.
    Future: route through the agent loop (e.g., pyagent_run_python that
    emits NarrativeSegment + AddClipOp).
    """
    import warnings
    warnings.warn("LLM-based narrative analysis is not yet implemented; using rule-based fallback")
    return _analyze_rule_based(asset)
