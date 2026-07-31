"""Phase 4 Task 3: tag-gated style profile retrieval."""
import json

from open_edit.style.retrieve import get_slice
from open_edit.storage.config import get_profile_path


def _write_profile(tmp_path, monkeypatch, *, transitions_confidence: float, examples: list | None = None):
    monkeypatch.setenv("HOME", str(tmp_path))
    profile = json.loads(get_profile_path().read_text())
    profile["transitions"]["confidence"] = transitions_confidence
    if examples is not None:
        profile["transitions"]["examples"] = examples
    get_profile_path().write_text(json.dumps(profile))


def test_get_slice_add_transition(tmp_path, monkeypatch):
    _write_profile(tmp_path, monkeypatch, transitions_confidence=1.0)
    slice_data = get_slice("AddTransition")
    assert "transitions" in slice_data
    assert "corrections" in slice_data  # Always included


def test_get_slice_omits_low_confidence(tmp_path, monkeypatch):
    """Per spec section 8.8: below confidence 0.2, category is omitted."""
    _write_profile(tmp_path, monkeypatch, transitions_confidence=0.1)
    slice_data = get_slice("AddTransition")
    # transitions confidence is 0.1, should be omitted
    assert "transitions" not in slice_data
    # corrections is always included
    assert "corrections" in slice_data


def test_get_slice_token_cap(tmp_path, monkeypatch):
    """Per spec section 8.8: slice is <=250 tokens."""
    examples = [
        {"proposed": {"duration_s": 2.0 + i * 0.1}, "final": {"duration_s": 1.0}, "weight": 5}
        for i in range(4)
    ]
    _write_profile(tmp_path, monkeypatch, transitions_confidence=1.0, examples=examples)
    slice_data = get_slice("AddTransition")
    text = json.dumps(slice_data)
    tokens = len(text) / 4  # rough estimate
    assert tokens <= 250


def test_tag_map_covers_all_op_types():
    """All 12 op types have a tag map entry."""
    from open_edit.style.retrieve import TAG_MAP
    expected_ops = [
        "AddTransition", "AddEffect", "SetKeyframe", "AddClip", "MoveClip",
        "TrimClip", "SetAudioGain", "NormalizeAudio", "RemoveClip", "GroupEdits",
        "RawMltXml", "FreeFormCode",
    ]
    for op in expected_ops:
        assert op in TAG_MAP, f"Missing op type: {op}"
