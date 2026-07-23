"""Tests for the ContextBudget module."""
from __future__ import annotations

import json
import os

import pytest

from open_edit.serve.context_budget import (
    ContextBudget,
    count_tokens,
    count_tokens_history,
    count_tokens_message,
)


def test_count_tokens_basic():
    assert count_tokens("hello world") == 2
    assert count_tokens("") == 1
    assert count_tokens("a" * 100) == 25


def test_count_tokens_message():
    msg = {"role": "user", "content": "hello world"}
    assert count_tokens_message(msg) > 0


def test_count_tokens_history():
    hist = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
    ]
    assert count_tokens_history(hist) > 0


def test_truncate_keeps_first_and_last():
    budget = ContextBudget(max_tokens=50, reserve_tokens=10)
    hist = [
        {"role": "user", "content": "first message"},
        {"role": "assistant", "content": "middle 1"},
        {"role": "user", "content": "middle 2"},
        {"role": "assistant", "content": "last message"},
    ]
    result = budget.truncate(hist)
    assert result[0] == hist[0]
    total_tokens = count_tokens_history(result)
    assert total_tokens <= budget.max_tokens - budget.reserve_tokens


def test_truncate_inserts_placeholder():
    budget = ContextBudget(max_tokens=30, reserve_tokens=5)
    hist = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "X" * 200},
        {"role": "user", "content": "last"},
    ]
    result = budget.truncate(hist)
    placeholders = [m for m in result if "truncated" in str(m.get("content", ""))]
    assert len(placeholders) >= 1


def test_truncate_within_budget_unchanged():
    budget = ContextBudget(max_tokens=100000, reserve_tokens=1000)
    hist = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    result = budget.truncate(hist)
    assert result == hist


def test_summarize_tool_result_truncates_long_fields():
    budget = ContextBudget()
    result = {"stdout": "x" * 5000, "stderr": "", "status": "ok"}
    capped = budget.summarize_tool_result(result, max_chars=100)
    assert len(capped["stdout"]) < 200
    assert capped.get("_truncated") is True


def test_summarize_tool_result_caps_lists():
    budget = ContextBudget()
    result = {"items": [{"i": n} for n in range(50)]}
    capped = budget.summarize_tool_result(result)
    assert len(capped["items"]) <= 21
    assert capped.get("_truncated") is True


def test_summarize_tool_result_small_unchanged():
    budget = ContextBudget()
    result = {"status": "ok", "value": 42}
    capped = budget.summarize_tool_result(result)
    assert capped == result


def test_summarize_tool_result_render_strips_stdout():
    budget = ContextBudget()
    result = {"status": "ok", "stdout": "lots of debug output", "stderr": "", "output_path": "/tmp/x.mp4"}
    capped = budget.summarize_tool_result(result, max_chars=10)
    assert len(capped["stdout"]) < 100
