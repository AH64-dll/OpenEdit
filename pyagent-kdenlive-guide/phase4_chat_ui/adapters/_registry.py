"""Adapter registry — single source of truth for app_id -> adapter class."""
from __future__ import annotations

from .piagent import PiAgentAdapter
from .opencode import OpenCodeAdapter


_APP_REGISTRY: dict[str, type] = {
    "piagent": PiAgentAdapter,
    "opencode": OpenCodeAdapter,
}


def get_adapter_class(app_id: str) -> type:
    if app_id not in _APP_REGISTRY:
        raise ValueError(f"unknown agent app: {app_id!r}")
    return _APP_REGISTRY[app_id]
