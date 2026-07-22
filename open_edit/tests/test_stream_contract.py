"""Tests for the StreamEvent contract (Wave 3.3)."""
from __future__ import annotations

from typing import get_type_hints

from open_edit.serve.llm import StreamEvent, _coerce_event


def test_stream_event_is_typed_dict():
    """StreamEvent must be importable and annotated — not just a docstring."""
    hints = get_type_hints(StreamEvent)
    # The exact field set is what _stream_anthropic / _stream_cli / etc.
    # actually emit; this is a contract, so guard it with a test.
    assert "type" in hints
    for field in ("text_delta", "tool_use", "tool_result", "usage", "done", "error"):
        assert field in hints, f"StreamEvent must declare {field!r} variant"


def test_coerce_event_passes_through_valid_text_delta():
    raw = {"type": "text_delta", "text": "hello"}
    out = _coerce_event(raw)
    assert out["type"] == "text_delta"
    assert out["text"] == "hello"


def test_coerce_event_fills_missing_text_with_empty_string():
    raw = {"type": "text_delta"}  # text missing
    out = _coerce_event(raw)
    assert out["text"] == ""


def test_coerce_event_handles_unknown_type_gracefully():
    """A provider emitting a new event type should not crash the agent loop."""
    raw = {"type": "future_event_type", "anything": 1}
    out = _coerce_event(raw)
    assert out["type"] == "future_event_type"
    # The contract is "be tolerant": forward unknown events as-is.


def test_coerce_event_requires_type_field():
    import pytest
    with pytest.raises(ValueError):
        _coerce_event({})
