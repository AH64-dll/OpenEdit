"""Agent tool: write a Remotion composition TSX file with safety checks."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def write_remotion_composition(args: dict[str, Any], project_path: str | Path) -> dict[str, Any]:
    relative_path = str(args.get("relative_path") or "").strip()
    source = args.get("source")
    if not relative_path:
        return {
            "ok": False,
            "error": "relative_path is required (e.g. src/compositions/MyTitle.tsx)",
            "expected_keys": ["relative_path", "source"],
            "retry": False,
        }
    if not isinstance(source, str) or not source.strip():
        return {
            "ok": False,
            "error": "source is required (TypeScript/TSX string)",
            "expected_keys": ["relative_path", "source"],
            "retry": False,
        }
    project = Path(project_path)
    from open_edit.render.remotion_scaffold import write_composition_file

    try:
        path = write_composition_file(project, relative_path, source)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "retry": False}
    return {
        "ok": True,
        "path": str(path),
        "relative_path": relative_path,
        "bytes": len(source.encode("utf-8")),
    }
