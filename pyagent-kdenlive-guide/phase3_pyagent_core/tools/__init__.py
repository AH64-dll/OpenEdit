"""Per-domain tool definitions consumed by extension.ts (Task 2.3).

Each tools/*.py module exports a `TOOLS` list of `ToolDef`s. The
`all_tools()` function flattens them in the same order as the brief.
"""
from __future__ import annotations

from . import bin, catalog, clips, clips_edit, effects, markers, project, render_qc, transitions


def all_tools() -> list:
    """Return every tool def in the system, in canonical order."""
    return [
        *project.TOOLS,
        *catalog.TOOLS,
        *bin.TOOLS,
        *clips.TOOLS,
        *clips_edit.TOOLS,
        *transitions.TOOLS,
        *effects.TOOLS,
        *markers.TOOLS,
        *render_qc.TOOLS,
    ]


__all__ = ["all_tools", "ToolDef"]
