"""PiAgentAdapter — wraps the Phase 3 PiClient for the chat UI."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import AsyncIterator

from phase4_chat_ui.pi_client import PiClient
from phase4_chat_ui.types import PiEvent


# Repo root (grandparent of this file: <repo>/phase4_chat_ui/adapters/piagent.py).
_REPO_ROOT = Path(__file__).resolve().parents[2]


MODELS_STORE_PATH = Path(os.path.expanduser("~/.pi/agent/models-store.json"))
_PI_AGENT_PROVIDER = "opencode-go"


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
        # Always load the pyagent extension so the `pyagent_*` timeline-editing
        # tools are exposed to the model. Without it the AI has no way to mutate
        # the .kdenlive project (timeline appears immutable in Kdenlive).
        resolved_args = list(pi_args) if pi_args is not None else []
        ext = _REPO_ROOT / "phase3_pyagent_core" / "extension.ts"
        if ext.exists() and "-e" not in resolved_args and "--extension" not in resolved_args:
            resolved_args += ["-e", str(ext)]
        self._client = PiClient(
            provider=provider,
            model=model,
            project=project,
            binary=binary,
            session_id=session_id,
            pi_args=resolved_args,
        )

    async def run_prompt(self, text: str, image_paths: list[str] | None = None) -> AsyncIterator[PiEvent]:
        async for event in self._client.run_prompt(text, image_paths):
            yield event

    @property
    def project(self) -> str:
        return self._client.project

    @project.setter
    def project(self, value: str) -> None:
        self._client.project = value

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
