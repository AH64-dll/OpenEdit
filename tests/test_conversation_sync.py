"""Tests for conversation sync between JSONL and pi session."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from open_edit.serve.agent import append_to_conversation, load_conversation


def _project_with_jsonl(tmp_path: Path) -> tuple[Path, str]:
    proj = tmp_path / "testproj"
    proj.mkdir()
    (proj / ".open_edit").mkdir()
    (proj / ".open_edit" / "conversations").mkdir()
    conv_id = "test-conv-001"
    return proj, conv_id


def test_append_and_load_roundtrip(tmp_path):
    proj, conv_id = _project_with_jsonl(tmp_path)
    def fake_resolve(pid):
        return proj if pid == conv_id else None
    with mock.patch("open_edit.serve.agent._resolve_project_path", fake_resolve):
        msg = {"role": "user", "content": "hello"}
        append_to_conversation(conv_id, conv_id, msg)
        loaded = load_conversation(conv_id, conv_id)
    assert len(loaded) == 1
    assert loaded[0]["content"] == "hello"


def test_load_missing_returns_empty(tmp_path):
    proj, conv_id = _project_with_jsonl(tmp_path)
    def fake_resolve(pid):
        return proj if pid == conv_id else None
    with mock.patch("open_edit.serve.agent._resolve_project_path", fake_resolve):
        loaded = load_conversation("missing", "missing")
    assert loaded == []


def test_append_multiple_messages(tmp_path):
    proj, conv_id = _project_with_jsonl(tmp_path)
    def fake_resolve(pid):
        return proj if pid == conv_id else None
    with mock.patch("open_edit.serve.agent._resolve_project_path", fake_resolve):
        for i in range(3):
            append_to_conversation(conv_id, conv_id, {"role": "user", "content": f"msg_{i}"})
        loaded = load_conversation(conv_id, conv_id)
    assert len(loaded) == 3
    assert [m["content"] for m in loaded] == ["msg_0", "msg_1", "msg_2"]


def test_append_mid_turn_survives(tmp_path):
    """Simulate mid-turn crash: save after each tool_result, crash, restart."""
    proj, conv_id = _project_with_jsonl(tmp_path)
    def fake_resolve(pid):
        return proj if pid == conv_id else None
    with mock.patch("open_edit.serve.agent._resolve_project_path", fake_resolve):
        append_to_conversation(conv_id, conv_id, {"role": "user", "content": "tool_result_1"})
        append_to_conversation(conv_id, conv_id, {"role": "user", "content": "tool_result_2"})
        loaded = load_conversation(conv_id, conv_id)
    assert len(loaded) == 2
    assert loaded[1]["content"] == "tool_result_2"


def test_jsonl_is_valid_jsonl(tmp_path):
    """Each line must be valid JSON."""
    proj, conv_id = _project_with_jsonl(tmp_path)
    def fake_resolve(pid):
        return proj if pid == conv_id else None
    with mock.patch("open_edit.serve.agent._resolve_project_path", fake_resolve):
        append_to_conversation(conv_id, conv_id, {"role": "user", "content": "line1"})
        append_to_conversation(conv_id, conv_id, {"role": "assistant", "content": "line2"})
    f = proj / ".open_edit" / "conversations" / f"{conv_id}.jsonl"
    lines = f.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        obj = json.loads(line)
        assert "role" in obj
