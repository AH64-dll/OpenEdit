"""CLI-owned turns (pi / opencode / antigravity / jcode).

CLI providers run a COMPLETE agent loop inside a single subprocess call:
the model calls tools, the CLI executes them (pi via the TS extension ->
pi_bridge), and the event stream carries both ``tool_use`` and
``tool_result`` events. The Open Edit agent loop must NOT:
  - re-execute those tools locally (every mutation would run TWICE —
    duplicate notes, duplicate clips, corrupted edit graphs), or
  - re-loop (the next subprocess call would have no new user text —
    previously this ended every tool-using pi turn with a spurious
    "no user message found" error).
Instead we stream exactly once, forward events for the UI, and record a
well-formed transcript (every tool_use paired with a tool_result) so the
conversation history stays valid if the user later switches to an SDK
provider.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from open_edit.serve import agent as _agent_pkg

from open_edit.kernel.tool_schemas import TOOL_SCHEMAS

from ..llm import _coerce_event

from .cost_sidecar import _SOURCE_PRIORITY, _create_bg_task, _save_cost_state_async
from .history_store import _make_slim_history
from .loop import AgentEvent


# ---------------------------------------------------------------------------
# CLI-owned turns (pi / opencode / antigravity / jcode)
# ---------------------------------------------------------------------------
# CLI providers run a COMPLETE agent loop inside a single subprocess call:
# the model calls tools, the CLI executes them (pi via the TS extension ->
# pi_bridge), and the event stream carries both ``tool_use`` and
# ``tool_result`` events. The Open Edit agent loop must NOT:
#   - re-execute those tools locally (every mutation would run TWICE —
#     duplicate notes, duplicate clips, corrupted edit graphs), or
#   - re-loop (the next subprocess call would have no new user text —
#     previously this ended every tool-using pi turn with a spurious
#     "no user message found" error).
# Instead we stream exactly once, forward events for the UI, and record a
# well-formed transcript (every tool_use paired with a tool_result) so the
# conversation history stays valid if the user later switches to an SDK
# provider.

async def _run_cli_owned_turn(
    *,
    project_id: str,
    project_path: Path,
    conv_id: str | None,
    conversation_history: list[dict[str, Any]],
    system_prompt: str,
    should_cancel: Callable[[], bool] | None,
    _is_cancelled: Callable[[], bool],
    cost_ctx: dict[str, Any],
) -> AsyncIterator[AgentEvent]:
    """Run one turn against a provider that owns its agent loop."""
    current_text_parts: list[str] = []
    tool_use_blocks: list[dict[str, Any]] = []
    forwarded_results: dict[str, dict[str, Any]] = {}  # tool_use_id -> result
    unmatched_result_queue: list[dict[str, Any]] = []  # results without ids (FIFO)
    _assistant_saved = False
    stop_reason = "end_turn"

    try:
        async for raw_event in _agent_pkg.stream_chat(
            messages=_make_slim_history(conversation_history, None),
            tools=TOOL_SCHEMAS,
            system=system_prompt,
            session_id=conv_id,
            project_path=str(project_path),
        ):
            if _is_cancelled():
                yield {"type": "done", "stop_reason": "cancelled"}
                return
            event = _coerce_event(raw_event)
            etype = event["type"]
            if etype == "text_delta":
                text = event.get("text", "")
                if text:
                    current_text_parts.append(text)
                    yield {"type": "text", "text": text}
            elif etype == "tool_use":
                block = {
                    "type": "tool_use",
                    "id": event["id"],
                    "name": event["name"],
                    "input": event.get("input", {}),
                }
                tool_use_blocks.append(block)
                yield {
                    "type": "tool_start",
                    "id": block["id"],
                    "name": block["name"],
                    "input": block["input"],
                }
            elif etype == "tool_result":
                result = event.get("result", {})
                tu_id = event.get("tool_use_id", "")
                if tu_id:
                    forwarded_results[tu_id] = result
                else:
                    unmatched_result_queue.append(result)
                yield {
                    "type": "tool_result",
                    "id": tu_id,
                    "name": event.get("name", ""),
                    "result": result,
                    "is_error": bool(event.get("is_error")),
                }
                # A render result carries output_path — surface it so the
                # UI refreshes the renders list.
                if isinstance(result, dict) and result.get("output_path"):
                    yield {
                        "type": "render",
                        "path": result["output_path"],
                        "mode": result.get("mode", "proxy"),
                    }
                # Save partial progress after each tool_result so
                # mid-turn crashes don't lose accumulated state.
                if conv_id and tu_id:
                    if not _assistant_saved:
                        _assistant_saved = True
                        ac: list[dict[str, Any]] = []
                        if current_text_parts:
                            ac.append({
                                "type": "text",
                                "text": "".join(current_text_parts),
                            })
                        ac.extend(tool_use_blocks)
                        _agent_pkg.append_to_conversation(
                            project_id, conv_id,
                            {"role": "assistant", "content": ac},
                        )
                    _agent_pkg.append_to_conversation(
                        project_id, conv_id,
                        {
                            "role": "user",
                            "content": [{
                                "type": "tool_result",
                                "tool_use_id": tu_id,
                                "content": json.dumps(result, default=str),
                            }],
                        },
                    )
            elif etype == "usage":
                try:
                    cost_ctx["turn_tokens"] += int(event.get("tokens", 0) or 0)
                    cost_ctx["turn_cost_usd"] += float(event.get("cost_usd", 0.0) or 0.0)
                except (TypeError, ValueError):
                    pass
                src = event.get("source", "unavailable")
                if not isinstance(src, str):
                    src = "unavailable"
                prio = _SOURCE_PRIORITY.get(src, _SOURCE_PRIORITY["unavailable"])
                if prio < cost_ctx["best_source_priority"]:
                    cost_ctx["best_source_priority"] = prio
                    cost_ctx["best_source"] = src
            elif etype == "error":
                yield {"type": "error", "message": event.get("message", "provider error")}
            elif etype == "done":
                stop_reason = event.get("stop_reason", "end_turn")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        yield {"type": "error", "message": f"LLM stream error: {exc}"}
        stop_reason = "error"

    # Record a well-formed transcript: assistant text + tool_uses, then one
    # user message pairing every tool_use with its result (synthesizing a
    # placeholder for any the provider didn't report, so the history stays
    # valid for SDK providers if the user switches later).
    assistant_content: list[dict[str, Any]] = []
    if current_text_parts:
        assistant_content.append({
            "type": "text",
            "text": "".join(current_text_parts),
        })
    assistant_content.extend(tool_use_blocks)
    if assistant_content:
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": assistant_content}
        conversation_history.append(assistant_msg)
        if conv_id and not _assistant_saved:
            _agent_pkg.append_to_conversation(project_id, conv_id, assistant_msg)

    if tool_use_blocks:
        result_blocks: list[dict[str, Any]] = []
        for block in tool_use_blocks:
            result = forwarded_results.get(block["id"])
            if result is None and unmatched_result_queue:
                result = unmatched_result_queue.pop(0)
            if result is None:
                result = {"status": "no_result_forwarded"}
            result_blocks.append({
                "type": "tool_result",
                "tool_use_id": block["id"],
                "content": json.dumps(result, default=str),
            })
        results_msg: dict[str, Any] = {"role": "user", "content": result_blocks}
        conversation_history.append(results_msg)
        if conv_id and not _assistant_saved:
            _agent_pkg.append_to_conversation(project_id, conv_id, results_msg)

    yield {"type": "done", "stop_reason": stop_reason}
    session_cost_usd = cost_ctx["previous_session_cost"] + cost_ctx["turn_cost_usd"]
    yield {
        "type": "cost_update",
        "turn_tokens": cost_ctx["turn_tokens"],
        "turn_cost_usd": round(cost_ctx["turn_cost_usd"], 9),
        "session_cost_usd": round(session_cost_usd, 9),
        "source": cost_ctx["best_source"],
    }
    if conv_id:
        cost_ctx["cost_state"][conv_id] = {
            "session_cost_usd": session_cost_usd,
            "source": cost_ctx["best_source"],
            "last_turn_cost_usd": cost_ctx["turn_cost_usd"],
        }
        _create_bg_task(
            _save_cost_state_async(project_path, dict(cost_ctx["cost_state"]))
        )
