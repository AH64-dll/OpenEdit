"""Silence cutter skill: propose cuts at silence gaps.

Per phase4-design-revised.md section 4.2 (W3).

Detects three kinds of silence:
- leading silence:  [0.0, first_word.t_start]
- inter-word gaps:  [prev_word.t_end, next_word.t_start]
- trailing silence: [last_word.t_end, asset.duration_sec]

Adjacent gaps separated by a speech segment shorter than ``min_segment_s``
are merged, so very short speech fragments are not proposed as cuts (this
prevents the "hyper-choppy" edit that fragments speech into sub-2s clips).
The default policy keeps breaths shorter than 600ms and protects sub-2s
speech fragments.
"""
from __future__ import annotations

from open_edit.ir.types import Asset, WordAlignment


def find_silence_gaps(
    alignment: list[WordAlignment],
    threshold_ms: int = 400,
    duration: float | None = None,
    min_segment_s: float = 0.0,
    keep_breath_ms: int = 0,
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
    # Catch candidate pauses while preserving natural breaths by default.
    threshold_s = max(threshold_ms, keep_breath_ms) / 1000.0
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


# ---------------------------------------------------------------------------
# Filler-word detection (video-use merge: verbatim filler cutting)
# ---------------------------------------------------------------------------

# Conservative filler vocabulary. Whisper keeps fillers verbatim when
# normalization is off, so these appear as ordinary tokens. "like" and
# "you know" are intentionally NOT in the conservative set — they are often
# content words; enable them explicitly with include_contextual=True.
FILLER_WORDS: frozenset[str] = frozenset({
    "um", "uh", "umm", "ummm", "uhh", "uhhh", "hmm", "hmmm", "mm", "mhm",
    "mm-hmm", "uh-huh", "uhhuh", "er", "erm", "ah", "eh", "hm",
})

# Contextual fillers: only treated as fillers when flanked by silence
# (pause >= CONTEXTUAL_PAUSE_MS on both sides or at an utterance edge).
CONTEXTUAL_FILLERS: frozenset[str] = frozenset({"like", "you", "know", "basically", "actually"})
CONTEXTUAL_PAUSE_MS: int = 150


def _norm_token(word: str) -> str:
    """Lowercase and strip punctuation for filler matching."""
    return word.strip().strip(".,!?;:()\"\'").lower()


def find_filler_spans(
    alignment: list[WordAlignment],
    include_contextual: bool = False,
    min_confidence: float = 0.0,
) -> list[tuple[float, float]]:
    """Find filler-word spans (source time) to cut.

    Returns merged (start, end) spans covering consecutive filler tokens,
    mirroring how silence gaps are expressed. ``min_confidence`` can be used
    to skip low-confidence Whisper tokens when false positives are costly
    (note: Whisper often assigns LOW confidence to genuine fillers, so the
    default 0.0 keeps detection aggressive).

    Contextual fillers ("like", "you know", ...) are only included when
    ``include_contextual=True`` AND they are flanked by a pause of at least
    ``CONTEXTUAL_PAUSE_MS`` or sit at the very start/end of the take.
    """
    if not alignment:
        return []
    spans: list[tuple[float, float]] = []
    for i, w in enumerate(alignment):
        token = _norm_token(w.word)
        if not token:
            continue
        if w.confidence is not None and w.confidence < min_confidence:
            continue
        is_filler = token in FILLER_WORDS
        if not is_filler and include_contextual and token in CONTEXTUAL_FILLERS:
            pause_before = (
                w.t_start if i == 0 else w.t_start - alignment[i - 1].t_end
            )
            pause_after = (
                0.0 if i == len(alignment) - 1 else alignment[i + 1].t_start - w.t_end
            )
            at_edge = i == 0 or i == len(alignment) - 1
            if at_edge or (
                pause_before >= CONTEXTUAL_PAUSE_MS / 1000.0
                and pause_after >= CONTEXTUAL_PAUSE_MS / 1000.0
            ):
                is_filler = True
        if is_filler:
            if spans and w.t_start <= spans[-1][1] + 0.35:
                # merge adjacent/close fillers into one removable span
                spans[-1] = (spans[-1][0], max(spans[-1][1], w.t_end))
            else:
                spans.append((w.t_start, w.t_end))
    return spans


def propose_cuts(
    asset: Asset,
    silence_threshold_ms: int = 400,
    min_segment_s: float = 2.0,
    keep_breath_ms: int = 600,
    include_fillers: bool = False,
    filler_min_confidence: float = 0.0,
) -> list[dict]:
    """Return gap-based cut suggestions for `asset`.

    Each suggestion is a dict::

        {"t_start": float, "t_end": float, "suggested_kind": "trim",
         "reason": "silence" | "filler"}

    With ``include_fillers=True``, filler-word spans are merged into the
    gap list (they are removable intervals like silences).
    """
    if not asset.alignment:
        return []
    gaps = find_silence_gaps(
        asset.alignment,
        threshold_ms=silence_threshold_ms,
        duration=getattr(asset, "duration_sec", None),
        min_segment_s=min_segment_s,
        keep_breath_ms=keep_breath_ms,
    )
    spans: list[tuple[float, float]] = [(g[0], g[1], "silence") for g in gaps]
    if include_fillers:
        for fs, fe in find_filler_spans(
            asset.alignment, include_contextual=True, min_confidence=filler_min_confidence
        ):
            spans.append((fs, fe, "filler"))
    spans.sort(key=lambda x: x[0])
    merged: list[tuple[float, float, str]] = []
    for start, end, reason in spans:
        if merged and start <= merged[-1][1] + 0.05:
            # merge overlapping/adjacent; prefer keeping the first reason
            if end > merged[-1][1]:
                merged[-1] = (merged[-1][0], end, merged[-1][2])
        else:
            merged.append((start, end, reason))
    return [
        {"t_start": t_start, "t_end": t_end, "suggested_kind": "trim", "reason": reason}
        for t_start, t_end, reason in merged
    ]


def no_word_split_check(
    asset: Asset, t_start: float, t_end: float, tolerance_ms: int = 50,
) -> tuple[bool, str]:
    """Check if a cut at [t_start, t_end] splits any word.

    A cut splits a word if either endpoint falls strictly inside the
    word's time range, leaving `tolerance_ms` of slack at each edge so
    that a cut exactly on a word boundary still passes.

    Returns (passed, detail). passed=True means no word is split.
    """
    tolerance_s = tolerance_ms / 1000.0
    for w in asset.alignment:
        if (w.t_start + tolerance_s) < t_start < (w.t_end - tolerance_s):
            return False, f"Cut at {t_start}s splits word '{w.word}' ({w.t_start}s - {w.t_end}s)"
        if (w.t_start + tolerance_s) < t_end < (w.t_end - tolerance_s):
            return False, f"Cut at {t_end}s splits word '{w.word}' ({w.t_start}s - {w.t_end}s)"
    return True, "no word split"
