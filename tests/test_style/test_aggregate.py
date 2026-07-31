"""Phase 4 Task 3: style memory aggregation (pinned overrides)."""
import json
import pytest
from pathlib import Path

from open_edit.style.aggregate import set_pinned
from open_edit.storage.config import get_profile_path


def _load_profile() -> dict:
    return json.loads(get_profile_path().read_text())


def test_set_pinned(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    set_pinned("fades.default_out_s", 1.8)
    assert _load_profile()["pinned"]["fades.default_out_s"] == 1.8


def test_set_pinned_accumulates(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    set_pinned("fades.default_out_s", 1.8)
    set_pinned("transitions.default_duration_s", 0.5)
    profile = _load_profile()
    assert profile["pinned"] == {
        "fades.default_out_s": 1.8,
        "transitions.default_duration_s": 0.5,
    }


def test_keeps_last_3_backup_versions(tmp_path, monkeypatch):
    """Per spec section 8.6.7: keep last 3 versions as .bak."""
    monkeypatch.setenv("HOME", str(tmp_path))
    for v in range(5):
        set_pinned("v", v)
    profile_dir = Path.home() / ".open-edit"
    baks = sorted(profile_dir.glob("style_profile_v*.json.bak"))
    assert len(baks) == 3


def test_chmod_600(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    set_pinned("k", 1)
    profile_path = Path.home() / ".open-edit" / "style_profile.json"
    assert oct(profile_path.stat().st_mode)[-3:] == "600"
