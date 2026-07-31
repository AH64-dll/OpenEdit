"""Phase 4 Task 3: prior_state block builder."""

from open_edit.agent.style_inject import build_prior_state
from open_edit.style.aggregate import set_pinned


def test_build_prior_state_format(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    state = build_prior_state(project_id="p1", expected_op_type="AddTransition", creativity_level="balanced")
    assert "<prior_state>" in state
    assert "</prior_state>" in state
    assert "creativity_level: balanced" in state


def test_build_prior_state_token_budget(tmp_path, monkeypatch):
    """Per audit M4: total <=600 tokens."""
    monkeypatch.setenv("HOME", str(tmp_path))
    state = build_prior_state(project_id="p1", expected_op_type="AddTransition", creativity_level="balanced")
    tokens = len(state) / 4
    assert tokens <= 600, f"prior_state is {tokens} tokens, exceeds 600 budget"


def test_pin_precedence_in_prior_state(tmp_path, monkeypatch):
    """Per spec section 8.7: pinned > profile_default > LLM_default."""
    monkeypatch.setenv("HOME", str(tmp_path))
    set_pinned("transitions.default_duration_s", 0.5)
    state = build_prior_state(project_id="p1", expected_op_type="AddTransition", creativity_level="balanced")
    # The pinned value should appear, with priority marker
    assert "0.5" in state
    assert "[pinned]" in state
