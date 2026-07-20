"""Phase 4 Task 3: style memory aggregation."""
import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from open_edit.style.taste_events import TasteEvent, TasteEventStore
from open_edit.style.aggregate import rollup, reset, set_pinned


def _make_event(action: str, weight: int, proposed: dict, final: dict | None = None, ts_offset_days: int = 0) -> TasteEvent:
    ts = (datetime.now(timezone.utc) - timedelta(days=ts_offset_days)).isoformat()
    return TasteEvent(
        project_id="p1",
        op_type="AddTransition",
        proposed_params=proposed,
        final_params=final or proposed,
        action=action,
        correction_note="",
        timestamp=ts,
        weight=weight,
    )


def test_rollup_creates_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    store.append(_make_event("applied_modified", 5, {"duration_s": 2.0}, {"duration_s": 1.5}))
    profile = rollup("p1", store)
    assert "transitions" in profile.model_dump()
    assert profile.meta["sample_size"] == 1


def test_rollup_weights_applied(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    for _ in range(10):
        store.append(_make_event("applied_modified", 5, {"duration_s": 2.0}, {"duration_s": 1.5}))
    profile = rollup("p1", store)
    assert profile.transitions["confidence"] >= 0.9


def test_rollup_applied_unmodified_weight_zero(tmp_path, monkeypatch):
    """Per spec section 8.4: indifference is not signal."""
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    for _ in range(20):
        store.append(_make_event("applied_unmodified", 1, {"duration_s": 1.0}))
    profile = rollup("p1", store)
    # 20 weak signals (weight=1) should not reach confidence 1.0
    assert profile.transitions["confidence"] < 0.5


def test_rollup_eviction_by_weight(tmp_path, monkeypatch):
    """Per spec section 8.6.3: cap at 4 examples per category, evict lowest weight."""
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    for i in range(6):
        store.append(_make_event("applied_modified", 5, {"duration_s": 2.0 + i * 0.1}, {"duration_s": 1.0}))
    profile = rollup("p1", store)
    assert len(profile.transitions["examples"]) <= 4


def test_rollup_keeps_last_3_versions(tmp_path, monkeypatch):
    """Per spec section 8.6.7: keep last 3 versions as .bak."""
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    for v in range(5):
        store.append(_make_event("applied_modified", 5, {"duration_s": float(v)}, {"duration_s": float(v) * 0.5}))
        rollup("p1", store)
    profile_dir = Path.home() / ".open-edit"
    baks = sorted(profile_dir.glob("style_profile_v*.json.bak"))
    assert len(baks) == 3


def test_chmod_600(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    store.append(_make_event("applied_modified", 5, {"duration_s": 2.0}, {"duration_s": 1.5}))
    rollup("p1", store)
    profile_path = Path.home() / ".open-edit" / "style_profile.json"
    assert oct(profile_path.stat().st_mode)[-3:] == "600"


def test_set_pinned(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    store.append(_make_event("applied_modified", 5, {"duration_s": 2.0}, {"duration_s": 1.5}))
    rollup("p1", store)
    set_pinned("fades.default_out_s", 1.8)
    profile = rollup("p1", store)  # Re-read
    assert profile.pinned["fades.default_out_s"] == 1.8
