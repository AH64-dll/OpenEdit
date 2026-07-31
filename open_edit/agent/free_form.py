"""Free-form script execution entry point (agent layer).

Task 2.3: moved from `open_edit.ir.apply._apply_free_form_code` so the IR
layer (pure domain) no longer depends on the agent layer.
"""

from __future__ import annotations

from open_edit.agent.sandbox_bridge import run_free_form
from open_edit.ir.apply import ApplyError
from open_edit.ir.types import FreeFormCodeOp, Project


def run_free_form_code(op: FreeFormCodeOp, project: Project) -> Project:
    """Run a free-form Python script in the sandbox and append its child ops.

    Each child op has parent_id == op.edit_id (stamped by IR at build time).

    Not invoked from `apply_operation` because that function is timeline-derive
    code (pure: Timeline → Timeline). Free-form intake mutates a Project's
    edit_graph; call this directly when processing a user-submitted script.
    The dispatch in `apply_operation` is a no-op so `derive_timeline` can
    safely replay a `FreeFormCodeOp` from the graph without re-running it.
    """
    result = run_free_form(
        code=op.code,
        workdir=project.workdir,
        project_id=project.project_id,
        parent_op_id=op.edit_id,
        timeout=op.timeout_sec,
        mem_mb=op.mem_mb,
        originating_note_id=op.originating_note_id,
    )
    if not result.success:
        raise ApplyError(f"free-form run failed: {result.reason}: {result.detail}")
    project.edit_graph.extend(result.ops)
    return project
