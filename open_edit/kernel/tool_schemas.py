"""Shared schemas generated from the typed registry; capability help is on demand."""
from __future__ import annotations

from typing import Any

from open_edit.kernel.tool_registry import build_tool_schemas

# ---------------------------------------------------------------------------
# Pillar tool schemas (generated from the Pydantic registry)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = build_tool_schemas()


# Convenience lookup
TOOL_BY_NAME: dict[str, dict[str, Any]] = {t["name"]: t for t in TOOL_SCHEMAS}


def get_tool_schema(name: str) -> dict[str, Any] | None:
    """Return the schema for a tool by name, or None if unknown."""
    return TOOL_BY_NAME.get(name)
