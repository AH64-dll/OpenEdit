"""Adapter abstraction for switching the chat UI's backend agentic app.

This module defines the `AgentAdapter` protocol that later tasks depend on,
and ships the first concrete implementation `PiAgentAdapter`, which wraps the
existing `PiClient` from `pi_client.py`.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Protocol, runtime_checkable

from phase4_chat_ui.pi_client import PiClient
from phase4_chat_ui.types import PiEvent


# Repo root (parent of this package dir) — used to locate the pyagent extension.
# __file__ = <repo>/phase4_chat_ui/agent_adapters.py  -> parents[1] = <repo>
_REPO_ROOT = Path(__file__).resolve().parents[1]


def _extract_cost(obj: dict) -> float | None:
    """Pull USD cost from a pi/opencode usage.cost.total field, if present."""
    usage = obj.get("usage") if isinstance(obj, dict) else None
    if not isinstance(usage, dict):
        return None
    cost = (usage.get("cost") or {}).get("total")
    if isinstance(cost, (int, float)) and cost > 0:
        return float(cost)
    return None

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


def _default_models(cmd: list[str]) -> str:
    """Shell `opencode models` and return its stdout as a string."""
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return result.stdout


async def _default_run_cmd(cmd: list[str]):
    """Default subprocess launcher: shells the given command list."""
    return await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


class OpenCodeAdapter:
    """Adapter that shells the `opencode` CLI (`opencode run --format json`)."""

    app_id = "opencode"

    def __init__(
        self,
        model: str,
        project: str,
        session_id: str,
        models_cmd_fn: Callable[[list[str]], str] | None = None,
        run_cmd_fn: Callable[..., Any] | None = None,
    ) -> None:
        self.model = model
        self.project = project
        self.session_id = session_id
        self._models_cmd_fn = models_cmd_fn if models_cmd_fn is not None else _default_models
        self._run_cmd_fn = run_cmd_fn if run_cmd_fn is not None else _default_run_cmd
        self._proc = None

    def available(self) -> bool:
        return shutil.which("opencode") is not None

    def list_models(self) -> list[dict]:
        raw = self._models_cmd_fn(["opencode", "models"])
        models: list[dict] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            models.append({"id": line, "name": line})
        return models

    async def run_prompt(self, text: str, image_paths: list[str] | None = None) -> AsyncIterator[PiEvent]:
        cmd = [
            "opencode", "run", "--format", "json", "--auto",
            "--model", self.model,
        ]
        if image_paths:
            for ip in image_paths:
                cmd += ["--file", ip]
        cmd += [text]

        try:
            proc = await self._run_cmd_fn(cmd)
        except FileNotFoundError:
            yield PiEvent(kind="error", text="opencode binary not found")
            return

        self._proc = proc
        try:
            assert proc.stdout is not None
            async for raw in proc.stdout:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event = self._to_event(obj)
                if event is not None:
                    yield event
            yield PiEvent(kind="done")
        except asyncio.CancelledError:
            self.stop()
            raise
        finally:
            if proc.returncode is None:
                try:
                    proc.kill()
                except Exception:
                    pass
            self._proc = None

    def stop(self) -> None:
        if self._proc is not None and self._proc.returncode is None:
            try:
                self._proc.kill()
            except Exception:
                pass

    @staticmethod
    def _to_event(obj: dict) -> PiEvent | None:
        """Map an `opencode run --format json` event to a normalized PiEvent.

        Real opencode event schema (observed):
          {"type":"step_start", ...}                       -> ignore
          {"type":"text","text":"...", ...}                 -> assistant text delta
          {"type":"tool_use","part":{                      -> tool call
              "type":"tool","tool":"bash",
              "state":{"status":"completed",
                       "input":{"command":"ls"},
                       "output":"..."}}}
          {"type":"step_finish", ...}                      -> ignore (done emitted after stream)
          {"type":"error","error":"..."}                   -> error
        """
        etype = obj.get("type")

        if etype == "error" or "error" in obj:
            err = obj.get("error") or obj.get("message") or "unknown error"
            return PiEvent(kind="error", text=str(err))

        if etype == "text":
            # The text string lives in different places depending on whether
            # opencode is attached to a TTY: top-level "text", or nested
            # under "part"."text" when run headless (subprocess, no TTY).
            text = obj.get("text")
            if not isinstance(text, str):
                text = (obj.get("part") or {}).get("text")
            if isinstance(text, str) and text:
                return PiEvent(kind="message_delta", role="assistant", text=text)
            return None

        # opencode streams a "usage" / cost object on step_finish / final
        # events. Surface any positive USD total as a cost event.
        cost = _extract_cost(obj)
        if cost is not None:
            return PiEvent(kind="cost", cost=cost)

        if etype == "tool_use":
            part = obj.get("part") or {}
            tool = part.get("tool")
            state = part.get("state") or {}
            args = state.get("input") or {}
            result = state.get("output")
            if tool:
                return PiEvent(
                    kind="tool",
                    tool=str(tool),
                    args=args if isinstance(args, dict) else {"input": args},
                    result=result,
                )
            return None

        # step_start / step_finish / unknown -> no UI event
        return None


class AntiGravityAdapter:
    app_id = "antigravity"

    def __init__(self, model, project, session_id):
        self.model = model
        self.project = project
        self.session_id = session_id
        self._proc = None

    def available(self) -> bool:
        # No CLI/API on this machine; Electron-only. Never usable as a backend.
        return False

    def list_models(self) -> list[dict]:
        return []

    async def run_prompt(self, text, image_paths=None):
        # pragma: no cover - adapter is unavailable by design
        raise RuntimeError("Anti-gravity backend is not available on this machine")

    def stop(self) -> None:
        pass


# Registry of app_id -> adapter class. Order defines default menu order.
_APP_REGISTRY: dict[str, type] = {
    "piagent": PiAgentAdapter,
    "opencode": OpenCodeAdapter,
    "antigravity": AntiGravityAdapter,
}


def build_adapter(app_id, model, project, session_id) -> AgentAdapter:
    """Construct the adapter for `app_id`. Raises ValueError if unknown."""
    if app_id not in _APP_REGISTRY:
        raise ValueError(f"unknown agent app: {app_id!r}")
    cls = _APP_REGISTRY[app_id]
    return cls(model=model, project=project, session_id=session_id)


def list_apps() -> list[dict]:
    """Return menu entries with availability + models for each app.

    Each entry: {"id": app_id, "name": <Human>, "available": bool, "models": [...]}.
    """
    def _name(app_id):
        return {
            "piagent": "PiAgent",
            "opencode": "OpenCode",
            "antigravity": "Anti-gravity (unavailable)",
        }.get(app_id, app_id)
    apps = []
    for app_id, cls in _APP_REGISTRY.items():
        # Build a throwaway instance to query availability + models without
        # launching anything: available() only uses shutil.which (no shell), and
        # list_models() is only invoked when available() is True, so no subprocess
        # is ever launched here.
        try:
            inst = cls(model="", project="", session_id="")
            avail = inst.available()
            models = inst.list_models() if avail else []
        except Exception:
            avail = False
            models = []
        apps.append({
            "id": app_id,
            "name": _name(app_id),
            "available": avail,
            "models": models,
        })
    return apps
