"""Tests for conversation history compaction."""
from __future__ import annotations

from open_edit.serve.context_budget import compact_history


def test_merge_consecutive_user_messages():
    hist = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "response"},
        {"role": "user", "content": "second"},
        {"role": "user", "content": "third"},
    ]
    compacted = compact_history(hist)
    assert len(compacted) == 3
    assert compacted[0]["content"] == "first"
    assert compacted[1]["content"] == "response"
    assert "second" in compacted[2]["content"]
    assert "third" in compacted[2]["content"]


def test_remove_tool_only_assistant():
    hist = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": [{"type": "tool_use", "name": "bash"}]},
        {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]},
    ]
    compacted = compact_history(hist)
    assert len(compacted) == 1
    assert compacted[0]["role"] == "user"


def test_preserve_assistant_with_text():
    hist = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": [{"type": "text", "text": "hi!"}, {"type": "tool_use", "name": "bash"}]},
    ]
    compacted = compact_history(hist)
    assert len(compacted) == 2


def test_empty_history():
    assert compact_history([]) == []


def test_single_message():
    hist = [{"role": "user", "content": "hello"}]
    assert compact_history(hist) == hist


def test_no_consecutive_users():
    hist = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": "c"},
    ]
    compacted = compact_history(hist)
    assert len(compacted) == 3
