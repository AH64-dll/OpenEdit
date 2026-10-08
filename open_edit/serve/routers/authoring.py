"""Revision-aware source and visual property writes through the MCP adapter."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
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


class GraphicsCommitRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: StrictInt = Field(ge=0)
    job_id: str = Field(min_length=1, max_length=128)
    clip_id: str = Field(default='graphics', min_length=1, max_length=128)
    track_id: str = Field(default='graphics', min_length=1, max_length=128)
    position_sec: float = Field(default=0, ge=0, allow_inf_nan=False)


@router.get('/api/projects/{project_id}/graphics')
async def read_graphics(project_id: str, clip_id: str = 'graphics') -> dict:
    from open_edit.integrations.diffusion.graphics import get_graphics_view

    state = await _require_project(project_id)
    try:
        return await run_in_threadpool(get_graphics_view, state.path, clip_id=clip_id, include_source=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/api/projects/{project_id}/graphics/commit')
async def write_graphics(project_id: str, req: GraphicsCommitRequest) -> JSONResponse:
    from open_edit.integrations.diffusion.graphics import commit_graphics

    state = await _require_project(project_id)
    try:
        result = await run_in_threadpool(commit_graphics, state.path, **req.model_dump(), author='user')
    except GraphRevisionConflict as exc:
        return JSONResponse(status_code=409, content={'error_code': 'stale_revision', 'error': str(exc), 'graph_revision': exc.actual})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


@router.get('/api/projects/{project_id}/graphics/{job_id}/poster')
async def graphics_poster(project_id: str, job_id: str) -> FileResponse:
    from pathlib import Path

    from open_edit.kernel.render_jobs import DEFAULT_RENDER_JOB_SERVICE

    state = await _require_project(project_id)
    root = Path(state.path).resolve()
    job = DEFAULT_RENDER_JOB_SERVICE.get(root, job_id)
    if job is None or job.mode != 'graphics' or job.status != 'succeeded':
        raise HTTPException(status_code=404, detail='Completed graphics preview not found')
    poster = Path((job.result or {}).get('poster_path', '')).resolve()
    if not poster.is_relative_to(root / '.open_edit/graphics') or not poster.is_file():
        raise HTTPException(status_code=404, detail='Graphics poster not found')
    return FileResponse(poster, media_type='image/png')
