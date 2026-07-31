"""The agent loop: ``run_agent_turn``.

Runs the LLM streaming loop for SDK providers and diverts CLI
providers (pi) to ``_run_cli_owned_turn``. Patchable seams
(``stream_chat``, ``_execute_tool``, ``effective_provider``,
``_resolve_project_path``) are looked up through the package
namespace so tests that patch ``open_edit.serve.agent`` observe
their replacements.
"""
from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any, Literal, TypedDict

from open_edit.serve import agent as _agent_pkg

from open_edit.kernel.tool_executor import (
    execute_tool as _execute_agent_tool,
    execute_trigger_render as _execute_trigger_render,
)
from open_edit.kernel.tool_schemas import TOOL_SCHEMAS

from .. import cli_adapter as cli_adapter_mod
from .. import projects as projects_mod
from .. import visual_verify
from ..llm import _coerce_event
from ..providers import resolve_provider
from ..result_capper import cap_tool_result
from ..serve_env import get_visual_verify_config

from .cost_sidecar import (
    _SOURCE_PRIORITY,
    _create_bg_task,
    _load_cost_state,
    _save_cost_state_async,
)
from .history_store import (
    _build_tool_result_message,
    _make_slim_history,
)
from .prompts import _build_system_prompt
from .verify_stage import _build_verification_result, _maybe_verify_render


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------
class AgentEvent(TypedDict, total=False):
    """One event yielded by ``run_agent_turn``.

    Variants:
    - ``{"type": "text", "text": "..."}``  — assistant text delta
    - ``{"type": "tool_start", "name": "...", "input": {...}}``
    - ``{"type": "tool_result", "name": "...", "result": {...}}``
    - ``{"type": "render", "path": "...", "mode": "proxy"|"final"}``
    - ``{"type": "error", "message": "..."}``
    - ``{"type": "done", "stop_reason": "..."}``  — terminal event
    - ``{"type": "cost_update", "turn_tokens", "turn_cost_usd",
         "session_cost_usd", "source"}``  — v1.4 P1-3, emitted
      AFTER the terminal ``done`` once per turn.
    """
    type: Literal[
        "text", "tool_start", "tool_result", "render",
        "error", "done", "cost_update",
        "verification_started", "verification_result",
    ]
# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

async def _execute_tool(
    name: str, args: dict[str, Any], project_path: Path,
    command_id: str | None = None,
) -> dict[str, Any]:
    """Dispatch a tool call. ``trigger_render`` is server-side; the rest
    live in ``open_edit.agent.tools``.
    """
    if name == "trigger_render":
        res = _execute_trigger_render(args, project_path, command_id=command_id)
        if inspect.isawaitable(res):
            return await res
        return res
    res = _execute_agent_tool(name, args, project_path, command_id=command_id)
    if inspect.isawaitable(res):
        return await res
    return res
# ---------------------------------------------------------------------------
# The agent loop
# ---------------------------------------------------------------------------

async def run_agent_turn(
    project_id: str,
    user_message: str,
    conversation_history: list[dict[str, Any]],
    conv_id: str | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> AsyncIterator[AgentEvent]:
    """Run one full agent turn (user message -> final assistant text).

    Yields :class:`AgentEvent` dicts as the turn progresses. The caller
    is expected to iterate this generator and forward events to the
    client (e.g. over a WebSocket).

    The ``conversation_history`` list is mutated in place — the user
    message and the assistant's response (including tool calls and tool
    results) are appended. If ``conv_id`` is provided, each new message
    is also appended to ``.open_edit/conversations/<conv_id>.jsonl``.

    ``should_cancel`` is an optional callback used by the verification
    stage to abort in-flight ffmpeg work when the WebSocket disconnects.

    The loop continues until the LLM returns ``end_turn`` or hits a
    safety cap (``MAX_AGENT_ITERATIONS``).
    """
    # Resolve project + state
    try:
        state = await projects_mod.get_project_state(project_id)
    except KeyError as exc:
        yield {"type": "error", "message": str(exc)}
        yield {"type": "done", "stop_reason": "error"}
        return

    project_path = _agent_pkg._resolve_project_path(project_id)
    if project_path is None:
        yield {"type": "error", "message": f"project not found: {project_id}"}
        yield {"type": "done", "stop_reason": "error"}
        return

    provider_name = _agent_pkg.effective_provider(str(project_path))
    try:
        adapter = cli_adapter_mod.get_adapter(provider_name)
        supports_tools = adapter.supports_tools()
    except KeyError:
        supports_tools = True

    system_prompt = _build_system_prompt(state, supports_tools=supports_tools)

    # Append the user message to history
    user_msg: dict[str, Any] = {"role": "user", "content": user_message}
    conversation_history.append(user_msg)
    if conv_id:
        _agent_pkg.append_to_conversation(project_id, conv_id, user_msg)

    # v1.4 P1-3: cost tracking. The previous session cumulative
    # cost is loaded from the sidecar JSON once at turn start.
    # The agent loop aggregates per-call ``usage`` events into a
    # turn total and emits a single ``cost_update`` after the
    # final ``done``. Persistence happens off-loop via
    # ``asyncio.to_thread`` so the WS stays responsive.
    cost_state = _load_cost_state(project_path) if conv_id else {}
    previous_session_cost = 0.0
    if conv_id and conv_id in cost_state:
        try:
            previous_session_cost = float(
                cost_state[conv_id].get("session_cost_usd", 0.0)
            )
        except (TypeError, ValueError):
            previous_session_cost = 0.0
    turn_tokens = 0
    turn_cost_usd = 0.0
    # The source for the cost_update: highest-priority non-"unavailable"
    # source seen in this turn. Defaults to "unavailable" so a turn
    # that yields zero ``usage`` events (rare) still produces a
    # well-formed cost_update.
    best_source_priority = _SOURCE_PRIORITY["unavailable"]
    best_source = "unavailable"

    cfg = get_visual_verify_config()
    verify_active = cfg["enabled"] and not _agent_pkg.is_verify_disabled(project_path)
    turn_render_count = 0
    pending_verification: dict[str, Any] | None = None

    def _is_cancelled() -> bool:
        if should_cancel and should_cancel():
            return True
        try:
            task = asyncio.current_task()
            if task and hasattr(task, "cancelling") and task.cancelling() > 0:
                return True
        except Exception:
            pass
        return False

    # v1.9: CLI providers (pi, opencode, ...) run a COMPLETE agent loop
    # per subprocess call — they execute tools themselves and stream both
    # tool_use and tool_result events. The loop below must NOT re-execute
    # those tools or re-iterate (that double-executed every mutation and
    # ended every pi turn with a spurious "no user message found" error).
    # Divert to the single-stream implementation and return.
    try:
        provider_spec = resolve_provider(provider_name)
    except KeyError:
        provider_spec = None
    if provider_spec is not None and provider_spec.agent_mode == "external_loop":
        cost_ctx = {
            "cost_state": cost_state,
            "previous_session_cost": previous_session_cost,
            "turn_tokens": turn_tokens,
            "turn_cost_usd": turn_cost_usd,
            "best_source_priority": best_source_priority,
            "best_source": best_source,
        }
        async for event in _agent_pkg._run_cli_owned_turn(
            project_id=project_id,
            project_path=project_path,
            conv_id=conv_id,
            conversation_history=conversation_history,
            system_prompt=system_prompt,
            should_cancel=should_cancel,
            _is_cancelled=_is_cancelled,
            cost_ctx=cost_ctx,
        ):
            yield event
        return

    # Chat-only providers may answer questions, but cannot truthfully claim
    # to edit a project. Never expose mutation schemas to them and reject a
    # non-conforming provider's tool event before it can reach the executor.
    chat_only_provider = provider_spec is not None and provider_spec.agent_mode == "chat_only"
    chat_only_system_prompt = system_prompt
    if chat_only_provider:
        chat_only_system_prompt += (
            "\n\nThis provider is chat-only. You cannot inspect, modify, render, "
            "or claim to have changed the OpenEdit project. Explain that limitation "
            "clearly when the user requests an edit."
        )

    # Circuit breaker (v1.9): track consecutive failures per (tool, args)
    # pair. If the LLM retries the IDENTICAL failing call, we warn it in
    # the error result; after the third identical failure we terminate the
    # turn instead of burning the remaining iterations in a retry loop.
    failure_counts: dict[str, int] = {}

    # Main loop
    for _ in range(_agent_pkg.MAX_AGENT_ITERATIONS):
        if _is_cancelled():
            yield {"type": "done", "stop_reason": "cancelled"}
            return

        # Stream the LLM
        current_text_parts: list[str] = []
        tool_use_blocks: list[dict[str, Any]] = []
        stop_reason = "end_turn"

        try:
            async for raw_event in _agent_pkg.stream_chat(
                messages=_make_slim_history(conversation_history, pending_verification),
                tools=[] if chat_only_provider else TOOL_SCHEMAS,
                system=chat_only_system_prompt,
                session_id=conv_id,
                project_path=str(project_path),
            ):
                if _is_cancelled():
                    yield {"type": "done", "stop_reason": "cancelled"}
                    return
                # Wave 3.3: normalize through the StreamEvent contract so
                # every consumer below can rely on ``event["type"]`` being
                # present and the variant payload fields having safe
                # defaults. ``_coerce_event`` raises on events missing
                # ``type``; everything else is filled in.
                event = _coerce_event(raw_event)
                etype = event["type"]
                if etype == "text_delta":
                    text = event.get("text", "")
                    if text:
                        current_text_parts.append(text)
                        yield {"type": "text", "text": text}
                elif etype == "tool_use":
                    if chat_only_provider:
                        yield {
                            "type": "error",
                            "message": "This provider is chat-only and cannot apply project edits.",
                        }
                        continue
                    tool_use_blocks.append({
                        "type": "tool_use",
                        "id": event["id"],
                        "name": event["name"],
                        "input": event.get("input", {}),
                    })
                elif etype == "tool_result":
                    # SDK providers (anthropic/openai) never emit this —
                    # the agent loop executes tools itself. CLI providers
                    # are diverted to ``_run_cli_owned_turn`` before the
                    # loop, so receiving one here means a provider is
                    # misbehaving; ignore it rather than corrupt the
                    # execution state.
                    pass
                elif etype == "usage":
                    # v1.4 P1-3: aggregate per-call cost data into
                    # the turn total. The source priority ranking
                    # ensures the cost_update reports the most
                    # informative source when a turn mixes
                    # providers.
                    try:
                        turn_tokens += int(event.get("tokens", 0) or 0)
                        turn_cost_usd += float(event.get("cost_usd", 0.0) or 0.0)
                    except (TypeError, ValueError):
                        pass
                    src = event.get("source", "unavailable")
                    if not isinstance(src, str):
                        src = "unavailable"
                    prio = _SOURCE_PRIORITY.get(src, _SOURCE_PRIORITY["unavailable"])
                    if prio < best_source_priority:
                        best_source_priority = prio
                        best_source = src
                elif etype == "error":
                    yield event
                elif etype == "done":
                    stop_reason = event.get("stop_reason", "end_turn")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # LLM/streaming failure — surface and abort. Emit a
            # cost_update with whatever we've accumulated so the
            # UI doesn't get stuck on a missing event.
            yield {"type": "error", "message": f"LLM stream error: {exc}"}
            yield {"type": "done", "stop_reason": "error"}
            session_cost_usd = previous_session_cost + turn_cost_usd
            yield {
                "type": "cost_update",
                "turn_tokens": turn_tokens,
                "turn_cost_usd": round(turn_cost_usd, 9),
                "session_cost_usd": round(session_cost_usd, 9),
                "source": best_source,
            }
            if conv_id:
                cost_state[conv_id] = {
                    "session_cost_usd": session_cost_usd,
                    "source": best_source,
                    "last_turn_cost_usd": turn_cost_usd,
                }
                _create_bg_task(
                    _save_cost_state_async(project_path, dict(cost_state))
                )
            return

        if pending_verification is not None:
            verdict = visual_verify.parse_verdict("".join(current_text_parts))
            if tool_use_blocks:
                outcome = "iterate"
            elif verdict["verdict"] == "pass":
                outcome = "pass"
            else:
                outcome = "uncertain"
            yield _build_verification_result(
                render_id=pending_verification["render_id"],
                render_path=pending_verification["output_path"],
                outcome=outcome,
                verdict_source=verdict["source"],
                render_count=pending_verification["render_count"],
                max_renders=pending_verification["max_renders"],
            )
            pending_verification = None

        # Build the assistant message
        assistant_content: list[dict[str, Any]] = []
        if current_text_parts:
            assistant_content.append({
                "type": "text",
                "text": "".join(current_text_parts),
            })
        assistant_content.extend(tool_use_blocks)

        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": assistant_content,
        }
        conversation_history.append(assistant_msg)
        if conv_id:
            _agent_pkg.append_to_conversation(project_id, conv_id, assistant_msg)

        # No tool calls -> turn is done. Emit the cost_update
        # AFTER ``done`` (per the brief) and persist the new
        # session cumulative to the sidecar JSON (off-loop).
        if not tool_use_blocks:
            yield {"type": "done", "stop_reason": stop_reason}
            session_cost_usd = previous_session_cost + turn_cost_usd
            yield {
                "type": "cost_update",
                "turn_tokens": turn_tokens,
                "turn_cost_usd": round(turn_cost_usd, 9),
                "session_cost_usd": round(session_cost_usd, 9),
                "source": best_source,
            }
            if conv_id:
                cost_state[conv_id] = {
                    "session_cost_usd": session_cost_usd,
                    "source": best_source,
                    "last_turn_cost_usd": turn_cost_usd,
                }
                # Fire-and-forget write; the cost_update has
                # already been yielded so the user sees the
                # number immediately. If the write fails the
                # next turn will reconcile from the in-memory
                # state we just stashed here.
                _create_bg_task(
                    _save_cost_state_async(project_path, dict(cost_state))
                )
            return

        # Execute tool calls. v1.5: reorder so mutations run before
        # ``trigger_render``, and only the last ``trigger_render`` in a
        # batch is executed (pi may emit several in one turn; the
        # first ones are short-circuited).
        tool_result_messages: list[dict[str, Any]] = []
        mutations = [tu for tu in tool_use_blocks if tu["name"] != "trigger_render"]
        trigger_renders = [tu for tu in tool_use_blocks if tu["name"] == "trigger_render"]

        for tu in mutations:
            if _is_cancelled():
                yield {"type": "done", "stop_reason": "cancelled"}
                return
            tool_name = tu["name"]
            tool_input = dict(tu.get("input", {}))
            if "project_id" not in tool_input and tool_name != "search_assets":
                tool_input["project_id"] = project_id

            # Circuit breaker: has this EXACT call (name + args) failed
            # repeatedly? Terminate instead of burning iterations in a
            # retry loop.
            fail_key = f"{tool_name}:{json.dumps(tool_input, sort_keys=True, default=str)}"
            if failure_counts.get(fail_key, 0) >= 3:
                yield {
                    "type": "error",
                    "message": (
                        f"tool '{tool_name}' failed 3 times with identical "
                        f"arguments; aborting the turn instead of looping."
                    ),
                }
                yield {"type": "done", "stop_reason": "tool_loop_detected"}
                tool_result_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tu["id"],
                            "content": json.dumps({
                                "error": (
                                    f"tool '{tool_name}' aborted: same call "
                                    f"failed 3 times. STOP retrying it."
                                )
                            }),
                        }
                    ],
                })
                for trm in tool_result_messages:
                    conversation_history.append(trm)
                    if conv_id:
                        _agent_pkg.append_to_conversation(project_id, conv_id, trm)
                return

            yield {"type": "tool_start", "id": tu["id"], "name": tool_name, "input": tool_input}
            try:
                res = _agent_pkg._execute_tool(tool_name, tool_input, project_path, command_id=tu["id"])
                if inspect.isawaitable(res):
                    result = await res
                else:
                    result = res
                result = cap_tool_result(result)
                # A tool-level error payload (status: error) counts as a
                # failure for the circuit breaker even though the call
                # didn't raise.
                if isinstance(result, dict) and (
                    result.get("status") == "error" or result.get("error")
                ):
                    failure_counts[fail_key] = failure_counts.get(fail_key, 0) + 1
                yield {"type": "tool_result", "id": tu["id"], "name": tool_name, "result": result}
                tool_result_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tu["id"],
                            "content": json.dumps(result, default=str),
                        }
                    ],
                })
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                failure_counts[fail_key] = failure_counts.get(fail_key, 0) + 1
                err_msg = f"tool '{tool_name}' failed: {exc}"
                if failure_counts[fail_key] >= 2:
                    err_msg += (
                        " [circuit-breaker: this exact call has failed "
                        f"{failure_counts[fail_key]} times — DO NOT retry it "
                        "with the same arguments; change your approach or "
                        "explain the blocker to the user]"
                    )
                # Complete the tool card with the error (a bare ``error``
                # event left the card's spinner running forever) and echo
                # it to the chat log for visibility.
                yield {
                    "type": "tool_result",
                    "id": tu["id"],
                    "name": tool_name,
                    "result": {"error": err_msg},
                    "is_error": True,
                }
                yield {"type": "error", "message": err_msg}
                tool_result_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tu["id"],
                            "content": json.dumps({"error": err_msg}),
                        }
                    ],
                })

        if trigger_renders:
            if _is_cancelled():
                yield {"type": "done", "stop_reason": "cancelled"}
                return
            # Only the LAST trigger_render in a batch executes; every
            # earlier one gets a synthesized "skipped" tool_result so the
            # conversation history never contains an orphaned tool_use
            # block (Anthropic rejects those with a 400 on the next call).
            for skipped_tu in trigger_renders[:-1]:
                tool_result_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": skipped_tu["id"],
                            "content": json.dumps({
                                "status": "skipped",
                                "reason": "superseded by a later trigger_render in the same turn",
                            }),
                        }
                    ],
                })
            tu = trigger_renders[-1]
            tool_name = tu["name"]
            tool_input = dict(tu.get("input", {}))
            if "project_id" not in tool_input and tool_name != "search_assets":
                tool_input["project_id"] = project_id
            yield {"type": "tool_start", "id": tu["id"], "name": tool_name, "input": tool_input}
            try:
                res = _agent_pkg._execute_tool(tool_name, tool_input, project_path, command_id=tu["id"])
                if inspect.isawaitable(res):
                    result = await res
                else:
                    result = res
                result = cap_tool_result(result)
                yield {"type": "tool_result", "id": tu["id"], "name": tool_name, "result": result}
                if isinstance(result, dict):
                    output_path = result.get("output_path", "")
                    mode = result.get("mode", "proxy")
                    if output_path:
                        yield {"type": "render", "path": output_path, "mode": mode}

                if verify_active:
                    turn_render_count += 1
                    if turn_render_count > cfg["max_renders"]:
                        capped = visual_verify.build_failure_tool_result(
                            "render_capped",
                            render_id=result.get("render_id", "render_unknown"),
                            cap=cfg["max_renders"],
                            render_count=turn_render_count,
                        )
                        yield _build_verification_result(
                            render_id=result.get("render_id", "render_unknown"),
                            render_path=output_path,
                            outcome="capped",
                            verdict_source="cap_reached",
                            render_count=turn_render_count,
                            max_renders=cfg["max_renders"],
                        )
                        tool_result_messages.append(
                            _build_tool_result_message(tu["id"], capped)
                        )
                    else:
                        try:
                            v_events, augmented_result, vstate = await _maybe_verify_render(
                                result, project_path, turn_render_count, cfg, should_cancel,
                            )
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:
                            v_events = [_build_verification_result(
                                render_id=result.get("render_id", "render_unknown"),
                                render_path=output_path,
                                outcome="failed",
                                verdict_source="frame_extraction_failed",
                                render_count=turn_render_count,
                                max_renders=cfg["max_renders"],
                            )]
                            augmented_result = visual_verify.build_failure_tool_result(
                                "frame_extraction_failed",
                                render_id=result.get("render_id", "render_unknown"),
                                detail=str(exc),
                            )
                            vstate = None
                        for ev in v_events:
                            yield ev
                        if vstate is not None:
                            pending_verification = vstate
                        tool_result_messages.append(
                            _build_tool_result_message(tu["id"], augmented_result)
                        )
                else:
                    tool_result_messages.append(
                        _build_tool_result_message(tu["id"], result)
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                fail_key = f"{tool_name}:{json.dumps(tool_input, sort_keys=True, default=str)}"
                failure_counts[fail_key] = failure_counts.get(fail_key, 0) + 1
                err_msg = f"tool '{tool_name}' failed: {exc}"
                if failure_counts[fail_key] >= 2:
                    err_msg += (
                        " [circuit-breaker: this exact call has failed "
                        f"{failure_counts[fail_key]} times — DO NOT retry it "
                        "with the same arguments; change your approach or "
                        "explain the blocker to the user]"
                    )
                yield {
                    "type": "tool_result",
                    "id": tu["id"],
                    "name": tool_name,
                    "result": {"error": err_msg},
                    "is_error": True,
                }
                yield {"type": "error", "message": err_msg}
                tool_result_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tu["id"],
                            "content": json.dumps({"error": err_msg}),
                        }
                    ],
                })

        # Append all tool_result messages in order
        for trm in tool_result_messages:
            conversation_history.append(trm)
            if conv_id:
                _agent_pkg.append_to_conversation(project_id, conv_id, trm)

        # Re-read state after tool mutations so the next LLM call sees
        # up-to-date project state (without duplicating JSON in tool results).
        state = await projects_mod.get_project_state(project_id)
        system_prompt = _build_system_prompt(state, supports_tools=supports_tools, state_summary_only=True)

    # Hit the iteration cap — surface a soft error and stop.
    # Also emit the cost_update so the user sees how much this
    # runaway turn cost; persist the cumulative as usual.
    yield {
        "type": "error",
        "message": f"agent hit the {_agent_pkg.MAX_AGENT_ITERATIONS}-iteration cap without finishing.",
    }
    yield {"type": "done", "stop_reason": "max_iterations"}
    session_cost_usd = previous_session_cost + turn_cost_usd
    yield {
        "type": "cost_update",
        "turn_tokens": turn_tokens,
        "turn_cost_usd": round(turn_cost_usd, 9),
        "session_cost_usd": round(session_cost_usd, 9),
        "source": best_source,
    }
    if conv_id:
        cost_state[conv_id] = {
            "session_cost_usd": session_cost_usd,
            "source": best_source,
            "last_turn_cost_usd": turn_cost_usd,
        }
        _create_bg_task(
            _save_cost_state_async(project_path, dict(cost_state))
        )
