"""Tests for the ``usage`` StreamEvent emitted by ``open_edit.serve.llm``.

The agent loop aggregates these per-turn to emit a ``cost_update`` event
to the frontend, so the LLM layer must surface cost data:

- ``pi`` path: read the session JSONL after the subprocess exits
  and yield a ``usage`` event with the delta cost.
- ``anthropic`` path: capture the final ``usage`` object from the
  streaming response and yield it as a ``usage`` event.
- ``openai`` path: same, with the OpenAI shape.

We use fake ``pi`` / anthropic / openai binaries to drive the streams,
so the tests don't need real API keys.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, AsyncIterator

import pytest

_THIS_DIR = Path(__file__).resolve()
_REPO_ROOT = _THIS_DIR.parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from open_edit.serve.llm import (  # noqa: E402
    StreamEvent,
    stream_chat,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _collect(stream: AsyncIterator[StreamEvent]) -> list[StreamEvent]:
    out = []
    async for ev in stream:
        out.append(ev)
    return out


# ---------------------------------------------------------------------------
# pi path: usage event derived from session JSONL
# ---------------------------------------------------------------------------

FAKE_PI_SCRIPT_WITH_USAGE = """\
#!/usr/bin/env python3
import json, os, sys
from pathlib import Path

# A minimal session event stream — text + done. The cost is read
# from the session file by the LLM layer, not the fake pi binary.
EVENTS = [
    {"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": "ok"}},
    {"type": "agent_settled"},
]
for ev in EVENTS:
    sys.stdout.write(json.dumps(ev) + "\\n")
    sys.stdout.flush()

# Mirror real pi's behavior: append an assistant-message entry to
# the session JSONL. Real pi writes per-call usage; we do the same
# so the LLM layer's delta parser has something to read.
session_id = ""
for i, a in enumerate(sys.argv):
    if a == "--session-id" and i + 1 < len(sys.argv):
        session_id = sys.argv[i + 1]
        break

sessions_dir = os.environ.get("OPEN_EDIT_PI_SESSIONS_DIR", "")
if sessions_dir and session_id:
    cwd = os.getcwd()
    encoded = "-" + cwd.replace("/", "-") + "-"
    sess_dir = Path(sessions_dir) / encoded
    suffix = "_" + session_id + ".jsonl"
    if sess_dir.exists():
        for entry in sess_dir.iterdir():
            if entry.is_file() and entry.name.endswith(suffix):
                with entry.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({
                        "type": "message",
                        "id": "m-fake-1",
                        "timestamp": "2026-07-21T00:00:00.000Z",
                        "message": {
                            "role": "assistant",
                            "content": [{"type": "text", "text": "ok"}],
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
                    }) + "\\n")
                break
sys.exit(0)
"""


def _write_session_jsonl(path: Path, assistant_messages: list[dict]) -> None:
    """Write a session JSONL with the requested assistant message
    usage entries. Used to simulate pi's already-written session file."""
    with path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "type": "session",
            "version": 3,
            "id": "test-session",
            "timestamp": "2026-07-21T00:00:00.000Z",
            "cwd": "/tmp",
        }) + "\n")
        for i, m in enumerate(assistant_messages):
            fh.write(json.dumps({
                "type": "message",
                "id": f"m{i}",
                "timestamp": "2026-07-21T00:00:00.000Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "x"}],
                    "model": "minimax-m3",
                    "usage": m,
                },
            }) + "\n")


@pytest.fixture
def fake_pi_with_usage(tmp_path, monkeypatch):
    """Fake pi binary + a pi session dir with a pre-created session file.
    The session file has a session header but no assistant messages yet.
    When pi runs (fake pi), it finds this file via ``--session-id`` and
    appends an assistant message with usage data.
    """
    script = tmp_path / "fake-pi"
    script.write_text(FAKE_PI_SCRIPT_WITH_USAGE)
    script.chmod(0o755)
    monkeypatch.setenv("OPEN_EDIT_PI_BINARY", str(script))
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "pi")
    monkeypatch.setenv("OPEN_EDIT_LLM_MODEL", "minimax-m3")
    # Set up pi sessions dir (mimics ~/.pi/agent/sessions/).
    sessions_dir = tmp_path / "pi-sessions"
    sessions_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("OPEN_EDIT_PI_SESSIONS_DIR", str(sessions_dir))
    # Create the encoded-cwd subdirectory and session file.
    cwd = os.getcwd()
    encoded = "-" + cwd.replace("/", "-") + "-"
    sess_subdir = sessions_dir / encoded
    sess_subdir.mkdir(parents=True, exist_ok=True)
    session_file = sess_subdir / f"2026-07-21T00-00-00-000Z_test-session.jsonl"
    _write_session_jsonl(session_file, [])
    return {
        "script": script,
        "session_file": session_file,
        "test_cwd": cwd,
    }


def test_pi_path_yields_usage_event_after_done(fake_pi_with_usage, tmp_path):
    """After pi exits, the LLM layer should yield a ``usage`` event
    whose payload matches the assistant message the fake pi
    appended to the session JSONL during the turn."""
    ctx = fake_pi_with_usage

    # Stub the extension check (fake pi ignores it but the code still
    # checks for the file).
    from open_edit.serve.llm import _pi_extension_path
    ext = _pi_extension_path()
    if not Path(ext).is_file():
        Path(ext).parent.mkdir(parents=True, exist_ok=True)
        Path(ext).write_text("// stub\n")

    events = asyncio.run(_collect(stream_chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system="",
        session_id="test-session",
        project_path=str(ctx["test_cwd"]),
    )))
    types = [e["type"] for e in events]
    # Must contain a usage event after the done event.
    assert "usage" in types, f"no usage event in {types}"
    usage = next(e for e in events if e["type"] == "usage")
    # Per the brief: source is one of "pi" | "computed" | "unavailable".
    # For the pi path that successfully reads the session file, source="pi".
    assert usage["source"] == "pi"
    # Tokens and cost should match what fake pi wrote to the session file.
    assert usage["tokens"] == 150
    assert usage["cost_usd"] == pytest.approx(0.0003, abs=1e-9)


def test_pi_path_yields_unavailable_when_session_file_missing(
    tmp_path, monkeypatch,
):
    """If pi didn't write a session file (e.g. first-ever run, or
    pi's sessions dir is missing), the usage event should report
    source=unavailable with zero cost — the agent loop will then
    show the honest ``cost n/a (subscription)`` UI."""
    script = tmp_path / "fake-pi"
    script.write_text(FAKE_PI_SCRIPT_WITH_USAGE)
    script.chmod(0o755)
    monkeypatch.setenv("OPEN_EDIT_PI_BINARY", str(script))
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "pi")
    monkeypatch.setenv("OPEN_EDIT_LLM_MODEL", "minimax-m3")
    # Empty sessions dir — no file at all.
    empty_sessions = tmp_path / "sessions-empty"
    empty_sessions.mkdir()
    monkeypatch.setenv("OPEN_EDIT_PI_SESSIONS_DIR", str(empty_sessions))

    from open_edit.serve.llm import _pi_extension_path
    ext = _pi_extension_path()
    if not Path(ext).is_file():
        Path(ext).parent.mkdir(parents=True, exist_ok=True)
        Path(ext).write_text("// stub\n")

    # Create the project dir so the --session path resolves correctly.
    project_dir = tmp_path / "project-unavailable"
    project_dir.mkdir(parents=True)

    events = asyncio.run(_collect(stream_chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system="",
        session_id="missing-session",
        project_path=str(project_dir),
    )))
    usage = next((e for e in events if e["type"] == "usage"), None)
    assert usage is not None, f"no usage event in {[e['type'] for e in events]}"
    assert usage["source"] == "unavailable"
    assert usage["tokens"] == 0
    assert usage["cost_usd"] == 0.0


# ---------------------------------------------------------------------------
# Anthropic path: usage event from SDK's final usage object
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
    sdk, fake_usage = fake_anthropic_sdk
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

def test_pi_path_emits_done_after_usage(fake_pi_with_usage):
    """The wire contract is: ``usage`` arrives just before ``done``
    (after the assistant's last text/tool). Tests pin that order so
    the frontend's event dispatch can rely on it."""
    ctx = fake_pi_with_usage
    from open_edit.serve.llm import _pi_extension_path
    ext = _pi_extension_path()
    if not Path(ext).is_file():
        Path(ext).parent.mkdir(parents=True, exist_ok=True)
        Path(ext).write_text("// stub\n")

    events = asyncio.run(_collect(stream_chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system="",
        session_id="test-session",
        project_path=str(ctx["test_cwd"]),
    )))
    types = [e["type"] for e in events]
    # The done must be the last event.
    assert types[-1] == "done"
    # usage must appear before done.
    if "usage" in types:
        assert types.index("usage") < types.index("done")


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
