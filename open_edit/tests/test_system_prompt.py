from __future__ import annotations

import json
from pathlib import Path

import pytest

from open_edit.serve.agent import _build_state_summary, _build_system_prompt


class FakeProjectState:
    """Minimal stand-in for projects_mod.ProjectState."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        if not hasattr(self, "name"):
            self.name = "untitled"
        if not hasattr(self, "assets"):
            self.assets = []
        if not hasattr(self, "notes"):
            self.notes = []

    def model_dump(self):
        return {
            "name": self.name,
            "assets": self.assets,
            "notes": self.notes,
        }


def test_build_state_summary_under_1kb():
    state = FakeProjectState(
        name="test",
        assets=[{"id": i} for i in range(10)],
    )
    summary = _build_state_summary(state)
    assert len(summary) < 1024
    assert "Asset count: 10" in summary
    assert "Project: test" in summary


def test_build_state_summary_with_pending():
    state = FakeProjectState(
        notes=[{"id": "n1", "text": "fix the audio"}],
    )
    summary = _build_state_summary(state)
    assert "Pending notes: 1" in summary
    assert "fix the audio" in summary


def test_build_system_prompt_full_state():
    state = FakeProjectState(name="test")
    prompt = _build_system_prompt(state, supports_tools=False)
    assert "Project state" in prompt
    assert "Project:" not in prompt  # summary format not used


def test_build_system_prompt_summary_mode():
    state = FakeProjectState(name="test")
    prompt = _build_system_prompt(state, supports_tools=False, state_summary_only=True)
    assert "Project:" in prompt
    assert "```json" not in prompt


def test_empty_state_summary():
    state = FakeProjectState()
    summary = _build_state_summary(state)
    assert len(summary) > 0
