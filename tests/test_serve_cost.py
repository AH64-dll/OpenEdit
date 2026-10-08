"""SDK pricing and usage accounting tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from open_edit.serve import cost as cost_mod

_THIS_DIR = Path(__file__).resolve()
_REPO_ROOT = _THIS_DIR.parents[1]


# ---------------------------------------------------------------------------
# Pricing config
# ---------------------------------------------------------------------------

def test_load_pricing_returns_anthropic_and_openai_sections(tmp_path, monkeypatch):
    """The shipped pricing.json has anthropic + openai sections."""
    cfg = {
        "anthropic": {"claude-sonnet-4-5": {"input_per_1m": 3.0, "output_per_1m": 15.0}},
        "openai": {"gpt-4o": {"input_per_1m": 2.5, "output_per_1m": 10.0}},
    }
    p = tmp_path / "pricing.json"
    p.write_text(json.dumps(cfg))
    # load_pricing uses a module-level constant resolved from the
    # package dir by default; we monkeypatch it to point at our temp
    # file so the test doesn't depend on the bundled file.
    monkeypatch.setattr(cost_mod, "PRICING_PATH", p)
    out = cost_mod.load_pricing()
    assert "anthropic" in out
    assert "openai" in out
    assert out["anthropic"]["claude-sonnet-4-5"]["input_per_1m"] == 3.0


def test_load_pricing_missing_file_raises(monkeypatch, tmp_path):
    """If the file doesn't exist (operator misconfig), we raise loudly
    rather than silently returning $0 cost — that would mislead users."""
    monkeypatch.setattr(cost_mod, "PRICING_PATH", tmp_path / "nope.json")
    with pytest.raises(FileNotFoundError):
        cost_mod.load_pricing()


def test_lookup_pricing_found():
    """Looking up a known model returns its entry."""
    entry = cost_mod.lookup_pricing("anthropic", "claude-sonnet-4-5")
    assert entry is not None
    assert entry["input_per_1m"] == pytest.approx(3.0)
    assert entry["output_per_1m"] == pytest.approx(15.0)


def test_lookup_pricing_unknown_model_returns_none():
    """Unknown model returns None — caller maps to ``source: unavailable``."""
    assert cost_mod.lookup_pricing("anthropic", "no-such-model") is None
    assert cost_mod.lookup_pricing("no-such-provider", "x") is None


# ---------------------------------------------------------------------------
# Anthropic cost computation
# ---------------------------------------------------------------------------

def test_compute_anthropic_cost_basic_input_output():
    """1000 input + 500 output tokens of claude-sonnet-4-5:
    input  = 1000 * 3.00 / 1_000_000 = 0.003
    output = 500  * 15.00 / 1_000_000 = 0.0075
    total  = 0.0105
    """
    usage = {
        "input_tokens": 1000,
        "output_tokens": 500,
    }
    tokens, cost = cost_mod.compute_anthropic_cost(usage, "claude-sonnet-4-5")
    assert tokens == 1500
    assert cost == pytest.approx(0.0105, abs=1e-9)


def test_compute_anthropic_cost_with_cache():
    """Cache hits/creation get their own per-1m rates."""
    usage = {
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_creation_input_tokens": 200,
        "cache_read_input_tokens": 5000,
    }
    _, cost = cost_mod.compute_anthropic_cost(usage, "claude-sonnet-4-5")
    # 100 * 3 + 50 * 15 + 200 * 3.75 + 5000 * 0.30, all / 1_000_000
    expected = (100 * 3.0 + 50 * 15.0 + 200 * 3.75 + 5000 * 0.30) / 1_000_000
    assert cost == pytest.approx(expected, abs=1e-9)


def test_compute_anthropic_cost_unknown_model_returns_none():
    """Unknown model → None (caller maps to ``unavailable`` source)."""
    out = cost_mod.compute_anthropic_cost(
        {"input_tokens": 100, "output_tokens": 50}, "no-such-model"
    )
    assert out is None


# ---------------------------------------------------------------------------
# OpenAI cost computation
# ---------------------------------------------------------------------------

def test_compute_openai_cost_basic():
    """OpenAI's usage is ``prompt_tokens`` / ``completion_tokens``."""
    usage = {"prompt_tokens": 1000, "completion_tokens": 500}
    tokens, cost = cost_mod.compute_openai_cost(usage, "gpt-4o")
    assert tokens == 1500
    assert cost == pytest.approx(0.0025 + 0.005, abs=1e-9)


def test_compute_openai_cost_with_cached_tokens():
    """OpenAI exposes cached prompt tokens under
    ``prompt_tokens_details.cached_tokens``. We still pay the full
    input rate (cached is a separate, lower rate on some models), but
    the simple shape: just sum all into tokens and apply input rate.
    For OpenAI models we only have input/output rates here; cached
    tokens are counted as input."""
    usage = {
        "prompt_tokens": 1000,
        "completion_tokens": 500,
        "prompt_tokens_details": {"cached_tokens": 400},
    }
    tokens, cost = cost_mod.compute_openai_cost(usage, "gpt-4o")
    assert tokens == 1500
    # We do NOT subtract cached tokens from the input bill — the
    # shipped pricing for gpt-4o doesn't expose a cache rate. The
    # cached_tokens field is informational; the operator can extend
    # pricing.json with cache fields if they want to discount.
    expected = (1000 * 2.5 + 500 * 10.0) / 1_000_000
    assert cost == pytest.approx(expected, abs=1e-9)


def test_compute_openai_cost_unknown_model_returns_none():
    """Unknown model → None."""
    out = cost_mod.compute_openai_cost(
        {"prompt_tokens": 100, "completion_tokens": 50}, "no-such-model"
    )
    assert out is None


# ---------------------------------------------------------------------------
