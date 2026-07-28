"""Phase 4 Task 3: prior_state block builder."""
import pytest
from pathlib import Path

from open_edit.style.taste_events import TasteEvent, TasteEventStore
from open_edit.style.aggregate import rollup
from open_edit.agent.style_inject import build_prior_state


def _make_event(action: str, weight: int, proposed: dict, final: dict | None = None):
    from datetime import datetime, timezone
    return TasteEvent(
        project_id="p1",
        op_type="AddTransition",
        proposed_params=proposed,
        final_params=final or proposed,
        action=action,
        correction_note="",
        timestamp=datetime.now(timezone.utc).isoformat(),
        weight=weight,
    )


def test_build_prior_state_format(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    for _ in range(10):
        store.append(_make_event("applied_modified", 5, {"duration_s": 2.0}, {"duration_s": 1.5}))
    rollup("p1", store)
    state = build_prior_state(project_id="p1", expected_op_type="AddTransition", creativity_level="balanced")
    assert "<prior_state>" in state
    assert "</prior_state>" in state
    assert "creativity_level: balanced" in state


def test_build_prior_state_token_budget(tmp_path, monkeypatch):
    """Per audit M4: total <=600 tokens."""
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    for _ in range(10):
        store.append(_make_event("applied_modified", 5, {"duration_s": 2.0}, {"duration_s": 1.5}))
    rollup("p1", store)
    state = build_prior_state(project_id="p1", expected_op_type="AddTransition", creativity_level="balanced")
    tokens = len(state) / 4
    assert tokens <= 600, f"prior_state is {tokens} tokens, exceeds 600 budget"


def test_pin_precedence_in_prior_state(tmp_path, monkeypatch):
    """Per spec section 8.7: pinned > profile_default > LLM_default."""
    monkeypatch.setenv("HOME", str(tmp_path))
    store = TasteEventStore(tmp_path / "taste.db")
    for _ in range(10):
        store.append(_make_event("applied_modified", 5, {"duration_s": 2.0}, {"duration_s": 1.5}))
    rollup("p1", store)
    from open_edit.style.aggregate import set_pinned
    set_pinned("transitions.default_duration_s", 0.5)
    state = build_prior_state(project_id="p1", expected_op_type="AddTransition", creativity_level="balanced")
    # The pinned value should appear, with priority marker
    assert "0.5" in state
    assert "[pinned]" in state
