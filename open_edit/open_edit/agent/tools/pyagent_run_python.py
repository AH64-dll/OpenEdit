"""pyagent_run_python: invokes the Phase 3 free-form Python sandbox.

Per phase4-design-revised.md §3.3 (T8): the agent can run arbitrary
Python inside the bwrap+seccomp sandbox. The sandbox appends ops to
edit_graph.db atomically; this wrapper just translates the call.
"""
from __future__ import annotations

from pathlib import Path

from open_edit.agent.exceptions import FreeFormResult
from open_edit.agent.sandbox_bridge import run_free_form
from open_edit.agent.tools._helpers import _db_path


def run_python(args: dict, project_path: str) -> dict:
    """Run free-form Python; return {status, ops, error}."""
    workdir = Path(_db_path(project_path)).parent
    result: FreeFormResult = run_free_form(
        code=args["code"],
        workdir=workdir,
        project_id=args["project_id"],
        parent_op_id=args.get("parent_op_id"),
        timeout=int(args.get("timeout_sec", 30)),
        mem_mb=int(args.get("mem_mb", 512)),
        originating_note_id=args.get("originating_note_id"),
    )
    return {
        "status": "ok" if result.success else "error",
        "ops": [op.model_dump() for op in result.ops],
        "error": (result.reason + ": " + result.detail) if not result.success else None,
    }
