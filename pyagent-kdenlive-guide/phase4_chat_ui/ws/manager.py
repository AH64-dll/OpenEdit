"""WebSocket connection manager + Kdenlive D-Bus reload helper.

`ChatConnectionManager` is the broadcast hub: every connected WebSocket is
appended on `connect`, removed on `disconnect`. The `broadcast` helper
sends a JSON message to all of them (silently dropping any that fail to
send). For project-scoped notes broadcasts (Phase 4 T6) the manager
maintains a `project_path -> set[ws]` map; `broadcast_to_project` uses
that map so only websocket connections bound to the same project hear
about note changes (per audit H4).
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
    """Tracks active WebSockets and broadcasts project-state updates.

    Sessions list is global; the per-project map (added in Phase 4 T6)
    is maintained alongside it so we can broadcast note-list updates
    to only the sockets bound to the same project.
    """

    def __init__(self) -> None:
        self.sessions: list[WebSocket] = []
        self._by_project: dict[str, set[WebSocket]] = {}

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.sessions.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.sessions:
            self.sessions.remove(ws)
        for bucket in self._by_project.values():
            bucket.discard(ws)

    def track(self, project: str, ws: WebSocket) -> None:
        if not project:
            return
        self._by_project.setdefault(project, set()).add(ws)

    def untrack(self, project: str, ws: WebSocket) -> None:
        bucket = self._by_project.get(project)
        if bucket is not None:
            bucket.discard(ws)
            if not bucket:
                self._by_project.pop(project, None)

    async def broadcast(self, msg: dict) -> None:
        for ws in list(self.sessions):
            try:
                await ws.send_json(msg)
            except Exception:
                self.disconnect(ws)

    async def broadcast_to_project(self, project: str, msg: dict) -> None:
        """Per audit H4: send a message to all sockets bound to `project`."""
        bucket = self._by_project.get(project, set())
        for ws in list(bucket):
            try:
                await ws.send_json(msg)
            except Exception:
                self.disconnect(ws)
