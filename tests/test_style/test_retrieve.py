"""Phase 4 Task 3: tag-gated style profile retrieval."""
import json
import pytest
from pathlib import Path

from open_edit.style.taste_events import TasteEvent, TasteEventStore
from open_edit.style.aggregate import rollup
from open_edit.style.retrieve import get_slice


def _make_event(action: str, weight: int, proposed: dict, final: dict | None = None):
    from datetime import datetime, timezone
    return TasteEvent(
        project_id="p1",
        op_type="AddTransition",
        proposed_params=proposed,
        final_params=final or proposed,
        action=action,
        correction_note="",
        timestamp=datetime.now(timezone.utc).isoformat(),
        weight=weight,
    )


def test_get_slice_add_transition(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    for _ in range(10):
        store.append(_make_event("applied_modified", 5, {"duration_s": 2.0}, {"duration_s": 1.5}))
    rollup("p1", store)
    slice_data = get_slice("AddTransition")
    assert "transitions" in slice_data
    assert "corrections" in slice_data  # Always included


def test_get_slice_omits_low_confidence(tmp_path, monkeypatch):
    """Per spec section 8.8: below confidence 0.2, category is omitted."""
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    # 1 weak signal = confidence = 5/50 = 0.1
    store.append(_make_event("applied_modified", 5, {"duration_s": 2.0}, {"duration_s": 1.5}))
    rollup("p1", store)
    slice_data = get_slice("AddTransition")
    # transitions confidence is 0.1, should be omitted
    assert "transitions" not in slice_data
    # corrections is always included
    assert "corrections" in slice_data


def test_get_slice_token_cap(tmp_path, monkeypatch):
    """Per spec section 8.8: slice is <=250 tokens."""
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    for _ in range(10):
        store.append(_make_event("applied_modified", 5, {"duration_s": 2.0}, {"duration_s": 1.5}))
    rollup("p1", store)
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
