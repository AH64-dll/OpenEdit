"""Edit-graph (ops) routes: timeline commands, op status, reorder, delete."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .projects import _require_project

router = APIRouter()


class TimelineCommandRequest(BaseModel):
    command: str
    params: dict[str, Any] = Field(default_factory=dict)
    expected_revision: int | None = None
    author: str = "user"


class UpdateOpStatusRequest(BaseModel):
    status: str  # "applied" | "reverted" | "superseded"
    expected_revision: int | None = None


class ReorderOpsRequest(BaseModel):
    op_ids: list[str]  # ordered list of edit_ids in desired sequence
    expected_revision: int | None = None


@router.post("/api/projects/{project_id}/ops")
async def post_timeline_command(
    project_id: str, req: TimelineCommandRequest,
) -> JSONResponse:
    """Apply a manual timeline command through the shared edit-graph service."""
    state = await _require_project(project_id)
    author = req.author if req.author in ("ai", "user") else "user"
    from open_edit.kernel.edit_graph_service import EditGraphCommandError, apply_command
    from open_edit.storage.edit_graph import GraphRevisionConflict

    try:
        result = apply_command(
            Path(state.path),
            req.command,
            req.params,
            author=author,  # type: ignore[arg-type]
            expected_revision=req.expected_revision,
        )
    except GraphRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EditGraphCommandError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


@router.patch("/api/projects/{project_id}/ops/{edit_id}/status")
async def update_op_status(
    project_id: str, edit_id: str, req: UpdateOpStatusRequest,
) -> JSONResponse:
    if req.status not in ("applied", "reverted", "superseded"):
        raise HTTPException(
            status_code=400,
            detail=f"invalid status {req.status!r}; expected applied, reverted, or superseded",
        )
    state = await _require_project(project_id)
    db_path = Path(state.path) / ".open_edit" / "edit_graph.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="edit graph not found")
    from open_edit.storage.edit_graph import EditGraphStore, GraphRevisionConflict

    store = EditGraphStore(db_path)
    ops = store.load_all()
    if not any(o.edit_id == edit_id for o in ops):
        raise HTTPException(status_code=404, detail=f"op {edit_id} not found")
    try:
        revision = store.update_status(edit_id, req.status, expected_revision=req.expected_revision)
    except GraphRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JSONResponse({"edit_id": edit_id, "status": req.status, "graph_revision": revision})


@router.delete("/api/projects/{project_id}/ops/{edit_id}")
async def delete_op(project_id: str, edit_id: str, expected_revision: int | None = None) -> JSONResponse:
    """Revert a public operation without destroying durable edit history.

    Hard deletion remains a storage-maintenance operation.  UI/API callers
    must use a reversible status transition so later operations keep their
    references and the graph remains auditable.
    """
    state = await _require_project(project_id)
    db_path = Path(state.path) / ".open_edit" / "edit_graph.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="edit graph not found")
    from open_edit.storage.edit_graph import EditGraphStore, GraphRevisionConflict

    store = EditGraphStore(db_path)
    ops = store.load_all()
    if not any(op.edit_id == edit_id for op in ops):
        raise HTTPException(status_code=404, detail=f"op {edit_id} not found")
    if any(op.parent_id == edit_id for op in ops):
        raise HTTPException(
            status_code=409,
            detail="operation is referenced by later edits; revert dependent edits first",
        )
    try:
        revision = store.update_status(
            edit_id, "reverted", reason="api_revert", expected_revision=expected_revision,
        )
    except GraphRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JSONResponse({"edit_id": edit_id, "status": "reverted", "deleted": False, "graph_revision": revision})


@router.post("/api/projects/{project_id}/ops/reorder")
async def reorder_ops(
    project_id: str, req: ReorderOpsRequest,
) -> JSONResponse:
    state = await _require_project(project_id)
    db_path = Path(state.path) / ".open_edit" / "edit_graph.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="edit graph not found")
    from open_edit.storage.edit_graph import EditGraphStore, GraphRevisionConflict

    store = EditGraphStore(db_path)
    try:
        revision = store.reorder_all(req.op_ids, expected_revision=req.expected_revision)
    except GraphRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"reordered": True, "graph_revision": revision})
