"""Tests for the StreamEvent contract (Wave 3.3)."""
from __future__ import annotations

from typing import get_type_hints

from open_edit.serve.llm import StreamEvent, _coerce_event


def test_stream_event_is_typed_dict():
    """StreamEvent must be importable and annotated — not just a docstring."""
    hints = get_type_hints(StreamEvent)
    # Wave 3.3 final: events are flat, discriminated by ``type``. The
    # contract is that the ``type`` discriminant and every variant payload
    # field are declared on the TypedDict.
    assert "type" in hints
    for field in ("text", "id", "name", "input", "result",
                  "tokens", "cost_usd", "usage", "source",
                  "stop_reason", "message"):
        assert field in hints, f"StreamEvent must declare {field!r} field"


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
