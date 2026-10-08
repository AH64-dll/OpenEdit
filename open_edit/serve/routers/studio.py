"""Source-backed editor documents and non-rendered AI annotations."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from starlette.concurrency import run_in_threadpool

from open_edit.kernel.studio_service import (
    commit_studio,
    get_editing_context,
    get_studio,
    save_editing_selection,
)
from open_edit.storage.edit_graph import GraphRevisionConflict

from .projects import _require_project

router = APIRouter()


class StudioEditRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: StrictInt = Field(ge=0)
    changes: list[dict] = Field(default_factory=list, max_length=1000)
    ops: list[dict] = Field(default_factory=list, max_length=1000)
    request_id: str | None = Field(default=None, min_length=1, max_length=128)
    label: str | None = Field(default=None, min_length=1, max_length=256)


class EditingContextRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    selected_ids: list[str] = Field(default_factory=list, max_length=500)
    annotation_ids: list[str] = Field(default_factory=list, max_length=500)
    playhead_sec: float = Field(default=0, ge=0, allow_inf_nan=False)
    document_id: str | None = Field(default=None, min_length=1, max_length=128)


class StudioCompileRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: StrictInt = Field(ge=0)
    source: str = Field(min_length=1, max_length=512 * 1024)
    edits: list[dict] = Field(default_factory=list, max_length=1000)


class StudioSelectionRequest(EditingContextRequest):
    expected_revision: StrictInt = Field(ge=0)


@router.post('/api/projects/{project_id}/studio/selection')
async def write_selection(project_id: str, request: StudioSelectionRequest):
    project = await _require_project(project_id)
    try:
        return await run_in_threadpool(save_editing_selection, project.path, **request.model_dump())
    except GraphRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/api/studio/runtime.js')
async def runtime_bundle():
    from open_edit.integrations.diffusion.graphics import editor_bundle

    try:
        data = await run_in_threadpool(editor_bundle)
        return Response(data, media_type='text/javascript', headers={'Cache-Control': 'no-cache'})
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get('/api/studio/font.woff2')
async def bundled_font():
    from open_edit.integrations.diffusion.graphics import browser_directory

    return FileResponse(browser_directory() / 'fonts/OpenEditSans.woff2', media_type='font/woff2')


@router.post('/api/projects/{project_id}/studio/compile')
async def compile_source(project_id: str, request: StudioCompileRequest):
    from open_edit.integrations.diffusion.graphics import compile_editor

    project = await _require_project(project_id)
    try:
        result = await run_in_threadpool(compile_editor, project.path, **request.model_dump())
        for asset in result['asset_manifest']:
            from urllib.parse import quote

            asset['url'] = f'/api/projects/{quote(project_id, safe="")}/studio/assets/{asset["id"]}'
        return result
    except GraphRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/api/projects/{project_id}/studio/assets/{asset_hash}')
async def studio_image(project_id: str, asset_hash: str):
    import re

    from open_edit.integrations.diffusion.graphics import graphics_asset_manifest

    project = await _require_project(project_id)
    if not re.fullmatch(r'[a-f0-9]{64}', asset_hash):
        raise HTTPException(status_code=404, detail='Image not found')
    try:
        manifest = await run_in_threadpool(graphics_asset_manifest, project.path, [asset_hash])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(manifest[0]['file'], media_type=manifest[0]['mimeType'],
                        headers={'Cache-Control': 'private, max-age=31536000, immutable'})


@router.get('/api/projects/{project_id}/studio')
async def read_studio(project_id: str, kind: str | None = None,
                      object_id: str | None = None, include_source: bool = False):
    project = await _require_project(project_id)
    try:
        return await run_in_threadpool(get_studio, project.path, kind=kind,
                                      object_id=object_id, include_source=include_source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/api/projects/{project_id}/studio')
async def write_studio(project_id: str, request: StudioEditRequest):
    project = await _require_project(project_id)
    try:
        return await run_in_threadpool(commit_studio, project.path, **request.model_dump(), author='user')
    except GraphRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/api/projects/{project_id}/editing-context')
async def editing_context(project_id: str, request: EditingContextRequest):
    project = await _require_project(project_id)
    try:
        return await run_in_threadpool(get_editing_context, project.path, **request.model_dump())
    except GraphRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
