"""Local stdio MCP server — Open Edit as an agent plugin.

Exposes the pillar tools so an external agent host (Cursor, Claude Code,
Pi, …) owns the LLM loop while Open Edit remains the editing/render backend.

Harness skills (playbooks) live in repo ``skills/`` and are also exposed as
MCP instructions / resources / prompts — see ``open_edit.mcp.skills``.
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
