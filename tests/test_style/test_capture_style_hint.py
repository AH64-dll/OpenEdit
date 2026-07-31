"""Tests for capture_style_hint + aggregate.capture_hint."""
from __future__ import annotations

import json

from open_edit.agent.tools.pyagent_capture_style_hint import capture_style_hint
from open_edit.style.aggregate import capture_hint
from open_edit.style.retrieve import get_slice


def test_capture_hint_persists_and_raises_confidence(tmp_path, monkeypatch):
    cfg = tmp_path / ".open-edit"
    cfg.mkdir()
    profile = cfg / "style_profile.json"
    profile.write_text(json.dumps({
        "pacing": {"confidence": 0.0, "examples": []},
        "corrections": {},
        "pinned": {},
    }))
    monkeypatch.setattr("open_edit.style.aggregate.get_config_dir", lambda: cfg)
    monkeypatch.setattr("open_edit.style.aggregate.get_profile_path", lambda: profile)
    entry = capture_hint(category="pacing", hint="prefer punchy cuts under 3s")
    data = json.loads(profile.read_text())
    assert data["hints"][-1]["text"] == "prefer punchy cuts under 3s"
    assert data["pacing"]["confidence"] >= 0.35
    assert "punchy" in data["corrections"]["note"]
    assert entry["category"] == "pacing"


def test_capture_style_hint_tool_requires_confirmed(tmp_path, monkeypatch):
    cfg = tmp_path / ".open-edit"
    cfg.mkdir()
    profile = cfg / "style_profile.json"
    profile.write_text("{}")
    monkeypatch.setattr("open_edit.style.aggregate.get_config_dir", lambda: cfg)
    monkeypatch.setattr("open_edit.style.aggregate.get_profile_path", lambda: profile)
    monkeypatch.setattr("open_edit.style.retrieve.get_profile_path", lambda: profile)

    denied = capture_style_hint(
        {"hint": "9:16 vertical", "category": "export", "confirmed": False},
        str(tmp_path),
    )
    assert denied["status"] == "error"
    truthy_but_not_boolean = capture_style_hint(
        {"hint": "16:9 horizontal", "category": "export", "confirmed": 1},
        str(tmp_path),
    )
    assert truthy_but_not_boolean["status"] == "error"

    ok = capture_style_hint(
        {
            "hint": "9:16 vertical",
            "category": "export",
            "key": "aspect_ratio",
            "value": "9:16",
            "confirmed": True,
        },
        str(tmp_path),
    )
    assert ok["status"] == "ok"
    data = json.loads(profile.read_text())
    assert data["pinned"]["aspect_ratio"] == "9:16"
    slice_data = get_slice("AddClip")
    assert "hints" in slice_data or "pinned" in slice_data
