"""WebSocket chat route (streaming AgentEvents per conversation)."""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .. import agent as agent_mod
from ..auth import _check_rate_limit, _websocket_auth_error
from ..review_mode import is_review_only
from ..routers.projects import _require_project

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    conv_id: str | None = None


@router.websocket("/api/chat/{project_id}")
async def ws_chat(websocket: WebSocket, project_id: str) -> None:
    """Stream AgentEvents for a chat conversation."""
    if is_review_only():
        await websocket.close(code=4404, reason="review-only mode")
        return
    # HTTP middleware does not protect WebSocket upgrades. Authenticate and
    # validate the Origin before accepting so unauthorized clients cannot
    # receive project state or submit a chat turn.
    auth_error = _websocket_auth_error(websocket)
    if auth_error is not None:
        code, _reason = auth_error
        await websocket.close(code=code, reason=_reason)
        return

    # Verify project exists before accepting.
    try:
        await _require_project(project_id)
    except HTTPException as exc:
        await websocket.accept()
        # The detail already starts with "project not found: " (set by
        # projects.get_project_state's KeyError) and includes the recovery
        # hint — just forward it.
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": detail,
        }))
        await websocket.close(code=4404, reason="project not found")
        return

    await websocket.accept()
    await websocket.send_text(json.dumps({"type": "ready", "project_id": project_id}))

    # Per-connection conversation cache. In-memory only — persisted via
    # append_to_conversation() if a conv_id is provided by the client.
    conversations: dict[str, list[dict[str, Any]]] = {}
    current_turn_task: asyncio.Task | None = None

    async def _cancel_turn():
        nonlocal current_turn_task
        if current_turn_task and not current_turn_task.done():
            current_turn_task.cancel()
            try:
                await current_turn_task
            except (asyncio.CancelledError, Exception):
                pass
        current_turn_task = None

    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping"}))
                continue
            max_message_bytes = int(os.environ.get("OPEN_EDIT_WS_MAX_MESSAGE_BYTES", "65536"))
            if len(raw.encode("utf-8")) > max_message_bytes:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"message exceeds {max_message_bytes}-byte limit",
                }))
                await websocket.close(code=4409, reason="message too large")
                return
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "invalid JSON; expected {\"message\": \"...\"}",
                }))
                continue

            if not isinstance(payload, dict):
                continue

            msg_type = payload.get("type")
            if msg_type in ("cancel", "stop"):
                await _cancel_turn()
                await websocket.send_text(json.dumps({"type": "cancelled"}))
                continue

            message = payload.get("message")
            if not isinstance(message, str) or not message.strip():
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "missing 'message' field",
                }))
                continue

            client_host = websocket.client.host if websocket.client else "local"
            try:
                _check_rate_limit(
                    f"ws:{client_host}:{project_id}",
                    max_requests=int(os.environ.get("OPEN_EDIT_WS_MAX_MESSAGES", "20")),
                    window_sec=float(os.environ.get("OPEN_EDIT_WS_WINDOW_SECONDS", "60")),
                )
            except HTTPException:
                await websocket.send_text(json.dumps({
                    "type": "error", "message": "rate limit exceeded. try again later.",
                }))
                await websocket.close(code=4429, reason="rate limited")
                return

            conv_id = payload.get("conv_id") or agent_mod.new_conversation_id()

            # Load conversation from disk (if any) and cache it.
            if conv_id not in conversations:
                conversations[conv_id] = agent_mod.load_conversation(project_id, conv_id)

            history = conversations[conv_id]

            await _cancel_turn()

            async def _run_agent_turn_task(user_msg: str, cid: str, hist: list[dict[str, Any]]):
                try:
                    async for event in agent_mod.run_agent_turn(
                        project_id=project_id,
                        user_message=user_msg,
                        conversation_history=hist,
                        conv_id=cid,
                        should_cancel=lambda: asyncio.current_task() is not None and asyncio.current_task().cancelling() > 0,
                    ):
                        await websocket.send_text(json.dumps(event, default=str))
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"agent turn crashed: {exc}",
                    }))
                    await websocket.send_text(json.dumps({
                        "type": "done",
                        "stop_reason": "error",
                    }))

            current_turn_task = asyncio.create_task(_run_agent_turn_task(message, conv_id, history))
    except WebSocketDisconnect:
        await _cancel_turn()
        return
    except Exception:
        await _cancel_turn()
        return
    finally:
        await _cancel_turn()
