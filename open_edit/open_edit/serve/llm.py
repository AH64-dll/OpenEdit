"""Async streaming LLM client for the Open Edit server.

Default backend: Anthropic (``claude-sonnet-4-5``). The shape of
``stream_chat`` is intentionally generic so swapping to OpenAI later
only requires adding a sibling ``_stream_openai`` function and routing
based on ``OPEN_EDIT_LLM_PROVIDER``.

Environment
-----------
``OPEN_EDIT_LLM_API_KEY``    — required. API key for the chosen provider.
``OPEN_EDIT_LLM_MODEL``      — model name (default ``claude-sonnet-4-5``).
``OPEN_EDIT_LLM_PROVIDER``   — ``anthropic`` (default) or ``openai``.
``OPEN_EDIT_LLM_MAX_TOKENS`` — per-turn cap (default 4096).
"""
from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator, Literal, TypedDict

# ``anthropic`` is listed as a hard dependency in pyproject.toml. We import
# lazily inside ``stream_chat`` so the module can still be imported in test
# environments that mock the SDK away.


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

class StreamEvent(TypedDict):
    """One event emitted by ``stream_chat``.

    Variants:
    - ``{"type": "text_delta", "text": "..."}``
      — a chunk of assistant text (already delta-decoded)
    - ``{"type": "tool_use", "id": "...", "name": "...", "input": {...}}``
      — a fully-assembled tool_use block (input JSON already parsed)
    - ``{"type": "done", "stop_reason": "..."}``
      — final event; ``stop_reason`` is the model's stop reason
      (``end_turn`` / ``tool_use`` / ``max_tokens`` / ``stop_sequence``)
    """
    type: Literal["text_delta", "tool_use", "done"]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _api_key() -> str:
    key = os.environ.get("OPEN_EDIT_LLM_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "OPEN_EDIT_LLM_API_KEY is not set. Set it to your Anthropic "
            "(or OpenAI) API key before starting the server."
        )
    return key


def _model() -> str:
    return os.environ.get("OPEN_EDIT_LLM_MODEL", "claude-sonnet-4-5").strip()


def _provider() -> str:
    return os.environ.get("OPEN_EDIT_LLM_PROVIDER", "anthropic").strip().lower()


def _max_tokens() -> int:
    try:
        return int(os.environ.get("OPEN_EDIT_LLM_MAX_TOKENS", "4096"))
    except ValueError:
        return 4096


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def stream_chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system: str,
) -> AsyncIterator[StreamEvent]:
    """Stream an LLM response as a sequence of :class:`StreamEvent`.

    ``messages`` is the standard Anthropic messages list. ``tools`` is the
    Anthropic tools spec (list of ``{"name", "description", "input_schema"}``
    dicts). ``system`` is the system prompt.

    The function is an async generator — callers iterate it with
    ``async for event in stream_chat(...):``.

    Tool inputs are accumulated from ``input_json_delta`` events and only
    emitted once the block is closed (so callers receive one fully-formed
    ``tool_use`` event per tool call, not a stream of partial JSON).
    """
    if _provider() == "openai":
        async for ev in _stream_openai(messages, tools, system):
            yield ev
        return

    async for ev in _stream_anthropic(messages, tools, system):
        yield ev


# ---------------------------------------------------------------------------
# Anthropic implementation
# ---------------------------------------------------------------------------

async def _stream_anthropic(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system: str,
) -> AsyncIterator[StreamEvent]:
    import anthropic  # type: ignore

    client = anthropic.AsyncAnthropic(api_key=_api_key())

    # Anthropic SDK streaming event names are stable across versions.
    async with client.messages.stream(
        model=_model(),
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
                            if isinstance(parsed, dict):
                                parsed_input = parsed
                            else:
                                parsed_input = {"value": parsed}
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
                yield {
                    "type": "done",
                    "stop_reason": final.stop_reason or "end_turn",
                }


# ---------------------------------------------------------------------------
# OpenAI implementation (optional; minimal but functional)
# ---------------------------------------------------------------------------

async def _stream_openai(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system: str,
) -> AsyncIterator[StreamEvent]:
    """OpenAI-compatible streaming.

    Converts the Anthropic-style ``tools`` spec to OpenAI's function-calling
    format on the fly. Only the subset of features Open Edit uses is
    implemented.
    """
    import openai  # type: ignore

    client = openai.AsyncOpenAI(api_key=_api_key())

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
        model=_model(),
        messages=oai_messages,
        tools=oai_tools or None,
        stream=True,
    )

    # Accumulate tool calls by index, emit each when the tool_call finishes.
    pending_tools: dict[int, dict[str, Any]] = {}
    finish_reason = "stop"

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

    # Map OpenAI finish_reason -> Anthropic-style stop_reason
    stop_map = {
        "stop": "end_turn",
        "tool_calls": "tool_use",
        "length": "max_tokens",
        "function_call": "tool_use",
    }
    yield {"type": "done", "stop_reason": stop_map.get(finish_reason, "end_turn")}
