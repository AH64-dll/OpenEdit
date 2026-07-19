"""WebSocket connection manager + Kdenlive D-Bus reload helper.

`ChatConnectionManager` is the broadcast hub: every connected WebSocket is
appended on `connect`, removed on `disconnect`, and the `broadcast` helper
sends a JSON message to all of them (silently dropping any that fail to
send). `try_reload_kdenlive` is the only D-Bus call the chat UI makes; it
lives here so the round-trip is in one module with the only callers
(start_watching in handler.py + the `reload_kdenlive` message handler).
"""
from __future__ import annotations

from fastapi import WebSocket


def try_reload_kdenlive() -> bool:
    """Trigger a clean-restart in a running Kdenlive instance, if any."""
    try:
        from phase5_dbus_sync.dbus_client import (
            KdenliveDBus, detect_service_name, is_running,
        )
        if is_running():
            svc = detect_service_name()
            if svc:
                return KdenliveDBus(svc).clean_restart(clean=False)
    except Exception:
        pass
    return False


class ChatConnectionManager:
    """Tracks active WebSockets and broadcasts project-state updates."""

    def __init__(self) -> None:
        self.sessions: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.sessions.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.sessions:
            self.sessions.remove(ws)

    async def broadcast(self, msg: dict) -> None:
        for ws in list(self.sessions):
            try:
                await ws.send_json(msg)
            except Exception:
                self.disconnect(ws)
