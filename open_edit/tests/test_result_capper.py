"""Tests for the result_capper module."""
from __future__ import annotations

import pytest

from open_edit.serve.result_capper import cap_tool_result


def test_oversized_stdout_truncated():
    result = {"status": "ok", "stdout": "x" * 20000}
    capped = cap_tool_result(result)
    assert len(capped["stdout"]) < 11000
    assert capped.get("_truncated") is True


def test_long_list_capped():
    result = {"items": [{"i": n} for n in range(100)]}
    capped = cap_tool_result(result)
    assert len(capped["items"]) <= 21
    assert capped.get("_truncated") is True


def test_render_result_strips_stdout_stderr():
    result = {"status": "ok", "output_path": "/tmp/x.mp4", "stdout": "debug", "stderr": "warnings"}
    capped = cap_tool_result(result)
    assert "stdout" not in capped
    assert "stderr" not in capped


def test_small_result_unchanged():
    result = {"status": "ok", "value": 42}
    capped = cap_tool_result(result)
    assert capped == result


def test_truncated_field_set():
    result = {"status": "ok", "stdout": "x" * 20000}
    capped = cap_tool_result(result)
    assert capped["_truncated"] is True


def test_error_field_truncated():
    result = {"status": "error", "error": "x" * 20000}
    capped = cap_tool_result(result)
    assert len(capped["error"]) < 11000
