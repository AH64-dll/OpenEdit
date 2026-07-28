"""Tests for ``open_edit.serve.cost``.

Pure-function tests for the cost-computation module: pricing config
loading, anthropic/openai cost multiplication, and pi session JSONL
parsing. These are the building blocks that the LLM/agent layers will
combine to emit a ``cost_update`` event.

The pi path is the most important one (the default provider for this
project), so we cover the JSONL parser thoroughly — including the
position-tracking variant that the agent loop uses to compute turn
deltas.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_THIS_DIR = Path(__file__).resolve()
_REPO_ROOT = _THIS_DIR.parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from open_edit.serve import cost as cost_mod  # noqa: E402


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
# Pi session JSONL parsing
# ---------------------------------------------------------------------------

def _write_session_jsonl(path: Path, lines: list[dict]) -> None:
    """Write one JSON object per line to ``path`` (UTF-8, trailing newline)."""
    with path.open("w", encoding="utf-8") as fh:
        for obj in lines:
            fh.write(json.dumps(obj) + "\n")


def test_parse_pi_session_usage_sums_assistant_messages(tmp_path):
    """A session with 2 assistant messages: the parser sums their
    usage.cost.total into the session total."""
    session_file = tmp_path / "session.jsonl"
    _write_session_jsonl(session_file, [
        {"type": "session", "id": "abc"},
        {
            "type": "message", "id": "m1",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "hi"}],
            },
        },
        {
            "type": "message", "id": "m2",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "hello"}],
                "model": "minimax-m3",
                "usage": {
                    "input": 100, "output": 50,
                    "cacheRead": 0, "cacheWrite": 0,
                    "totalTokens": 150,
                    "cost": {
                        "input": 0.0001, "output": 0.0002,
                        "cacheRead": 0, "cacheWrite": 0,
                        "total": 0.0003,
                    },
                },
            },
        },
        {
            "type": "message", "id": "m3",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "more"}],
                "model": "minimax-m3",
                "usage": {
                    "input": 200, "output": 80,
                    "cacheRead": 0, "cacheWrite": 0,
                    "totalTokens": 280,
                    "cost": {
                        "input": 0.0002, "output": 0.0003,
                        "cacheRead": 0, "cacheWrite": 0,
                        "total": 0.0005,
                    },
                },
            },
        },
    ])
    result = cost_mod.parse_pi_session_usage(session_file)
    # tokens = sum of totalTokens across assistant messages
    assert result["tokens"] == 150 + 280
    # cost = sum of usage.cost.total
    assert result["cost_usd"] == pytest.approx(0.0008, abs=1e-9)
    # file_size is the on-disk size
    assert result["file_size"] == session_file.stat().st_size


def test_parse_pi_session_usage_ignores_user_and_tool_messages(tmp_path):
    """Only assistant messages have usage data; user/tool messages
    must be skipped (they have no ``usage`` field)."""
    session_file = tmp_path / "session.jsonl"
    _write_session_jsonl(session_file, [
        {"type": "session", "id": "abc"},
        {"type": "message", "id": "u1", "message": {"role": "user",
            "content": [{"type": "text", "text": "hi"}]}},
        {"type": "message", "id": "m1", "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "ok"}],
            "usage": {
                "input": 1, "output": 1, "cacheRead": 0, "cacheWrite": 0,
                "totalTokens": 2,
                "cost": {"input": 0, "output": 0, "cacheRead": 0,
                         "cacheWrite": 0, "total": 0.001},
            },
        }},
    ])
    result = cost_mod.parse_pi_session_usage(session_file)
    assert result["cost_usd"] == pytest.approx(0.001, abs=1e-9)


def test_parse_pi_session_usage_handles_missing_file(tmp_path):
    """Missing session file: the parser returns zeros (caller decides
    whether to surface as ``unavailable``)."""
    out = cost_mod.parse_pi_session_usage(tmp_path / "nope.jsonl")
    assert out["tokens"] == 0
    assert out["cost_usd"] == 0.0
    assert out["file_size"] == 0


def test_parse_pi_session_usage_delta_returns_only_new_content(tmp_path):
    """The delta variant only reads content appended after the last
    position. Useful for the agent loop: we read once at turn start,
    spawn pi, then read the delta."""
    session_file = tmp_path / "session.jsonl"
    _write_session_jsonl(session_file, [
        {"type": "session", "id": "abc"},
        {"type": "message", "id": "m1", "message": {
            "role": "assistant", "content": [],
            "usage": {"input": 1, "output": 1, "cacheRead": 0, "cacheWrite": 0,
                      "totalTokens": 2,
                      "cost": {"input": 0, "output": 0, "cacheRead": 0,
                               "cacheWrite": 0, "total": 0.005}},
        }},
    ])
    size_after_first = session_file.stat().st_size

    # Append a second assistant message (one more turn).
    with session_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "type": "message", "id": "m2",
            "message": {
                "role": "assistant", "content": [],
                "usage": {"input": 2, "output": 3, "cacheRead": 0,
                          "cacheWrite": 0, "totalTokens": 5,
                          "cost": {"input": 0, "output": 0, "cacheRead": 0,
                                   "cacheWrite": 0, "total": 0.007}},
            },
        }) + "\n")

    delta = cost_mod.parse_pi_session_usage_delta(
        session_file, last_size=size_after_first,
    )
    # The delta only contains the new message: tokens 5, cost 0.007.
    assert delta["tokens"] == 5
    assert delta["cost_usd"] == pytest.approx(0.007, abs=1e-9)
    assert delta["new_file_size"] == session_file.stat().st_size


def test_parse_pi_session_usage_delta_resets_when_file_truncated(tmp_path):
    """If the file shrank (e.g. pi's session was wiped), the delta
    parser must NOT report a negative cost. It should reset its
    baseline to 0 and report the full file as the delta."""
    session_file = tmp_path / "session.jsonl"
    _write_session_jsonl(session_file, [
        {"type": "message", "id": "m1", "message": {
            "role": "assistant", "content": [],
            "usage": {"input": 1, "output": 1, "cacheRead": 0, "cacheWrite": 0,
                      "totalTokens": 2,
                      "cost": {"input": 0, "output": 0, "cacheRead": 0,
                               "cacheWrite": 0, "total": 0.005}},
        }},
    ])
    # Pretend the caller last saw a 1MB file (a value larger than the
    # current real file), simulating "file got truncated by pi".
    fake_baseline = 1_000_000
    delta = cost_mod.parse_pi_session_usage_delta(
        session_file, last_size=fake_baseline,
    )
    # Truncation → reset baseline, report the whole file.
    assert delta["tokens"] == 2
    assert delta["cost_usd"] == pytest.approx(0.005, abs=1e-9)
    assert delta["new_file_size"] == session_file.stat().st_size
    # Crucially, the agent loop treats this as a fresh start (no
    # double-counted cost). The caller checks ``reset=True`` or
    # updates its baseline to ``new_file_size``.


def test_parse_pi_session_usage_handles_malformed_lines(tmp_path):
    """One corrupt line in the middle should not blow up the parser;
    we skip it and continue."""
    session_file = tmp_path / "session.jsonl"
    _write_session_jsonl(session_file, [
        {"type": "message", "id": "m1", "message": {
            "role": "assistant", "content": [],
            "usage": {"input": 1, "output": 1, "cacheRead": 0, "cacheWrite": 0,
                      "totalTokens": 2,
                      "cost": {"input": 0, "output": 0, "cacheRead": 0,
                               "cacheWrite": 0, "total": 0.001}},
        }},
    ])
    # Append a garbage line, then a valid one.
    with session_file.open("a", encoding="utf-8") as fh:
        fh.write("this is not json\n")
        fh.write(json.dumps({
            "type": "message", "id": "m2", "message": {
                "role": "assistant", "content": [],
                "usage": {"input": 2, "output": 2, "cacheRead": 0,
                          "cacheWrite": 0, "totalTokens": 4,
                          "cost": {"input": 0, "output": 0, "cacheRead": 0,
                                   "cacheWrite": 0, "total": 0.002}},
            },
        }) + "\n")
    out = cost_mod.parse_pi_session_usage(session_file)
    assert out["cost_usd"] == pytest.approx(0.003, abs=1e-9)
    assert out["tokens"] == 6


# ---------------------------------------------------------------------------
# find_pi_session_file
# ---------------------------------------------------------------------------

def test_find_pi_session_file_returns_matching_file(tmp_path):
    """Find the file that ends with the session id, even when there's
    a timestamp prefix."""
    target = tmp_path / "2026-07-20T11-30-44-319Z_abc-123.jsonl"
    target.write_text("{}")
    (tmp_path / "other.jsonl").write_text("{}")
    found = cost_mod.find_pi_session_file("abc-123", tmp_path)
    assert found == target


def test_find_pi_session_file_searches_recursively(tmp_path):
    """The session file is one level deep under sessions_dir (inside
    the encoded-CWD subdirectory pi creates). We recurse so the
    caller doesn't have to know the encoded name."""
    sub = tmp_path / "--home-foo--"
    sub.mkdir()
    target = sub / "2026-07-20T11-30-44-319Z_abc-456.jsonl"
    target.write_text("{}")
    found = cost_mod.find_pi_session_file("abc-456", tmp_path)
    assert found == target


def test_find_pi_session_file_missing_returns_none(tmp_path):
    """No matching file → None (caller maps to ``unavailable``)."""
    assert cost_mod.find_pi_session_file("nope", tmp_path) is None


def test_find_pi_session_file_no_directory_returns_none(tmp_path):
    """Missing sessions directory → None."""
    assert cost_mod.find_pi_session_file("abc", tmp_path / "no-such-dir") is None
