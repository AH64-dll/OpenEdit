"""Tests for the v1.7 opencode CLI event normalizer.

Mirrors the structure of ``test_serve_llm_pi.py``: we feed the
normalizer a sequence of raw stdout lines (as bytes, like a real
subprocess would emit) and assert the yielded events match the
project-wide ``StreamEvent`` shape.
"""
from __future__ import annotations

import json
from typing import AsyncIterator

import pytest

from open_edit.serve.opencode_adapter import parse_opencode_events


async def _feed(lines: list[str]) -> list[dict]:
    """Helper: feed a list of strings as bytes through the parser."""
    async def src() -> AsyncIterator[bytes]:
        for line in lines:
            yield (line + "\n").encode("utf-8")
    out: list[dict] = []
    async for ev in parse_opencode_events(src()):
        out.append(ev)
    return out


@pytest.mark.asyncio
async def test_normalize_text_event_yields_text_delta() -> None:
    raw = json.dumps({
        "type": "text",
        "timestamp": 1784700188886,
        "sessionID": "ses_abc",
        "part": {
            "id": "prt_x",
            "messageID": "msg_y",
            "sessionID": "ses_abc",
            "type": "text",
            "text": "Hello there!",
        },
    })
    events = await _feed([raw])
    assert events == [{"type": "text_delta", "text": "Hello there!"}]


@pytest.mark.asyncio
async def test_normalize_step_finish_yields_usage_and_done() -> None:
    raw = json.dumps({
        "type": "step_finish",
        "timestamp": 1784700188904,
        "sessionID": "ses_abc",
        "part": {
            "id": "prt_z",
            "messageID": "msg_y",
            "sessionID": "ses_abc",
            "type": "step-finish",
            "reason": "stop",
            "tokens": {
                "total": 100,
                "input": 80,
                "output": 10,
                "reasoning": 10,
                "cache": {"write": 0, "read": 0},
            },
            "cost": 0.0,
        },
    })
    events = await _feed([raw])
    # The order is: usage, then done. We assert the two events exist
    # with the expected keys rather than pinning the exact order, so
    # a future refactor that interleaves differently doesn't break
    # the test for no good reason.
    types = [e["type"] for e in events]
    assert "usage" in types
    assert "done" in types
    usage = next(e for e in events if e["type"] == "usage")
    assert usage["source"] == "computed"  # opencode gives us cost directly
    assert usage["cost_usd"] == 0.0
    assert usage["tokens"] == 100
    assert usage["usage"]["input_tokens"] == 80
    done = next(e for e in events if e["type"] == "done")
    assert done["stop_reason"] == "end_turn"  # reason "stop" maps to end_turn


@pytest.mark.asyncio
async def test_normalize_error_event_yields_error() -> None:
    raw = json.dumps({
        "type": "error",
        "timestamp": 1784700246540,
        "sessionID": "ses_abc",
        "error": {"name": "UnknownError", "data": {"message": "boom"}},
    })
    events = await _feed([raw])
    assert events == [{"type": "error", "message": "boom"}]


@pytest.mark.asyncio
async def test_normalize_step_start_yields_nothing() -> None:
    raw = json.dumps({
        "type": "step_start",
        "timestamp": 1, "sessionID": "s",
        "part": {"id": "p", "messageID": "m", "sessionID": "s", "type": "step-start"},
    })
    events = await _feed([raw])
    assert events == []


@pytest.mark.asyncio
async def test_normalize_skips_blank_and_garbage_lines() -> None:
    events = await _feed(["", "not json", "  ", json.dumps({"type": "text", "part": {"text": "hi"}})])
    # The valid line yields one text_delta; the others are skipped.
    assert {"type": "text_delta", "text": "hi"} in events
    # No spurious events.
    assert all(e["type"] in ("text_delta", "tool_use", "tool_result", "usage", "done", "error") for e in events)


@pytest.mark.asyncio
async def test_normalize_max_tokens_stop_reason() -> None:
    raw = json.dumps({
        "type": "step_finish",
        "part": {
            "type": "step-finish",
            "reason": "length",
            "tokens": {"total": 1, "input": 1, "output": 0, "reasoning": 0, "cache": {"write": 0, "read": 0}},
            "cost": 0.0,
        },
    })
    events = await _feed([raw])
    done = next(e for e in events if e["type"] == "done")
    assert done["stop_reason"] == "max_tokens"
