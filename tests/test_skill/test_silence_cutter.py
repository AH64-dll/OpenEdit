"""Phase 4.5 W3: silence cutter skill."""
import pytest

from open_edit.ir.types import Asset, WordAlignment
from open_edit.agent.skills.silence_cutter import (
    find_silence_gaps,
    no_word_split_check,
    propose_cuts,
)


def _make_asset(alignment, duration_sec=10.0):
    return Asset(
        asset_hash="abc",
        original_path="/tmp/x.mp4",
        stored_path="/tmp/x",
        type="video",
        duration_sec=duration_sec,
        fps=30.0, width=1920, height=1080, codec="h264", has_audio=True,
        alignment=alignment,
    )


def test_find_silence_gaps():
    """Given word-level alignment, find gaps > 400ms."""
    alignment = [
        WordAlignment(word="hello", t_start=0.0, t_end=0.5, confidence=1.0),
        WordAlignment(word="world", t_start=1.5, t_end=2.0, confidence=1.0),
        WordAlignment(word="foo", t_start=2.1, t_end=2.5, confidence=1.0),
    ]
    gaps = find_silence_gaps(alignment, threshold_ms=400, keep_breath_ms=0)
    # 0.5 -> 1.5 = 1.0s gap (yes), 2.0 -> 2.1 = 0.1s gap (no)
    assert len(gaps) == 1
    assert gaps[0] == (0.5, 1.5)


def test_find_silence_gaps_threshold_exact():
    """A gap exactly equal to threshold is included."""
    alignment = [
        WordAlignment(word="a", t_start=0.0, t_end=0.6, confidence=1.0),
        WordAlignment(word="b", t_start=1.0, t_end=1.5, confidence=1.0),
    ]
    # 0.6 -> 1.0 = 0.4s gap (== threshold_ms=400)
    gaps = find_silence_gaps(alignment, threshold_ms=400, keep_breath_ms=0)
    assert len(gaps) == 1
    assert gaps[0] == (0.6, 1.0)


def test_propose_cuts_emits_gaps():
    """propose_cuts returns dict gaps with t_start/t_end/suggested_kind."""
    asset = _make_asset([
        WordAlignment(word="hello", t_start=0.0, t_end=0.5, confidence=1.0),
        WordAlignment(word="world", t_start=1.5, t_end=2.0, confidence=1.0),
    ], duration_sec=2.0)
    cuts = propose_cuts(asset, silence_threshold_ms=400)
    assert len(cuts) == 1
    assert cuts[0]["t_start"] == 0.5
    assert cuts[0]["t_end"] == 1.5
    assert cuts[0]["suggested_kind"] == "trim"


def test_propose_cuts_no_alignment_returns_empty():
    """If asset has no alignment, return empty list (no cuts)."""
    asset = _make_asset([])
    cuts = propose_cuts(asset, silence_threshold_ms=400)
    assert cuts == []


def test_propose_cuts_default_threshold():
    """Default threshold is 400ms."""
    asset = _make_asset([
        WordAlignment(word="a", t_start=0.0, t_end=0.5, confidence=1.0),
        WordAlignment(word="b", t_start=1.0, t_end=1.5, confidence=1.0),
    ], duration_sec=1.5)
    # 0.5 -> 1.0 = 0.5s gap, exceeds default 400ms
    cuts = propose_cuts(asset)
    # The default policy preserves sub-600ms breaths.
    assert cuts == []


def test_propose_cuts_keeps_breath_but_allows_long_pause():
    asset = _make_asset([
        WordAlignment(word="a", t_start=0.0, t_end=0.5, confidence=1.0),
        WordAlignment(word="b", t_start=1.0, t_end=1.2, confidence=1.0),
        WordAlignment(word="c", t_start=2.5, t_end=2.7, confidence=1.0),
    ], duration_sec=2.7)
    cuts = propose_cuts(asset)
    assert [(c["t_start"], c["t_end"]) for c in cuts] == [(1.2, 2.5)]


def test_no_word_split_qc_check_mid_word_fails():
    """The QC check should reject cuts that split a word."""
    asset = _make_asset([
        WordAlignment(word="hello", t_start=0.0, t_end=0.5, confidence=1.0),
    ])
    # Cut at 0.25 (mid-word) should fail
    passed, detail = no_word_split_check(asset, t_start=0.25, t_end=0.75)
    assert passed is False
    assert "word" in detail.lower()


def test_leading_silence_detected():
    """Silence before the first word is reported when duration is unknown."""
    alignment = [
        WordAlignment(word="hello", t_start=1.0, t_end=1.5, confidence=1.0),
        WordAlignment(word="world", t_start=2.5, t_end=3.0, confidence=1.0),
    ]
    gaps = find_silence_gaps(alignment, threshold_ms=400)
    # leading (0 -> 1.0) + inter-word (1.5 -> 2.5)
    assert (0.0, 1.0) in gaps
    assert (1.5, 2.5) in gaps


def test_trailing_silence_detected_with_duration():
    """Silence after the last word is reported when duration is provided."""
    alignment = [
        WordAlignment(word="hello", t_start=0.0, t_end=0.5, confidence=1.0),
        WordAlignment(word="world", t_start=1.5, t_end=2.0, confidence=1.0),
    ]
    gaps = find_silence_gaps(alignment, threshold_ms=400, duration=5.0)
    assert (2.0, 5.0) in gaps


def test_merge_protects_short_speech():
    """Gaps separated by speech shorter than min_segment_s are merged."""
    alignment = [
        WordAlignment(word="a", t_start=0.0, t_end=0.5, confidence=1.0),
        WordAlignment(word="b", t_start=1.0, t_end=1.2, confidence=1.0),  # short word
        WordAlignment(word="c", t_start=1.8, t_end=2.3, confidence=1.0),
    ]
    # gap1 (0.5 -> 1.0, 0.5s); short speech b (1.0 -> 1.2, 0.2s);
    # gap2 (1.2 -> 1.8, 0.6s). With min_segment_s=0.5 the 0.2s speech merges
    # the two gaps into one (0.5 -> 1.8).
    gaps = find_silence_gaps(alignment, threshold_ms=400, duration=2.3, min_segment_s=0.5)
    assert gaps == [(0.5, 1.8)]


def test_no_word_split_qc_check_inter_word_passes():
    """The QC check should accept cuts at inter-word boundaries."""
    asset = _make_asset([
        WordAlignment(word="hello", t_start=0.0, t_end=0.5, confidence=1.0),
    ])
    # Cut at 0.5 (inter-word) should pass
    passed, detail = no_word_split_check(asset, t_start=0.5, t_end=1.0)
    assert passed is True


def test_no_word_split_reexported_from_gate():
    """qc.gate keeps a thin re-export for backward compatibility."""
    from open_edit.agent.skills.silence_cutter import no_word_split_check as canonical
    from open_edit.qc.gate import no_word_split_check as reexported

    assert reexported is canonical


# =========================================================================
# Video-use merge: filler detection + word-boundary snapping + padding
# =========================================================================


def _wa(word, t_start, t_end, confidence=1.0):
    return WordAlignment(word=word, t_start=t_start, t_end=t_end, confidence=confidence)


def test_find_filler_spans_basic():
    from open_edit.agent.skills.silence_cutter import find_filler_spans

    al = [
        _wa("uh", 1.0, 1.3),
        _wa("hello", 1.5, 2.0),
        _wa("there", 2.1, 2.6),
        _wa("um", 3.0, 3.4),
        _wa("world", 4.0, 4.5),
    ]
    spans = find_filler_spans(al)
    assert spans == [(1.0, 1.3), (3.0, 3.4)]


def test_find_filler_spans_merges_adjacent():
    from open_edit.agent.skills.silence_cutter import find_filler_spans

    al = [_wa("uh", 1.0, 1.3), _wa("um", 1.35, 1.7), _wa("hello", 2.0, 2.5)]
    assert find_filler_spans(al) == [(1.0, 1.7)]


def test_contextual_filler_requires_pauses():
    from open_edit.agent.skills.silence_cutter import find_filler_spans

    # "like" surrounded by speech without pauses -> NOT a filler
    al = [_wa("i", 0.0, 0.3), _wa("like", 0.35, 0.6), _wa("pizza", 0.7, 1.1)]
    assert find_filler_spans(al, include_contextual=True) == []
    # "like" flanked by 300ms pauses -> filler
    al2 = [_wa("i", 0.0, 0.3), _wa("like", 0.8, 1.1), _wa("pizza", 1.5, 1.9)]
    spans = find_filler_spans(al2, include_contextual=True)
    assert len(spans) == 1 and abs(spans[0][0] - 0.8) < 1e-6


def test_propose_cuts_merges_fillers_into_gaps():
    al = [
        _wa("uh", 0.5, 0.8),
        _wa("hello", 1.0, 1.5),
        _wa("world", 2.5, 3.0),
        _wa("um", 3.05, 3.3),
        _wa("foo", 4.0, 4.5),
    ]
    asset = _make_asset(al)
    cuts = propose_cuts(asset, silence_threshold_ms=400, include_fillers=True)
    reasons = [c["reason"] for c in cuts]
    assert "filler" in reasons
    assert all(c["suggested_kind"] == "trim" for c in cuts)
    # filler span (0.5,0.8) survives as its own cut
    filler_cuts = [c for c in cuts if c["reason"] == "filler"]
    assert any(abs(c["t_start"] - 0.5) < 1e-6 for c in filler_cuts)


def test_no_word_split_check_still_guards():
    al = [_wa("hello", 1.0, 2.0)]
    asset = _make_asset(al)
    passed, _ = no_word_split_check(asset, 1.5, 3.0)
    assert not passed
    passed, _ = no_word_split_check(asset, 0.9, 2.05)
    assert passed


def test_snap_edge_to_word():
    from open_edit.agent.tools.pyagent_timeline_ops import _snap_edge_to_word

    al = [_wa("hello", 1.0, 2.0), _wa("world", 2.5, 3.5)]
    # start edge inside "hello" snaps down to word start
    assert _snap_edge_to_word(al, 1.4, direction="start", tolerance_s=0.5,
                              clamp_low=0.0, clamp_high=3.0) == 1.0
    # end edge inside "world" snaps up to word end
    assert _snap_edge_to_word(al, 3.2, direction="end", tolerance_s=0.5,
                              clamp_low=0.0, clamp_high=4.0) == 3.5
    # far from any boundary -> unchanged
    assert _snap_edge_to_word(al, 0.2, direction="start", tolerance_s=0.5,
                              clamp_low=0.0, clamp_high=3.0) == 0.2


def test_pad_and_snap_keeps_expands_and_merges():
    from open_edit.agent.tools.pyagent_timeline_ops import _pad_and_snap_keeps

    al = [_wa("a", 1.0, 1.3), _wa("b", 2.0, 2.3), _wa("c", 3.0, 3.3)]
    keeps = [(1.0, 3.3)]
    out = _pad_and_snap_keeps(keeps, 0.0, 5.0, al, padding_ms=80, snap_to_words=True)
    # 1.0 stays (word boundary), 3.3 stays; padded out by 80ms
    assert out == [(0.92, 3.38)]
    # overlapping keeps merge
    out2 = _pad_and_snap_keeps([(1.0, 2.0), (1.95, 3.0)], 0.0, 5.0, al,
                               padding_ms=100, snap_to_words=False)
    assert len(out2) == 1 and abs(out2[0][0] - 0.9) < 1e-6 and abs(out2[0][1] - 3.1) < 1e-6
