"""OpenAI SDK streaming provider (optional; minimal but functional)."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from .. import cost as cost_mod
from .keys import _api_key, _model
from .events import StreamEvent


async def _stream_openai(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system: str,
    model: str | None = None,
) -> AsyncIterator[StreamEvent]:
    """OpenAI-compatible streaming.

    Converts the Anthropic-style ``tools`` spec to OpenAI's function-calling
    format on the fly. Only the subset of features Open Edit uses is
    implemented.
    """
    import openai  # type: ignore

    client = openai.AsyncOpenAI(api_key=_api_key("openai"))

    # Convert messages: Anthropic blocks -> OpenAI role/content
    oai_messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if isinstance(content, str):
            oai_messages.append({"role": role, "content": content})
        elif isinstance(content, list):
            # Anthropic blocks -> OpenAI parts
            parts: list[dict[str, Any]] = []
            for block in content:
                btype = block.get("type")
                if btype == "text":
                    parts.append({"type": "text", "text": block.get("text", "")})
                elif btype == "tool_use":
                    parts.append({
                        "type": "function",
                        "id": block.get("id"),
                        "function": {
                            "name": block.get("name"),
                            "arguments": json.dumps(block.get("input", {})),
                        },
                    })
                elif btype == "tool_result":
                    parts.append({
                        "role": "tool",
                        "tool_call_id": block.get("tool_use_id"),
                        "content": json.dumps(block.get("content", "")),
                    })
            oai_messages.append({"role": role, "content": parts})

    # Convert tool specs: Anthropic -> OpenAI
    oai_tools = [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]

    stream = await client.chat.completions.create(
        model=model or _model(),
        messages=oai_messages,
        tools=oai_tools or None,
        stream=True,
    )

    # Accumulate tool calls by index, emit each when the tool_call finishes.
    pending_tools: dict[int, dict[str, Any]] = {}
    finish_reason = "stop"
    # v1.4 P1-3: the OpenAI SDK only carries the usage object on
    # the LAST chunk (with finish_reason set). We capture the
    # latest usage we see, then emit it as a ``usage`` event after
    # the loop.
    last_usage: Any = None

    async for chunk in stream:
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        delta = choice.delta
        if delta.content:
            yield {"type": "text_delta", "text": delta.content}
        if delta.tool_calls:
            for call in delta.tool_calls:
                idx = call.index
                if idx not in pending_tools:
                    pending_tools[idx] = {
                        "id": call.id or "",
                        "name": (call.function.name if call.function else "") or "",
                        "args_json": "",
                    }
                else:
                    if call.id:
                        pending_tools[idx]["id"] = call.id
                    if call.function and call.function.name:
                        pending_tools[idx]["name"] = call.function.name
                if call.function and call.function.arguments:
                    pending_tools[idx]["args_json"] += call.function.arguments
        if choice.finish_reason:
            finish_reason = choice.finish_reason
        # The usage object lives at chunk.usage, not on the choice.
        chunk_usage = getattr(chunk, "usage", None)
        if chunk_usage is not None:
            last_usage = chunk_usage

    # Emit accumulated tool calls
    for idx in sorted(pending_tools.keys()):
        tool = pending_tools[idx]
        try:
            parsed = json.loads(tool["args_json"] or "{}")
        except json.JSONDecodeError:
            parsed = {"_raw": tool["args_json"]}
        yield {
            "type": "tool_use",
            "id": tool["id"],
            "name": tool["name"],
            "input": parsed,
        }

    # v1.4 P1-3: emit a ``usage`` event if the SDK gave us usage
    # data. The cost math happens here (against pricing.json) so
    # the agent loop can just aggregate per-call costs.
    if last_usage is not None:
        usage_dict = {
            "prompt_tokens": int(getattr(last_usage, "prompt_tokens", 0) or 0),
            "completion_tokens": int(getattr(last_usage, "completion_tokens", 0) or 0),
        }
        details = getattr(last_usage, "prompt_tokens_details", None)
        if details is not None:
            usage_dict["prompt_tokens_details"] = {
                "cached_tokens": int(getattr(details, "cached_tokens", 0) or 0),
            }
        cost_result = cost_mod.compute_openai_cost(usage_dict, model or _model())
        if cost_result is None:
            yield {
                "type": "usage",
                "source": "unavailable",
                "tokens": sum(v for k, v in usage_dict.items() if isinstance(v, int)),
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

    # Map OpenAI finish_reason -> Anthropic-style stop_reason
    stop_map = {
        "stop": "end_turn",
        "tool_calls": "tool_use",
        "length": "max_tokens",
        "function_call": "tool_use",
    }
    yield {"type": "done", "stop_reason": stop_map.get(finish_reason, "end_turn")}
