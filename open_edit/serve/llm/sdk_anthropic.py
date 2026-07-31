"""Anthropic SDK streaming provider."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from .. import cost as cost_mod
from .keys import _api_key, _max_tokens, _model
from .events import StreamEvent


async def _stream_anthropic(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system: str,
    model: str | None = None,
) -> AsyncIterator[StreamEvent]:
    # Check the API key before attempting the import so that a missing key
    # raises a clean RuntimeError (caught by the caller) rather than being
    # shadowed by an ImportError when the anthropic package is absent.
    api_key = _api_key("anthropic")
    import anthropic  # type: ignore

    client = anthropic.AsyncAnthropic(api_key=api_key)

    # Anthropic SDK streaming event names are stable across versions.
    async with client.messages.stream(
        model=model or _model(),
        max_tokens=_max_tokens(),
        system=system,
        messages=messages,
        tools=tools or anthropic.NOT_GIVEN,  # type: ignore[attr-defined]
    ) as stream:
        # We accumulate tool_use blocks manually because the high-level
        # ``stream.text()`` helper doesn't surface tool calls cleanly.
        current_tool: dict[str, Any] | None = None
        current_tool_input_json = ""

        async for event in stream:
            etype = event.type

            if etype == "content_block_start":
                block = event.content_block
                if getattr(block, "type", None) == "tool_use":
                    current_tool = {
                        "id": block.id,
                        "name": block.name,
                    }
                    current_tool_input_json = ""

            elif etype == "content_block_delta":
                delta = event.delta
                dtype = getattr(delta, "type", None)
                if dtype == "text_delta":
                    text = getattr(delta, "text", "")
                    if text:
                        yield {"type": "text_delta", "text": text}
                elif dtype == "input_json_delta":
                    partial = getattr(delta, "partial_json", "")
                    if partial:
                        current_tool_input_json += partial

            elif etype == "content_block_stop":
                if current_tool is not None:
                    parsed_input: dict[str, Any] = {}
                    raw = current_tool_input_json.strip()
                    if raw:
                        try:
                            parsed = json.loads(raw)
                            parsed_input = parsed if isinstance(parsed, dict) else {"value": parsed}
                        except json.JSONDecodeError:
                            # Forward the raw string so the agent loop can
                            # surface a useful error rather than crash.
                            parsed_input = {"_raw": raw}
                    yield {
                        "type": "tool_use",
                        "id": current_tool["id"],
                        "name": current_tool["name"],
                        "input": parsed_input,
                    }
                    current_tool = None
                    current_tool_input_json = ""

            elif etype == "message_stop":
                final = await stream.get_final_message()
                # v1.4 P1-3: emit a ``usage`` event so the agent
                # loop can compute and surface per-turn cost. We
                # compute the cost here from the SDK's usage
                # object + the pricing config; the agent loop
                # aggregates across the turn.
                usage_obj = getattr(final, "usage", None)
                if usage_obj is not None:
                    usage_dict = {
                        "input_tokens": int(getattr(usage_obj, "input_tokens", 0) or 0),
                        "output_tokens": int(getattr(usage_obj, "output_tokens", 0) or 0),
                        "cache_creation_input_tokens": int(
                            getattr(usage_obj, "cache_creation_input_tokens", 0) or 0
                        ),
                        "cache_read_input_tokens": int(
                            getattr(usage_obj, "cache_read_input_tokens", 0) or 0
                        ),
                    }
                    cost_result = cost_mod.compute_anthropic_cost(
                        usage_dict, model or _model(),
                    )
                    if cost_result is None:
                        yield {
                            "type": "usage",
                            "source": "unavailable",
                            "tokens": sum(usage_dict.values()),
                            "cost_usd": 0.0,
                            "usage": usage_dict,
                        }
                    else:
                        tokens, cost_usd = cost_result
                        yield {
                            "type": "usage",
                            "source": "computed",
                            "tokens": tokens,
                            "cost_usd": cost_usd,
                            "usage": usage_dict,
                        }
                yield {
                    "type": "done",
                    "stop_reason": final.stop_reason or "end_turn",
                }
