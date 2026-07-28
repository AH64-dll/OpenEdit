"""Narrative analyzer skill: segment a transcript into narrative beats.

The default path is **rule-based** and produces SENTENCE-ALIGNED segments
with POSITIONAL beat labels (``hook`` / ``turn`` / ``scope`` /
``mechanism`` / ``button``). The labels are heuristics — they tell the
agent where each segment sits in the narrative arc, not what it
semantically means. Use them for cut-boundary hints and visual-concept
suggestions, not for structural reordering.

A true LLM-based classifier is NOT implemented. ``use_llm=True`` is
accepted for forward compatibility but currently routes to the same
rule-based path with a warning. The ``cost`` and ``tease`` labels are
reserved for the future LLM path and are not emitted by the rule-based
classifier.

Per phase4-design-revised.md section 4.1 (W4).
"""
from __future__ import annotations

import warnings
from typing import Literal, Optional

from pydantic import BaseModel

from open_edit.ir.types import Asset, WordAlignment


BEAT_TYPES = ("hook", "turn", "scope", "mechanism", "cost", "tease", "button")

# Default pause (in ms) above which the gap between two words is treated
# as a segment boundary even without terminal punctuation.
_SENTENCE_BREAK_MS = 350


class NarrativeSegment(BaseModel):
    beat_type: Literal[
        "hook", "turn", "scope", "mechanism", "cost", "tease", "button"
    ]
    t_start: float
    t_end: float
    text: str
    suggested_visual_concept: str = ""
    # Silence (in seconds) between this segment's end and the next
    # segment's start. ``None`` on the last segment. The agent can use
    # this to decide where to cut without re-querying the alignment.
    gap_after_s: Optional[float] = None


# Force pydantic to resolve the Literal annotation now (it would
# otherwise be a lazy forward reference under PEP 563). No-op if the
# model is already fully defined.
NarrativeSegment.model_rebuild()


def analyze(asset: Asset, use_llm: bool = False) -> list[NarrativeSegment]:
    """Analyze the asset's transcript and return narrative segments.

    Segments are sentence-aligned: a segment ends at terminal punctuation
    (``.`` ``!`` ``?``) or at an inter-word pause longer than ~350ms.

    Beat labels are positional:

    - first segment  -> ``hook``
    - second segment -> ``turn``
    - third segment  -> ``scope``
    - last segment   -> ``button``
    - any other      -> ``mechanism`` (catch-all)

    The ``cost`` and ``tease`` labels are reserved for future LLM
    classification and are not emitted by the rule-based path.

    Each segment also carries ``gap_after_s``: the silence (in seconds)
    between this segment's end and the next segment's start. The agent
    can use this to decide where to cut without re-querying the
    alignment — segments with a large ``gap_after_s`` are natural cut
    candidates (see :mod:`open_edit.agent.skills.silence_cutter`).

    ``use_llm=True`` is accepted for forward compatibility but currently
    routes to the rule-based path with a warning. Do not enable it
    expecting semantic classification.
    """
    if not asset.alignment:
        return []
    if use_llm:
        warnings.warn(
            "narrative_analyzer.use_llm=True is not implemented; "
            "falling back to rule-based segmentation. Beat labels are "
            "positional heuristics, not semantic classifications.",
            stacklevel=2,
        )
    return _analyze_rule_based(asset)


def _is_sentence_terminator(word: str) -> bool:
    """True if the word ends with terminal punctuation."""
    return word.endswith((".", "!", "?"))


def _segment_by_sentence(
    alignment: list[WordAlignment],
    break_ms: int = _SENTENCE_BREAK_MS,
) -> list[tuple[float, float, str]]:
    """Group words into sentence-like segments.

    A segment ends when (a) a word ends with terminal punctuation
    (``.`` ``!`` ``?``), or (b) the inter-word pause to the next word
    exceeds ``break_ms``.

    Returns a list of ``(t_start, t_end, text)`` tuples.
    """
    if not alignment:
        return []
    segments: list[tuple[float, float, str]] = []
    break_s = break_ms / 1000.0

    seg_start = alignment[0].t_start
    seg_words: list[str] = []
    seg_end = alignment[0].t_end

    for i, w in enumerate(alignment):
        seg_words.append(w.word)
        seg_end = w.t_end
        is_break = _is_sentence_terminator(w.word)
        if not is_break and i + 1 < len(alignment):
            nxt = alignment[i + 1]
            if nxt.t_start - w.t_end >= break_s:
                is_break = True
        if is_break:
            text = " ".join(seg_words).strip()
            if text:
                segments.append((seg_start, seg_end, text))
            seg_words = []  # always clear after a flush
            if i + 1 < len(alignment):
                seg_start = alignment[i + 1].t_start
                seg_end = alignment[i + 1].t_end

    # Flush trailing words that did not end with a terminator.
    if seg_words:
        text = " ".join(seg_words).strip()
        if text:
            segments.append((seg_start, seg_end, text))
    return segments


def _label_by_position(index: int, total: int) -> str:
    """Positional beat label. See :func:`analyze` for the mapping."""
    if total <= 0:
        return "mechanism"
    if index == 0:
        return "hook"
    if index == total - 1:
        return "button"
    if index == 1:
        return "turn"
    if index == 2:
        return "scope"
    return "mechanism"


def _analyze_rule_based(asset: Asset) -> list[NarrativeSegment]:
    alignment = asset.alignment
    if not alignment:
        return []
    raw = _segment_by_sentence(alignment)
    if not raw:
        return []
    total = len(raw)
    out: list[NarrativeSegment] = []
    for i, (t_start, t_end, text) in enumerate(raw):
        gap_after = raw[i + 1][0] - t_end if i + 1 < total else None
        out.append(
            NarrativeSegment(
                beat_type=_label_by_position(i, total),
                t_start=t_start,
                t_end=t_end,
                text=text,
                gap_after_s=gap_after,
            )
        )
    return out
