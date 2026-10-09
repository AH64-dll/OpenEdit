"""Source-backed editor documents and non-rendered AI annotations."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt
from starlette.concurrency import run_in_threadpool

from open_edit.kernel.object_tracking import TrackingRequest, edit_object_track
from open_edit.kernel.studio_service import (
    EditingFocus,
    commit_studio,
    get_editing_context,
    get_studio,
    save_editing_selection,
)
from open_edit.storage.edit_graph import GraphRevisionConflict

from .projects import _require_project

router = APIRouter()


class TrackEditRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: StrictInt = Field(ge=0)
    edits: list[dict] = Field(min_length=1, max_length=100)
    label: str = Field(default='Edit tracked object', min_length=1, max_length=256)


class TrackApplyRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: StrictInt = Field(ge=0)


async def _tracking_call(project_id, function, **values):
    project = await _require_project(project_id)
    try:
        return await run_in_threadpool(function, project.path, **values)
    except GraphRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/api/projects/{project_id}/tracking')
async def track_region(project_id: str, request: TrackingRequest):
    from open_edit.kernel.tracking_jobs import start_tracking

    return await _tracking_call(project_id, start_tracking, **request.model_dump(exclude_unset=True))


@router.get('/api/projects/{project_id}/tracking')
async def tracking_jobs(project_id: str):
    from open_edit.kernel.tracking_jobs import list_tracking_jobs

    return await _tracking_call(project_id, list_tracking_jobs)


@router.get('/api/projects/{project_id}/tracking/{job_id}')
async def tracking_job(project_id: str, job_id: str):
    from open_edit.kernel.tracking_jobs import get_tracking_job

    return await _tracking_call(project_id, get_tracking_job, job_id=job_id)


@router.post('/api/projects/{project_id}/tracking/{job_id}/cancel')
async def stop_tracking(project_id: str, job_id: str):
    from open_edit.kernel.tracking_jobs import cancel_tracking

    return await _tracking_call(project_id, cancel_tracking, job_id=job_id)


@router.post('/api/projects/{project_id}/tracking/{job_id}/apply')
async def apply_track(project_id: str, job_id: str, request: TrackApplyRequest):
    from open_edit.kernel.tracking_jobs import apply_tracking_job

    return await _tracking_call(project_id, apply_tracking_job, job_id=job_id, **request.model_dump())


@router.post('/api/projects/{project_id}/object-tracks/{object_id}/edit')
async def edit_track(project_id: str, object_id: str, request: TrackEditRequest):
    return await _tracking_call(project_id, edit_object_track, object_id=object_id, author='user', **request.model_dump())


@router.get('/api/studio/effects')
async def effect_capabilities():
    """The same catalog drives validation, UI controls and XML properties."""
    from open_edit.ir.validate import _get_default_catalog

    catalog = _get_default_catalog()
    return {'effects': [catalog.get(name).model_dump(mode='json') for name in sorted(catalog.known_names())],
            'actions': ['update', 'remove', 'move', 'reset', 'duplicate'],
            'advanced': 'Uncatalogued effects retain source and can be bypassed, reordered or removed.'}


class StudioEditRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: StrictInt = Field(ge=0)
    changes: list[dict] = Field(default_factory=list, max_length=1000)
    ops: list[dict] = Field(default_factory=list, max_length=1000)
    request_id: str | None = Field(default=None, min_length=1, max_length=128)
    label: str | None = Field(default=None, min_length=1, max_length=256)


class EditingContextRequest(EditingFocus):
    include_source: StrictBool = False
    include_timeline: StrictBool = False
    offset: StrictInt = Field(default=0, ge=0)
    limit: StrictInt = Field(default=20, ge=1, le=100)
    section: str | None = Field(default=None, min_length=1, max_length=32)


class StudioCompileRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: StrictInt = Field(ge=0)
    source: str = Field(min_length=1, max_length=512 * 1024)
    edits: list[dict] = Field(default_factory=list, max_length=1000)


class StudioSelectionRequest(EditingFocus):
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
