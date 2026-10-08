"""Local MCP server for Open Edit.

External MCP clients own the LLM loop; Open Edit supplies editing and rendering
against the project pinned at server startup.
"""
from __future__ import annotations

__all__ = ["load_skill", "resolve_project_path"]


def __getattr__(name: str):
    if name == "resolve_project_path":
        from open_edit.mcp.context import resolve_project_path

        return resolve_project_path
    if name == "load_skill":
        from open_edit.mcp.skills import load_skill

        return load_skill
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
