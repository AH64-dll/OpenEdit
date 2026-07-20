"""Async streaming LLM client for the Open Edit server.

Three backends supported via ``OPEN_EDIT_LLM_PROVIDER``:

- ``anthropic`` (default) — direct Anthropic SDK streaming.
- ``openai``              — direct OpenAI SDK streaming.
- ``pi``                  — spawn the ``pi`` CLI as a subprocess and parse
                            its JSON output. The pi process loads our
                            ``open_edit/serve/pi_extension/extension.ts``
                            which registers the 11 Open Edit tools.

Environment
-----------
``OPEN_EDIT_LLM_API_KEY``    — required for anthropic/openai.
``OPEN_EDIT_LLM_MODEL``      — model name (default ``claude-sonnet-4-5`` for
                                anthropic, ``gpt-4o`` for openai, ``minimax-m3``
                                for pi).
``OPEN_EDIT_LLM_PROVIDER``   — ``anthropic`` | ``openai`` | ``pi`` (default
                                ``anthropic``).
``OPEN_EDIT_LLM_MAX_TOKENS`` — per-turn cap (default 4096). Anthropic only.
``OPEN_EDIT_PI_BINARY``      — path to the ``pi`` binary (default: from PATH).
``OPEN_EDIT_PI_EXTENSION``   — path to the open_edit pi extension .ts file
                                (default: ``<pkg>/serve/pi_extension/extension.ts``).
``OPEN_EDIT_PI_PROVIDER``    — provider name passed to pi (default ``opencode-go``).
``OPEN_EDIT_PI_SESSION_ID``  — pi session id (set per-WS connection).
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
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
    session_id: str | None = None,
    project_path: str | None = None,
) -> AsyncIterator[StreamEvent]:
    """Stream an LLM response as a sequence of :class:`StreamEvent`.

    ``messages`` is the standard Anthropic messages list. ``tools`` is the
    Anthropic tools spec (list of ``{"name", "description", "input_schema"}``
    dicts). ``system`` is the system prompt. ``session_id`` is used by the
    ``pi`` provider to maintain a persistent session across turns.
    ``project_path`` is used by the ``pi`` provider to tell the extension
    which project to operate on (via ``OPEN_EDIT_PROJECT`` env var).

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
    if _provider() == "pi":
        async for ev in _stream_pi(messages, tools, system, session_id, project_path):
            yield ev
        return

    async for ev in _stream_anthropic(messages, tools, system):
        yield ev


# ---------------------------------------------------------------------------
# Pi implementation
# ---------------------------------------------------------------------------

def _pi_binary() -> str:
    return os.environ.get("OPEN_EDIT_PI_BINARY", "").strip() or shutil.which("pi") or "pi"


def _pi_extension_path() -> str:
    """Default: <open_edit>/serve/pi_extension/extension.ts"""
    explicit = os.environ.get("OPEN_EDIT_PI_EXTENSION", "").strip()
    if explicit:
        return explicit
    # llm.py is at <pkg>/open_edit/serve/llm.py; extension is at
    # <pkg>/open_edit/serve/pi_extension/extension.ts
    here = Path(__file__).resolve()
    return str(here.parent / "pi_extension" / "extension.ts")


def _pi_provider_name() -> str:
    return os.environ.get("OPEN_EDIT_PI_PROVIDER", "opencode-go").strip()


def _pi_model() -> str:
    return os.environ.get("OPEN_EDIT_LLM_MODEL", "minimax-m3").strip()


async def _stream_pi(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system: str,
    session_id: str | None,
    project_path: str | None = None,
) -> AsyncIterator[StreamEvent]:
    """Spawn the ``pi`` CLI as a subprocess and parse its JSON output.

    Pi manages its own conversation state (per session_id). We:
    1. Pass the user message via ``--print``.
    2. Append our system prompt via ``--append-system-prompt``.
    3. Load the open_edit pi extension (registers the 11 tools).
    4. Read JSON-line events from stdout; map to our StreamEvent shape.

    The ``messages`` and ``tools`` args are ignored — pi has its own
    history and tool registry. ``project_path`` (if given) is passed
    to the subprocess as ``OPEN_EDIT_PROJECT`` so the extension knows
    which project to operate on.
    """
    # Pull the last user message text from the messages list.
    user_text = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content")
            if isinstance(content, str):
                user_text = content
            elif isinstance(content, list):
                for blk in content:
                    if isinstance(blk, dict) and blk.get("type") == "text":
                        user_text = blk.get("text", "")
                        break
            break

    if not user_text:
        yield {
            "type": "error",
            "message": "pi provider: no user message found in messages list",
        }
        return

    sid = session_id or f"oe-{os.getpid()}"
    ext_path = _pi_extension_path()
    if not Path(ext_path).is_file():
        yield {
            "type": "error",
            "message": f"pi provider: extension not found at {ext_path}",
        }
        return

    cmd = [
        _pi_binary(),
        "--provider", _pi_provider_name(),
        "--model", _pi_model(),
        "--mode", "json",
        "--no-extensions",       # we load the extension explicitly below
        "--extension", ext_path,
        "--session-id", sid,
        "--print", user_text,
        "--append-system-prompt", system,
    ]

    env = dict(os.environ)
    # The open_edit package root needs to be on PYTHONPATH so the
    # subprocess can import open_edit.serve.pi_bridge.
    pkg_root = str(Path(__file__).resolve().parents[2])  # .../open_edit
    env["PYTHONPATH"] = (
        pkg_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    )
    # The TS extension reads OPEN_EDIT_PROJECT to know which project to
    # operate on (passed to the pi_bridge subprocess).
    if project_path:
        env["OPEN_EDIT_PROJECT"] = str(project_path)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    except FileNotFoundError as exc:
        yield {"type": "error", "message": f"pi binary not found: {exc}"}
        return

    stop_reason = "end_turn"
    saw_text = False
    try:
        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            for ev in _pi_normalize_event(obj):
                if ev.get("type") == "done":
                    stop_reason = ev.get("stop_reason", stop_reason)
                if ev.get("type") == "text_delta":
                    saw_text = True
                yield ev
        await proc.wait()
    except asyncio.CancelledError:
        try:
            proc.kill()
        except Exception:
            pass
        raise

    if proc.returncode != 0 and not saw_text:
        stderr = (await proc.stderr.read()).decode("utf-8", "replace").strip() if proc.stderr else ""
        yield {
            "type": "error",
            "message": stderr or f"pi exited {proc.returncode}",
        }
        return

    yield {"type": "done", "stop_reason": stop_reason}


def _pi_normalize_event(obj: dict[str, Any]) -> list[StreamEvent]:
    """Map one pi JSON event to one or more of our StreamEvent dicts.

    Pi's event types we care about:
    - ``message_update`` with ``assistantMessageEvent.type=text_delta`` and
      ``delta: "..."`` → emit a ``text_delta``.
    - ``message_end`` with ``role=assistant`` and ``content[*].type=toolCall``
      → emit a ``tool_use`` (accumulated; tool name + id + parsed args).
    - ``message_end`` with ``role=toolResult`` → emit a ``tool_result``
      with the tool's output (we do NOT re-execute the tool; the pi
      extension already ran it via the bridge).
    - ``turn_end`` → caller derives ``done`` from the absence of tool_use.
    - ``agent_end`` → already accounted for by the done emit.
    - ``error`` → emit ``error``.

    Tool inputs are emitted as already-parsed dicts (pi may emit the
    arguments as a JSON string; we parse defensively).
    """
    et = obj.get("type")
    if et == "message_update":
        ame = obj.get("assistantMessageEvent") or {}
        if ame.get("type") == "text_delta":
            delta = ame.get("delta") or ""
            if delta:
                return [{"type": "text_delta", "text": delta}]
        return []
    if et == "message_end":
        msg = obj.get("message") or {}
        role = msg.get("role")
        content = msg.get("content") or []
        if not isinstance(content, list):
            return []

        # toolResult message: pi has already run the tool (via the
        # extension), so we just forward the result to the agent loop.
        if role == "toolResult":
            tool_name = msg.get("toolName", "")
            tool_call_id = msg.get("toolCallId", "")
            is_error = bool(msg.get("isError"))
            # The result content is typically a list of {type:"text", text:"..."}
            # blocks; the first one is the JSON the bridge emitted.
            result_text = ""
            if content and isinstance(content[0], dict):
                result_text = content[0].get("text", "")
            # Parse the JSON if possible.
            try:
                parsed_result = json.loads(result_text) if result_text else {}
            except json.JSONDecodeError:
                parsed_result = {"raw": result_text}
            if is_error:
                err_msg = (
                    parsed_result.get("error", "unknown")
                    if isinstance(parsed_result, dict) else str(parsed_result)
                )
                return [{
                    "type": "tool_result",
                    "name": tool_name,
                    "result": parsed_result if isinstance(parsed_result, dict) else {"value": parsed_result},
                    "is_error": True,
                    "tool_use_id": tool_call_id,
                    "error_message": err_msg,
                }]
            return [{
                "type": "tool_result",
                "name": tool_name,
                "result": parsed_result,
                "tool_use_id": tool_call_id,
            }]

        if role != "assistant":
            return []
        out: list[StreamEvent] = []
        for blk in content:
            if not isinstance(blk, dict):
                continue
            btype = blk.get("type")
            if btype == "toolCall":
                raw_args = blk.get("arguments", {})
                if isinstance(raw_args, str):
                    try:
                        raw_args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        raw_args = {"_raw": raw_args}
                out.append({
                    "type": "tool_use",
                    "id": blk.get("id", ""),
                    "name": blk.get("name", ""),
                    "input": raw_args if isinstance(raw_args, dict) else {"value": raw_args},
                })
            elif btype == "text":
                # Final text is also delivered via message_end; we
                # already streamed the deltas, so we skip here to avoid
                # duplicating the text in the UI.
                pass
        # If there was a toolCall, the assistant didn't return end_turn.
        # The agent loop sees a tool_use and continues; we DON'T emit
        # done here — the agent loop's logic handles stop_reason.
        return out
    if et == "error":
        return [{"type": "error", "message": str(obj.get("error", "pi error"))}]
    return []


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
