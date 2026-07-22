"""v1.7 — opencode CLI event normalizer.

Reads a sequence of bytes from an ``opencode run --format json``
subprocess stdout and yields ``StreamEvent``-shaped dicts (the same
shape ``open_edit.serve.llm._stream_pi`` yields).

The captured spike output (see design spec §2, Q1) shows the
opencode event vocabulary is different from pi's:

- ``step_start`` / ``step_finish`` bracket a turn (we ignore
  step_start; step_finish carries tokens + cost + stop reason).
- ``text`` carries the actual model output text in
  ``part.text``.
- ``error`` is a top-level event; we forward the message.

We deliberately do NOT implement tool-call parsing here — the
opencode adapter has ``supports_tools() == False`` in v1.7, so
the chat frontend never offers tool-triggering actions. If a
``toolCall`` event ever does arrive, it is ignored (logged to
stderr for debugging).
"""
from __future__ import annotations

import json
import sys
from typing import Any, AsyncIterator


_STOP_REASON_MAP = {
    "stop": "end_turn",
    "length": "max_tokens",
    "tool_use": "tool_use",
}


def _map_stop_reason(reason: str | None) -> str:
    if not reason:
        return "end_turn"
    return _STOP_REASON_MAP.get(reason, reason)


def _usage_from_part(part: dict[str, Any]) -> dict[str, Any] | None:
    """Map opencode's ``part.tokens`` + ``part.cost`` to our usage shape."""
    tokens = part.get("tokens") or {}
    if not isinstance(tokens, dict):
        return None
    input_tokens = int(tokens.get("input", 0) or 0)
    output_tokens = int(tokens.get("output", 0) or 0)
    cache = tokens.get("cache") or {}
    cache_read = int(cache.get("read", 0) or 0)
    cache_write = int(cache.get("write", 0) or 0)
    reasoning = int(tokens.get("reasoning", 0) or 0)
    cost_usd = float(part.get("cost", 0) or 0)
    total = int(
        tokens.get("total", input_tokens + output_tokens + cache_read + cache_write + reasoning)
        or (input_tokens + output_tokens + cache_read + cache_write + reasoning)
    )
    return {
        "type": "usage",
        "source": "computed",  # opencode gives us cost directly
        "tokens": total,
        "cost_usd": cost_usd,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": cache_write,
            "reasoning_tokens": reasoning,
        },
    }


async def parse_opencode_events(
    stdout: AsyncIterator[bytes],
) -> AsyncIterator[dict[str, Any]]:
    """Read raw stdout lines from ``opencode run --format json`` and yield
    ``StreamEvent``-shaped dicts.

    Yields:
      - ``{"type": "text_delta", "text": "..."}`` for each ``text`` event
      - ``{"type": "usage", "source": "computed", ...}`` for each
        ``step_finish`` event
      - ``{"type": "done", "stop_reason": "..."}`` for each
        ``step_finish`` event
      - ``{"type": "error", "message": "..."}`` for each ``error`` event
    """
    async for raw in stdout:
        try:
            line = raw.decode("utf-8", errors="replace").strip()
        except Exception:
            continue
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        et = obj.get("type")
        if et == "text":
            part = obj.get("part") or {}
            text = part.get("text") if isinstance(part, dict) else None
            if isinstance(text, str) and text:
                yield {"type": "text_delta", "text": text}
        elif et == "step_finish":
            part = obj.get("part") or {}
            if isinstance(part, dict):
                usage = _usage_from_part(part)
                if usage is not None:
                    yield usage
                yield {
                    "type": "done",
                    "stop_reason": _map_stop_reason(part.get("reason")),
                }
        elif et == "error":
            err = obj.get("error") or {}
            msg = "<unknown>"
            if isinstance(err, dict):
                data = err.get("data") or {}
                if isinstance(data, dict) and data.get("message"):
                    msg = str(data["message"])
                else:
                    msg = str(err.get("name") or msg)
            yield {"type": "error", "message": msg}
        elif et == "step_start":
            continue
        elif et == "toolCall":
            # Opencode has no open_edit tool extension in v1.7; if a
            # tool call somehow arrives, we drop it (rather than try
            # to execute) and log so the operator can see it.
            print(
                "opencode_adapter: ignoring toolCall event (no extension in v1.7)",
                file=sys.stderr,
            )
        # All other event types are silently dropped — the spike
        # showed only step_start/text/step_finish/error as real
        # events, and adding a noisy "unknown event" log here would
        # just spam operators when opencode adds new event types.
