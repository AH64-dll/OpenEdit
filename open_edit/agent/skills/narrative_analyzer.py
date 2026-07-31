"""Narrative analyzer skill: classify transcript segments into beat types.

Per phase4-design-revised.md section 4.1 (W4).

The deterministic path uses sentence-like boundaries in the word alignment
(terminal punctuation, with long pauses as a fallback), not fixed time windows.
It reports the source-time gap after each segment so callers can cut on natural
boundaries. The LLM-backed path is not implemented: ``use_llm=True`` warns and
uses this same deterministic transcript-aligned path; it never claims an LLM
ran. Beat labels remain positional heuristics and should be independently
verified for structural edit decisions.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from open_edit.ir.types import Asset


BEAT_TYPES = ("hook", "turn", "scope", "mechanism", "cost", "tease", "button")


class NarrativeSegment(BaseModel):
    beat_type: Literal["hook", "turn", "scope", "mechanism", "cost", "tease", "button"]
    t_start: float
    t_end: float
    text: str
    suggested_visual_concept: str = ""
    gap_after_s: float = 0.0


def analyze(asset: Asset, use_llm: bool = True) -> list[NarrativeSegment]:
    """Analyze the asset's transcript and return narrative segments.

    With use_llm=True, this warns and uses the deterministic
    transcript-aligned segmentation because no LLM provider is configured.
    With use_llm=False it directly returns that deterministic result.
    """
    if not asset.alignment:
        return []
    if use_llm:
        return _analyze_with_llm(asset)
    return _analyze_rule_based(asset)


def _analyze_rule_based(asset: Asset) -> list[NarrativeSegment]:
    """Segment aligned words at sentence-like boundaries."""
    alignment = asset.alignment
    if not alignment:
        return []
    groups: list[list] = []
    current: list = []
    for word in alignment:
        # Transcripts without punctuation still expose sense boundaries through
        # substantial pauses (and this keeps long-form assets segmented).
        if current and word.t_start - current[-1].t_end >= 0.6:
            groups.append(current)
            current = []
        current.append(word)
        token = word.word.rstrip()
        if token.endswith((".", "!", "?", "。", "！", "？")):
            groups.append(current)
            current = []
    if current:
        groups.append(current)

    segments = []
    for i, words in enumerate(groups):
        if i == 0:
            beat = "hook"
        elif i == len(groups) - 1:
            beat = "button"
        elif i == 1:
            beat = "turn"
        elif i == 2:
            beat = "scope"
        else:
            beat = "mechanism"
        gap_after_s = (
            max(0.0, groups[i + 1][0].t_start - words[-1].t_end)
            if i + 1 < len(groups)
            else 0.0
        )
        segments.append(NarrativeSegment(
            beat_type=beat,
            t_start=words[0].t_start,
            t_end=words[-1].t_end,
            text=" ".join(w.word for w in words),
            gap_after_s=gap_after_s,
        ))
    return segments


def _analyze_with_llm(asset: Asset) -> list[NarrativeSegment]:
    """LLM-backed beat classification.

    NOT IMPLEMENTED. Warns and returns the rule-based fallback so callers
    do not silently believe they received intelligent analysis.
    """
    import warnings
    warnings.warn(
        "LLM-based narrative analysis is not implemented; returning "
        "rule-based fallback (beat types are positional heuristics, not "
        "a real analysis)."
    )
    return _analyze_rule_based(asset)
