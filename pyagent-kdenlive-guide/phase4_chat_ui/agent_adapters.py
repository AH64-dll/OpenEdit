"""Adapter abstraction for switching the chat UI's backend agentic app.

This module defines the `AgentAdapter` protocol that later tasks depend on,
and ships the first concrete implementation `PiAgentAdapter`, which wraps the
existing `PiClient` from `pi_client.py`.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, AsyncIterator, Protocol, runtime_checkable

from pi_client import PiClient, PiEvent


MODELS_STORE_PATH = Path(os.path.expanduser("~/.pi/agent/models-store.json"))
_PI_AGENT_PROVIDER = "opencode-go"


@runtime_checkable
class AgentAdapter(Protocol):
    """Protocol every backend agent adapter must satisfy."""

    app_id: str
    session_id: str

    async def run_prompt(self, text: str, image_paths: list[str] | None = None) -> AsyncIterator[PiEvent]:
        ...

    def list_models(self) -> list[dict]:
        ...

    def stop(self) -> None:
        ...

    def available(self) -> bool:
        ...


class PiAgentAdapter:
    """Adapter that talks to the PiAgent backend via a wrapped `PiClient`."""

    app_id = "piagent"

    def __init__(
        self,
        model: str,
        project: str,
        session_id: str,
        pi_args: list[str] | None = None,
        binary: str | None = None,
        provider: str = _PI_AGENT_PROVIDER,
    ) -> None:
        self.session_id = session_id
        self._client = PiClient(
            provider=provider,
            model=model,
            project=project,
            binary=binary,
            session_id=session_id,
            pi_args=pi_args if pi_args is not None else [],
        )

    async def run_prompt(self, text: str, image_paths: list[str] | None = None) -> AsyncIterator[PiEvent]:
        async for event in self._client.run_prompt(text, image_paths):
            yield event

    def stop(self) -> None:
        self._client.stop()

    def available(self) -> bool:
        return shutil.which("pi") is not None

    def list_models(self) -> list[dict]:
        try:
            with open(MODELS_STORE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return []
        provider_entry = data.get(_PI_AGENT_PROVIDER)
        if not isinstance(provider_entry, dict):
            return []
        models = provider_entry.get("models")
        if not isinstance(models, list):
            return []
        return [
            {"id": m["id"], "name": m.get("name", m["id"])}
            for m in models
            if isinstance(m, dict) and "id" in m
        ]
