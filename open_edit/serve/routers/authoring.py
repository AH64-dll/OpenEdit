"""Revision-aware source and visual property writes through the MCP adapter."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from starlette.concurrency import run_in_threadpool

from open_edit.integrations.diffusion.authoring import apply_authoring_edit, get_authoring_view
from open_edit.storage.edit_graph import GraphRevisionConflict

from .projects import _require_project

router = APIRouter()


class AuthoringEditRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: StrictInt = Field(ge=0)
    source: str | None = Field(default=None, max_length=512 * 1024)
    edits: list[dict] | None = Field(default=None, max_length=1000)


@router.get('/api/projects/{project_id}/authoring')
async def read_authoring(project_id: str, include_source: bool = False) -> dict:
    state = await _require_project(project_id)
    try:
        return await run_in_threadpool(get_authoring_view, state.path, include_source=include_source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/api/projects/{project_id}/authoring')
async def write_authoring(project_id: str, req: AuthoringEditRequest) -> JSONResponse:
    state = await _require_project(project_id)
    try:
        result = await run_in_threadpool(
            apply_authoring_edit, state.path,
            expected_revision=req.expected_revision, source=req.source, edits=req.edits,
            author='user',
        )
    except GraphRevisionConflict as exc:
        return JSONResponse(status_code=409, content={
            'status': 'error', 'error_code': 'stale_revision', 'error': str(exc),
            'expected_revision': exc.expected, 'graph_revision': exc.actual,
        })
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)
