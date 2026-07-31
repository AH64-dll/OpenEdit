"""pyagent_run_python: invokes the Phase 3 free-form Python sandbox.

Per phase4-design-revised.md §3.3 (T8): the agent can run arbitrary
Python inside the bwrap+seccomp sandbox. On success, validated ops are
appended to edit_graph.db (same contract as the CLI path).
"""
from __future__ import annotations

import uuid
from pathlib import Path

from open_edit.agent.exceptions import FreeFormResult
from open_edit.agent.sandbox import run_free_form
from open_edit.agent.tools._contract import tool_result
from open_edit.agent.tools._helpers import _db_path
from open_edit.storage.edit_graph import EditGraphStore


@tool_result
def run_python(args: dict, project_path: str) -> dict:
    """Run free-form Python; persist ops; return a slim summary by default."""
    db_path = _db_path(project_path)
    workdir = Path(db_path).parent
    parent_op_id = args.get("parent_op_id") or f"pyagent_{uuid.uuid4().hex[:12]}"
    # Pillar-tool fix: the bridge no longer auto-injects project_id
    # for run_script (its schema has additionalProperties: false).
    # Derive it from the project_path's edit_graph.db when missing.
    project_id = args.get("project_id")
    store = EditGraphStore(db_path)
    if not project_id:
        project_id = store.project_id
    result: FreeFormResult = run_free_form(
        code=args["code"],
        workdir=workdir,
        project_id=project_id,
        parent_op_id=parent_op_id,
        timeout=int(args.get("timeout_sec", 30)),
        mem_mb=int(args.get("mem_mb", 512)),
        originating_note_id=args.get("originating_note_id"),
    )
    appended = 0
    op_summaries: list[dict] = []
    if result.success and result.ops:
        # Match CLI: persist validated ops to the edit graph.
        for op in result.ops:
            store.append(op)
            appended += 1
            dump = op.model_dump() if hasattr(op, "model_dump") else {}
            op_summaries.append({
                "kind": dump.get("kind") or getattr(op, "kind", type(op).__name__),
                "edit_id": dump.get("edit_id") or getattr(op, "edit_id", None),
                "clip_id": dump.get("clip_id"),
            })
    include_full = bool(args.get("include_full_ops", False))
    out = {
        "status": "ok" if result.success else "error",
        "ops_appended": appended,
        "ops_summary": op_summaries,
        "graph_revision": store.graph_revision(),
        "error": (result.reason + ": " + result.detail) if not result.success else None,
    }
    # Full dumps are huge — only when explicitly requested.
    if include_full:
        out["ops"] = [op.model_dump() for op in (result.ops or [])]
    return out


# run_script is an alias for run_python (Plan D consolidation).
run_script = run_python
