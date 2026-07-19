"""Agent adapters: protocol + per-app backends + registry.

Public surface:
- `AgentAdapter` Protocol
- `build_adapter(app_id, model, project, session_id)` factory
- `list_apps()` menu enumeration (id, name, available, models)
- `PiAgentAdapter`, `OpenCodeAdapter` concrete classes
"""
from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable

from phase4_chat_ui.types import PiEvent

from ._registry import _APP_REGISTRY, get_adapter_class
from .opencode import OpenCodeAdapter
from .piagent import PiAgentAdapter


_APP_NAMES: dict[str, str] = {
    "piagent": "PiAgent",
    "opencode": "OpenCode",
}


@runtime_checkable
class AgentAdapter(Protocol):
    """Protocol every backend agent adapter must satisfy."""

    app_id: str
    session_id: str

    async def run_prompt(self, text: str, image_paths: list[str] | None = None) -> AsyncIterator[PiEvent]: ...

    def list_models(self) -> list[dict]: ...

    def stop(self) -> None: ...

    def available(self) -> bool: ...


def build_adapter(app_id: str, model: str, project: str, session_id: str) -> AgentAdapter:
    """Construct the adapter for `app_id`. Raises ValueError if unknown."""
    return get_adapter_class(app_id)(model=model, project=project, session_id=session_id)


def list_apps() -> list[dict]:
    """Return menu entries with availability + models for each app.

    Each entry: {"id": app_id, "name": <Human>, "available": bool, "models": [...]}.
    """
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
            "name": _APP_NAMES.get(app_id, app_id),
            "available": avail,
            "models": models,
        })
    return apps


__all__ = [
    "AgentAdapter",
    "MODELS_STORE_PATH",
    "OpenCodeAdapter",
    "PiAgentAdapter",
    "build_adapter",
    "list_apps",
]


# Re-exported so tests can patch `adapters.MODELS_STORE_PATH` via the package
# surface, the same way they previously patched `agent_adapters.MODELS_STORE_PATH`.
from .piagent import MODELS_STORE_PATH  # noqa: E402  (must be after __all__)
