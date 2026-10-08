"""Local export settings, fixed-revision jobs and verified output actions."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from starlette.concurrency import run_in_threadpool

from open_edit.kernel.export_service import ExportSettings, capture_export, export_defaults
from open_edit.kernel.render_jobs import DEFAULT_RENDER_JOB_SERVICE, RenderEnqueueError, public_job
from open_edit.storage.edit_graph import GraphRevisionConflict

from ..auth import _check_rate_limit
from .projects import _require_project

router = APIRouter()


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: StrictInt = Field(ge=0)
    settings: ExportSettings


@router.get("/api/projects/{project_id}/export/settings")
async def get_settings(project_id: str):
    state = await _require_project(project_id)
    return await run_in_threadpool(export_defaults, Path(state.path))


@router.post("/api/projects/{project_id}/export", status_code=202)
async def post_export(project_id: str, request: ExportRequest):
    _check_rate_limit(f"export:{project_id}", max_requests=10, window_sec=300)
    state = await _require_project(project_id)
    root = Path(state.path)
    payload = None
    try:
        payload = await run_in_threadpool(
            capture_export, root, request.expected_revision, request.settings
        )
        job = DEFAULT_RENDER_JOB_SERVICE.enqueue(
            project_id,
            root,
            mode="final",
            expected_revision=request.expected_revision,
            params={"export": payload},
        )
    except (GraphRevisionConflict, RenderEnqueueError) as error:
        if payload:
            shutil.rmtree(root / ".open_edit/exports" / payload["snapshot"], ignore_errors=True)
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (ValueError, OSError) as error:
        if payload:
            shutil.rmtree(root / ".open_edit/exports" / payload["snapshot"], ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(error)) from error
    return public_job(job)


async def _output(project_id: str, job_id: str) -> Path:
    state = await _require_project(project_id)
    job = DEFAULT_RENDER_JOB_SERVICE.get(Path(state.path), job_id)
    if (
        job is None
        or job.status != "succeeded"
        or not (job.result or {}).get("export_verification", {}).get("passed")
        or not job.output_path
    ):
        raise HTTPException(status_code=404, detail="Verified export is unavailable")
    path = Path(job.output_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Export was moved or deleted")
    return path


@router.get("/api/projects/{project_id}/exports/{job_id}/file")
async def get_export_file(project_id: str, job_id: str):
    path = await _output(project_id, job_id)
    return FileResponse(
        path,
        media_type={
            "mp4": "video/mp4",
            "mov": "video/quicktime",
            "mkv": "video/x-matroska",
            "webm": "video/webm",
        }.get(path.suffix[1:], "application/octet-stream"),
    )


@router.post("/api/projects/{project_id}/exports/{job_id}/open/{action}")
async def open_export(project_id: str, job_id: str, action: Literal["play", "folder"]):
    path = await _output(project_id, job_id)
    target = path.parent if action == "folder" else path
    try:
        if os.name == "nt":
            os.startfile(str(target))
        else:
            command = ["open" if sys.platform == "darwin" else "xdg-open", str(target)]
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    except OSError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"status": "ok", "path": str(target)}
