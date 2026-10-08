"""SDK streaming usage and verification event tests."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from open_edit.serve.llm import (
    StreamEvent,
    stream_chat,
)

_THIS_DIR = Path(__file__).resolve()
_REPO_ROOT = _THIS_DIR.parents[1]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _collect(stream: AsyncIterator[StreamEvent]) -> list[StreamEvent]:
    out = []
    async for ev in stream:
        out.append(ev)
    return out


# ---------------------------------------------------------------------------
# SDK and CLI usage accounting
# ---------------------------------------------------------------------------

class _FakeAnthropicUsage:
    def __init__(self, **kwargs):
        self.input_tokens = kwargs.get("input_tokens", 0)
        self.output_tokens = kwargs.get("output_tokens", 0)
        self.cache_creation_input_tokens = kwargs.get("cache_creation_input_tokens", 0)
        self.cache_read_input_tokens = kwargs.get("cache_read_input_tokens", 0)


class _FakeAnthropicFinalMessage:
    def __init__(self, usage):
        self.usage = usage
        self.stop_reason = "end_turn"
        self.content = []


class _FakeAnthropicStream:
    """Async context manager that yields canned content_block / message_stop events.

    Mocks the SDK's `client.messages.stream(...)` async context
    manager. The real SDK yields an event whose ``.type`` is
    ``"message_stop"`` as the terminal event; we yield exactly one
    such event so the LLM layer can read ``get_final_message()``.
    """

    def __init__(self, usage: _FakeAnthropicUsage):
        self._usage = usage
        self._final = _FakeAnthropicFinalMessage(usage)
        self._emitted_stop = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._emitted_stop:
            raise StopAsyncIteration
        self._emitted_stop = True
        # The real SDK uses pydantic models; the LLM layer only
        # needs `.type` to be the string "message_stop".
        return _FakeAnthropicMessageStopEvent()

    async def get_final_message(self):
        return self._final

    async def text(self):
        return ""


class _FakeAnthropicMessageStopEvent:
    type = "message_stop"


class _FakeAnthropicStreamFactory:
    def __init__(self, usage):
        self.usage = usage
        self.last_call = None

    def __call__(self, **kwargs):
        self.last_call = kwargs
        return _FakeAnthropicStream(self.usage)


class _FakeAnthropicMessages:
    def __init__(self, usage):
        self.stream = _FakeAnthropicStreamFactory(usage)


class _FakeAnthropicClient:
    def __init__(self, usage, api_key):
        self.api_key = api_key
        self.usage = usage
        self.messages = _FakeAnthropicMessages(usage)


class _FakeAnthropicModule:
    def __init__(self, usage):
        self.usage = usage
        self.AsyncAnthropic = lambda api_key: _FakeAnthropicClient(usage, api_key)
        self.NOT_GIVEN = object()


def test_anthropic_path_yields_usage_event(monkeypatch, fake_anthropic_sdk):
    """The Anthropic provider must emit a ``usage`` event with the
    shape the agent loop expects. We pass the SDK usage through
    unchanged; the cost math happens in cost.py against pricing.json."""
    sdk, _fake_usage = fake_anthropic_sdk
    monkeypatch.setitem(sys.modules, "anthropic", sdk)
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("OPEN_EDIT_LLM_API_KEY", "test-key")
    monkeypatch.setenv("OPEN_EDIT_LLM_MODEL", "claude-sonnet-4-5")

    events = asyncio.run(_collect(stream_chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system="",
    )))
    usage = next((e for e in events if e["type"] == "usage"), None)
    assert usage is not None, f"no usage event in {[e['type'] for e in events]}"
    # Brief: source is "computed" for SDK-based providers.
    assert usage["source"] == "computed"
    # The raw SDK usage dict is passed through so the frontend can
    # see the breakdown if it wants; cost/tokens are derived in cost.py.
    assert usage["usage"]["input_tokens"] == 100
    assert usage["usage"]["output_tokens"] == 50
    assert usage["tokens"] == 150
    # Cost: 100 * 3 + 50 * 15 / 1_000_000 = 0.00105
    assert usage["cost_usd"] == pytest.approx(0.00105, abs=1e-9)


def test_anthropic_path_unknown_model_yields_unavailable(monkeypatch, fake_anthropic_sdk):
    """If the model isn't in pricing.json, the usage event reports
    source=unavailable (cost math is impossible without rates)."""
    sdk, _ = fake_anthropic_sdk
    monkeypatch.setitem(sys.modules, "anthropic", sdk)
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("OPEN_EDIT_LLM_API_KEY", "test-key")
    monkeypatch.setenv("OPEN_EDIT_LLM_MODEL", "no-such-model-xyz")

    events = asyncio.run(_collect(stream_chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system="",
    )))
    usage = next((e for e in events if e["type"] == "usage"), None)
    assert usage is not None
    assert usage["source"] == "unavailable"
    assert usage["cost_usd"] == 0.0


@pytest.fixture
def fake_anthropic_sdk():
    usage = _FakeAnthropicUsage(
        input_tokens=100, output_tokens=50,
    )
    return _FakeAnthropicModule(usage), usage


# ---------------------------------------------------------------------------
# OpenAI path
# ---------------------------------------------------------------------------

class _FakeOpenAIUsage:
    def __init__(self, **kwargs):
        self.prompt_tokens = kwargs.get("prompt_tokens", 0)
        self.completion_tokens = kwargs.get("completion_tokens", 0)
        self.prompt_tokens_details = kwargs.get("prompt_tokens_details")


class _FakeOpenAIStream:
    def __init__(self, usage: _FakeOpenAIUsage):
        self._usage = usage

    async def __aiter__(self):
        # A single terminal chunk with finish_reason=stop and the
        # usage object on it. The real SDK puts usage on the LAST
        # chunk only — we mimic that.
        chunk = _FakeOpenAIChunk(usage=self._usage, finish_reason="stop")
        yield chunk


class _FakeOpenAIChunk:
    def __init__(self, usage=None, finish_reason=None):
        self.choices = [
            _FakeOpenAIChoice(usage=usage, finish_reason=finish_reason),
        ]
        # Real OpenAI SDK exposes usage on the chunk, not the choice.
        self.usage = usage


class _FakeOpenAIChoice:
    def __init__(self, usage=None, finish_reason=None):
        self.delta = _FakeOpenAIDelta()
        self.finish_reason = finish_reason


class _FakeOpenAIDelta:
    def __init__(self):
        self.content = ""
        self.tool_calls = None


class _FakeOpenAICompletions:
    def __init__(self, usage):
        self.usage = usage

    async def create(self, **kwargs):
        return _FakeOpenAIStream(self.usage)


class _FakeOpenAIClient:
    def __init__(self, usage, api_key):
        self.usage = usage
        self.chat = type("Chat", (), {"completions": _FakeOpenAICompletions(usage)})()


class _FakeOpenAIModule:
    def __init__(self, usage):
        self.usage = usage
        self.AsyncOpenAI = lambda api_key: _FakeOpenAIClient(usage, api_key)


def test_openai_path_yields_usage_event(monkeypatch):
    usage = _FakeOpenAIUsage(prompt_tokens=200, completion_tokens=80)
    sdk = _FakeOpenAIModule(usage)
    monkeypatch.setitem(sys.modules, "openai", sdk)
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPEN_EDIT_LLM_API_KEY", "test-key")
    monkeypatch.setenv("OPEN_EDIT_LLM_MODEL", "gpt-4o")

    events = asyncio.run(_collect(stream_chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system="",
    )))
    usage_evt = next((e for e in events if e["type"] == "usage"), None)
    assert usage_evt is not None, f"no usage event in {[e['type'] for e in events]}"
    assert usage_evt["source"] == "computed"
    assert usage_evt["usage"]["prompt_tokens"] == 200
    assert usage_evt["usage"]["completion_tokens"] == 80
    assert usage_evt["tokens"] == 280
    # Cost: 200 * 2.5 + 80 * 10 / 1_000_000 = 0.0013
    assert usage_evt["cost_usd"] == pytest.approx(0.0013, abs=1e-9)


def test_openai_path_unknown_model_yields_unavailable(monkeypatch):
    usage = _FakeOpenAIUsage(prompt_tokens=100, completion_tokens=50)
    sdk = _FakeOpenAIModule(usage)
    monkeypatch.setitem(sys.modules, "openai", sdk)
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPEN_EDIT_LLM_API_KEY", "test-key")
    monkeypatch.setenv("OPEN_EDIT_LLM_MODEL", "no-such-model-xyz")

    events = asyncio.run(_collect(stream_chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system="",
    )))
    usage_evt = next((e for e in events if e["type"] == "usage"), None)
    assert usage_evt is not None
    assert usage_evt["source"] == "unavailable"


# ---------------------------------------------------------------------------
# done event always emitted last
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# v1.5: parse_verdict in the LLM response path
# ---------------------------------------------------------------------------

def test_parse_verdict_in_message():
    """A real LLM response containing ``VERIFICATION: PASS`` extracts as pass."""
    from open_edit.serve.visual_verify import parse_verdict
    r = parse_verdict("Looks good. The overlay is gone.\nVERIFICATION: PASS\n")
    assert r["verdict"] == "pass"
    assert r["source"] == "model_explicit_pass"


def test_no_verdict_line_returns_unknown():
    """No verdict line → unknown (caller decides what to do; the spec
    requires a non-false ``verification_result`` in this case)."""
    from open_edit.serve.visual_verify import parse_verdict
    r = parse_verdict("Done. Rendered successfully.")
    assert r["verdict"] == "unknown"
    assert r["source"] == "model_no_verdict_line"
