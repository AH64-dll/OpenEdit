"""Phase 4.5 W4: narrative analyzer skill."""
import pytest
from open_edit.ir.types import Asset, WordAlignment
from open_edit.agent.skills.narrative_analyzer import analyze, BEAT_TYPES


def test_beat_types_complete():
    """The 7 spec beat types are all present."""
    assert set(BEAT_TYPES) == {"hook", "turn", "scope", "mechanism", "cost", "tease", "button"}


def test_analyze_with_rule_based_fallback():
    """Without an LLM, analyze falls back to a simple rule-based segmentation."""
    asset = Asset(
        asset_hash="abc",
        original_path="/tmp/x.mp4",
        stored_path="/tmp/x",
        type="video",
        duration_sec=10.0,
        fps=30.0, width=1920, height=1080, codec="h264", has_audio=True,
        alignment=[
            WordAlignment(word="hello", t_start=0.0, t_end=0.5, confidence=1.0),
            WordAlignment(word="world", t_start=0.5, t_end=1.0, confidence=1.0),
        ],
    )
    segments = analyze(asset, use_llm=False)
    assert len(segments) >= 1
    for s in segments:
        assert s.beat_type in BEAT_TYPES


def test_narrative_segment_pydantic():
    from open_edit.agent.skills.narrative_analyzer import NarrativeSegment
    s = NarrativeSegment(
        beat_type="hook",
        t_start=0.0,
        t_end=3.0,
        text="Welcome",
        suggested_visual_concept="Cold open with logo",
    )
    assert s.beat_type == "hook"


def test_analyze_aligns_to_sentence_boundaries_and_reports_gaps():
    asset = Asset(
        asset_hash="abc",
        original_path="/tmp/x.mp4",
        stored_path="/tmp/x",
        type="video",
        duration_sec=8.0,
        fps=30.0, width=1920, height=1080, codec="h264", has_audio=True,
        alignment=[
            WordAlignment(word="First", t_start=0.0, t_end=0.4, confidence=1.0),
            WordAlignment(word="sentence.", t_start=0.4, t_end=1.0, confidence=1.0),
            WordAlignment(word="Second", t_start=2.2, t_end=2.6, confidence=1.0),
            WordAlignment(word="idea!", t_start=2.6, t_end=3.0, confidence=1.0),
        ],
    )
    segments = analyze(asset, use_llm=False)
    assert [(s.t_start, s.t_end, s.text) for s in segments] == [
        (0.0, 1.0, "First sentence."),
        (2.2, 3.0, "Second idea!"),
    ]
    assert segments[0].gap_after_s == pytest.approx(1.2)
    assert segments[1].gap_after_s == 0.0
