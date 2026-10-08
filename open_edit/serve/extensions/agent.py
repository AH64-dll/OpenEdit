"""Lazy compatibility entry for the optional built-in agent extension."""
from fastapi import APIRouter, WebSocket

from open_edit.serve.review_mode import is_review_only

router = APIRouter()

@router.websocket('/api/chat/{project_id}')
async def chat(websocket: WebSocket, project_id: str) -> None:
    if is_review_only():
        await websocket.close(code=4404, reason='Optional agent extension is disabled')
        return
    from open_edit.serve.ws.chat import ws_chat
    await ws_chat(websocket, project_id)
