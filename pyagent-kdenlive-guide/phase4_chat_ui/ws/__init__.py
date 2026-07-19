"""WebSocket handler package for the pyagent chat UI.

Owns the per-connection state (session map, adapter map, active prompt
task), the dispatch logic for incoming messages, and the broadcast path
for project-state updates triggered by the file watcher. Also owns the
D-Bus reload call so the round-trip stays in one module.

Public API (re-exported for backward-compat with `app.py` and tests):
- `ChatConnectionManager` — broadcast hub (in `manager.py`).
- `try_reload_kdenlive()` — D-Bus reload helper (in `manager.py`).
- `WsHandler` — per-app state + WebSocket dispatch (in `handler.py`).

Per-message-type handlers live in `handlers.py` as free functions; the
dispatcher in `WsHandler.handle` matches on the wire-level `type` and
delegates to them.
"""
from __future__ import annotations

from phase4_chat_ui.ws.handler import WsHandler
from phase4_chat_ui.ws.manager import ChatConnectionManager, try_reload_kdenlive

__all__ = ["ChatConnectionManager", "WsHandler", "try_reload_kdenlive"]
