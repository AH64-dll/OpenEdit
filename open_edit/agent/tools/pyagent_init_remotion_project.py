"""Agent tool: scaffold a Remotion project under ``.open_edit/remotion/``."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from open_edit.agent.tools._contract import tool_result


@tool_result
def init_remotion_project(args: dict[str, Any], project_path: str | Path) -> dict[str, Any]:
    project = Path(project_path)
    if not project.exists():
        return {"status": "error", "error": "project_path does not exist"}
    from open_edit.render.remotion_scaffold import ensure_remotion_scaffold

    root = ensure_remotion_scaffold(project)
    return {
        "status": "ok",
        "remotion_root": str(root),
        "entry_point": "src/index.ts",
        "demo_composition_id": "TitleCard",
        "note": "Remotion is optional; see docs/REMOTION_LICENSE.md",
    }
