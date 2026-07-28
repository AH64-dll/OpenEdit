"""pyagent_run_python: invokes the Phase 3 free-form Python sandbox.

Per phase4-design-revised.md §3.3 (T8): the agent can run arbitrary
Python inside the bwrap+seccomp sandbox. The sandbox appends ops to
edit_graph.db atomically; this wrapper just translates the call.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from open_edit.agent.exceptions import FreeFormResult
from open_edit.agent.sandbox_bridge import run_free_form
from open_edit.agent.tools._helpers import _db_path


def run_python(args: dict, project_path: str) -> dict:
    """Run free-form Python; return {status, ops, error}."""
    try:
        workdir = Path(_db_path(project_path)).parent
        parent_op_id = args.get("parent_op_id") or f"pyagent_{uuid.uuid4().hex[:12]}"
        # Pillar-tool fix: the bridge no longer auto-injects project_id
        # for run_script (its schema has additionalProperties: false).
        # Derive it from the project_path's edit_graph.db when missing.
        project_id = args.get("project_id")
        if not project_id:
            from open_edit.storage.edit_graph import EditGraphStore
            project_id = EditGraphStore(_db_path(project_path)).project_id
        result: FreeFormResult = run_free_form(
            code=args["code"],
            workdir=workdir,
            project_id=project_id,
            parent_op_id=parent_op_id,
            timeout=int(args.get("timeout_sec", 30)),
            mem_mb=int(args.get("mem_mb", 512)),
            originating_note_id=args.get("originating_note_id"),
        )
        return {
            "status": "ok" if result.success else "error",
            "ops": [op.model_dump() for op in result.ops],
            "error": (result.reason + ": " + result.detail) if not result.success else None,
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "ops": []}


# run_script is an alias for run_python (Plan D consolidation).
run_script = run_python
