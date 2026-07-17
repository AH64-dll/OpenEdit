"""WSClient — drive the chat UI's /ws WebSocket and collect events.

The chat UI's WebSocket protocol (see phase4_chat_ui/app.py) is:
  - Client sends {"type": "prompt", "text": "..."}.
  - Server sends a stream of {"type": "message" | "tool" | ...}
    events until {"type": "done"} arrives.

This client wraps that flow in a simple synchronous API.

Note on event-loop strategy: a naive ``asyncio.run`` per call breaks
because the ``websockets`` library binds each connection to the loop
that created it. A second ``asyncio.run`` (in ``send_prompt``) raises
``RuntimeError: ... attached to a different loop``. We therefore keep
one event loop on the instance and drive it with ``run_until_complete``
so connect/send/close all happen in the same loop. The public API is
still fully synchronous.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import websockets


class WSClient:
    """WebSocket client that collects one prompt's event stream."""

    def __init__(self, url: str, timeout: float = 180.0) -> None:
        self._url = url
        self._timeout = timeout
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ws: Any = None

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
        return self._loop

    def connect(self) -> None:
        """Open the WebSocket. Raises on failure."""
        loop = self._ensure_loop()

        async def _connect():
            return await websockets.connect(self._url)

        try:
            self._ws = loop.run_until_complete(_connect())
        except Exception:
            self._ws = None
            raise

    def close(self) -> None:
        """Close the WebSocket. Safe to call multiple times."""
        if self._ws is None:
            return
        ws = self._ws
        self._ws = None
        loop = self._ensure_loop()
        try:
            loop.run_until_complete(ws.close())
        except Exception:
            pass

    def send_prompt(self, text: str) -> list[dict]:
        """Send one prompt and collect events until 'done'. Returns the events."""
        if self._ws is None:
            raise RuntimeError("WSClient not connected; call connect() first")
        loop = self._ensure_loop()

        async def _send_and_collect():
            await self._ws.send(json.dumps({"type": "prompt", "text": text}))
            events: list[dict] = []
            while True:
                raw = await asyncio.wait_for(
                    self._ws.recv(), timeout=self._timeout
                )
                ev = json.loads(raw)
                events.append(ev)
                if ev.get("type") == "done":
                    break
            return events

        try:
            return loop.run_until_complete(_send_and_collect())
        except asyncio.TimeoutError as e:
            raise RuntimeError(
                f"WebSocket timed out after {self._timeout}s waiting for events"
            ) from e

    def run_prompt_sync(self, text: str) -> list[dict]:
        """Connect, send, collect, close. Returns the events."""
        self.connect()
        try:
            return self.send_prompt(text)
        finally:
            self.close()
