"""OpenCode CLI event normalization for project editing.

Maps native editing activity, usage, text and errors to StreamEvent.
"""
from __future__ import annotations

import json
import sys
from collections.abc import AsyncIterator
from typing import Any


def normalize_native_tool(
    name: str, call_id: str, arguments: Any, status: str,
    output: Any = None, error: Any = None,
) -> list[dict[str, Any]]:
    """CLI tools execute through MCP; report activity without executing twice."""
    from open_edit.kernel.tool_schemas import TOOL_BY_NAME
    name = name.removeprefix('mcp__openedit__').removeprefix('openedit_')
    if name not in TOOL_BY_NAME:
        return []
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            arguments = {}
    start = {'type':'tool_use', 'id':call_id, 'name':name, 'input':arguments or {}}
    if status in ('pending', 'running'):
        return [start]
    if status not in ('completed', 'error'):
        return []
    if isinstance(output, dict) and isinstance(output.get('structuredContent'), dict):
        output = output['structuredContent']
    if isinstance(output, dict) and isinstance(output.get('content'), list):
        output = next((b.get('text') for b in output['content'] if b.get('type') == 'text'), '')
    if isinstance(output, str):
        try:
            output = json.loads(output)
        except ValueError:
            output = {'summary':output[:1200]}
    result = output if isinstance(output, dict) else {'status':status}
    if error:
        result = {'status':'error', 'error':error.get('message', str(error)) if isinstance(error, dict) else str(error)}
    # Completed parts may arrive without a start. The agent loop deduplicates
    # starts by call ID so both streaming formats produce a complete log.
    return [start, {'type':'tool_result', 'id':call_id, 'name':name, 'result':result}]

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


def normalize_opencode_line(line: str) -> list[dict[str, Any]]:
    """Map one raw stdout line to 0..n ``StreamEvent``-shaped dicts.

    Blank / non-JSON lines are skipped.  Returns:
      - ``[{"type": "text_delta", "text": "..."}]`` for a ``text`` event
      - ``[{"type": "usage", ...}, {"type": "done", ...}]`` for each
        ``step_finish`` event
      - ``[{"type": "error", "message": "..."}]`` for an ``error`` event
    """
    line = line.strip()
    if not line:
        return []
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return []
    if not isinstance(obj, dict):
        return []
    et = obj.get("type")
    if et == 'tool_use':
        part = obj.get('part') or {}
        state = part.get('state') or {}
        return normalize_native_tool(part.get('tool', ''), part.get('id', ''),
                                     state.get('input') or {}, state.get('status', ''),
                                     state.get('output'), state.get('error'))
    if et == "text":
        part = obj.get("part") or {}
        text = part.get("text") if isinstance(part, dict) else None
        if isinstance(text, str) and text:
            return [{"type": "text_delta", "text": text}]
    elif et == "step_finish":
        part = obj.get("part") or {}
        if isinstance(part, dict):
            usage = _usage_from_part(part)
            out: list[dict[str, Any]] = []
            if usage is not None:
                out.append(usage)
            out.append({
                "type": "done",
                "stop_reason": _map_stop_reason(part.get("reason")),
            })
            return out
    elif et == "error":
        err = obj.get("error") or {}
        msg = "<unknown>"
        if isinstance(err, dict):
            data = err.get("data") or {}
            if isinstance(data, dict) and data.get("message"):
                msg = str(data["message"])
            else:
                msg = str(err.get("name") or msg)
        return [{"type": "error", "message": msg}]
    elif et == "step_start":
        return []
    elif et == "toolCall":
        # Older, unstructured events cannot establish a completed MCP call.
        print(
            "opencode_adapter: ignoring unstructured toolCall event",
            file=sys.stderr,
        )
    # All other event types are silently dropped — the spike
    # showed only step_start/text/step_finish/error as real
    # events, and adding a noisy "unknown event" log here would
    # just spam operators when opencode adds new event types.
    return []


async def parse_opencode_events(
    stdout: AsyncIterator[bytes],
) -> AsyncIterator[dict[str, Any]]:
    """Read raw stdout lines from ``opencode run --format json`` and yield
    ``StreamEvent``-shaped dicts.

    Line framing lives here; per-line mapping delegates to
    :func:`normalize_opencode_line`.
    """
    async for raw in stdout:
        try:
            line = raw.decode("utf-8", errors="replace")
        except Exception:
            continue
        for ev in normalize_opencode_line(line):
            yield ev

