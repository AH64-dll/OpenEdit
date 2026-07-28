"""Phase 4.5 W3: silence cutter skill."""
import pytest

from open_edit.ir.types import Asset, WordAlignment
from open_edit.agent.skills.silence_cutter import propose_cuts, find_silence_gaps


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
    gaps = find_silence_gaps(alignment, threshold_ms=400)
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
    gaps = find_silence_gaps(alignment, threshold_ms=400)
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
    assert len(cuts) == 1


def test_no_word_split_qc_check_mid_word_fails():
    """The QC check should reject cuts that split a word."""
    from open_edit.qc.gate import no_word_split_check
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
    from open_edit.qc.gate import no_word_split_check
    asset = _make_asset([
        WordAlignment(word="hello", t_start=0.0, t_end=0.5, confidence=1.0),
    ])
    # Cut at 0.5 (inter-word) should pass
    passed, detail = no_word_split_check(asset, t_start=0.5, t_end=1.0)
    assert passed is True
