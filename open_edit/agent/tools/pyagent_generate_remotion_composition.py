"""Agent tool: append AddRemotionCompositionOp (and optionally scaffold)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from open_edit.ir.types import AddRemotionCompositionOp, new_id
from open_edit.storage.edit_graph import EditGraphStore


def generate_remotion_composition(args: dict[str, Any], project_path: str | Path) -> dict[str, Any]:
    composition_id = str(args.get("composition_id") or "").strip()
    entry_point = str(args.get("entry_point") or "src/index.ts").strip()
    try:
        position_sec = float(args.get("position_sec", 0.0))
        duration_sec = float(args.get("duration_sec", 3.0))
    except (TypeError, ValueError):
        return {
            "ok": False,
            "error": "position_sec and duration_sec must be numbers",
            "retry": False,
        }
    if not composition_id:
        return {
            "ok": False,
            "error": "composition_id is required",
            "expected_keys": ["composition_id", "entry_point", "position_sec", "duration_sec"],
            "retry": False,
        }
    if duration_sec <= 0:
        return {"ok": False, "error": "duration_sec must be > 0", "retry": False}

    props = args.get("props") if isinstance(args.get("props"), dict) else {}
    track_id = str(args.get("track_id") or "video_graphics")
    alpha = bool(args.get("alpha", False))
    project = Path(project_path)

    from open_edit.render.remotion_scaffold import ensure_remotion_scaffold

    ensure_remotion_scaffold(project)

    db = project / ".open_edit" / "edit_graph.db"
    if not db.exists():
        return {"ok": False, "error": "edit_graph.db not found", "retry": False}

    op = AddRemotionCompositionOp(
        edit_id=new_id(),
        author="ai",
        entry_point=entry_point,
        composition_id=composition_id,
        props=props,
        position_sec=position_sec,
        duration_sec=duration_sec,
        track_id=track_id,
        alpha=alpha,
    )
    store = EditGraphStore(db)
    try:
        store.append(op)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "retry": False}

    return {
        "ok": True,
        "edit_id": op.edit_id,
        "composition_uid": op.composition_uid,
        "clip_id": op.clip_id,
        "kind": op.kind,
        "graph_revision": store.graph_revision(),
        "note": "Composition materializes to a CAS clip on the next proxy/final render",
    }
