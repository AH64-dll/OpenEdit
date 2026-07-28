"""Exception types and result types for the free-form Python sandbox."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from open_edit.ir.types import OperationUnion


@dataclass
class FreeFormResult:
    """Result of a free-form Python run. Always returned, never raised.

    success=True: ops list is non-empty (or empty if the script emitted no ops).
    success=False: reason is a stable string; detail is human-readable.
    """
    success: bool
    ops: list["OperationUnion"] = field(default_factory=list)
    reason: str = ""
    detail: str = ""
    duration_s: float = 0.0

    @classmethod
    def ok(cls, ops: list, duration_s: float) -> "FreeFormResult":
        return cls(success=True, ops=ops, duration_s=duration_s)

    @classmethod
    def fail(cls, reason: str, detail: str = "") -> "FreeFormResult":
        return cls(success=False, reason=reason, detail=detail)


@dataclass
class RenderResult:
    """Result of a render-sandbox run (Phase 4.5 W2).

    Distinct from open_edit.render.orchestrator.RenderResult (which is the
    outcome of a melt subprocess run). This is the outcome of running
    user-provided heavy-compute Python in the render sandbox.
    """
    path: Path
    ok: bool = True
    detail: str = ""


class SandboxError(Exception):
    """Raised for unrecoverable preflight/setup errors. NOT for runtime failures
    (those are reported via FreeFormResult.fail).
    """


class _ValidationError(Exception):
    """Internal: a single op in ops.jsonl failed referential or schema validation.
    Caught by sandbox_bridge and mapped to FreeFormResult.fail('invalid_op').
    """
