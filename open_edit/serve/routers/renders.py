"""Render routes: trigger, poll, cancel, and file streaming."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from open_edit.kernel.render_jobs import DEFAULT_RENDER_JOB_SERVICE

from .. import projects as projects_mod
from ..auth import _check_rate_limit
from .projects import _require_project

router = APIRouter()


class RenderRequest(BaseModel):
    mode: str = "proxy"  # "proxy" | "final" | "overlay"
    expected_revision: int | None = None
    encoder: str | None = None  # "gpu" (default) | "cpu"
    profile: str | None = None
    quality: str | None = None
    crf: int | None = None
    vb: str | None = None
    preset: str | None = None
    scale: str | None = None
    codec: str | None = None


class RenderJobResponse(BaseModel):
    job_id: str
    project_id: str
    mode: str
    status: str  # RenderJobService JobStatus: "queued" | "running" | "succeeded" | "failed" | ...
    output_path: str | None = None
    error: str | None = None
    # Set when the job is persisted by the durable RenderJobService.
    # Not part of the public API contract — kept on the model so the
    # field survives Pydantic serialization roundtrips in tests.
    created_at: float = Field(default_factory=time.time)
    graph_revision: int | None = None
    edit_graph_hash: str | None = None


@router.post("/api/projects/{project_id}/render", status_code=202)
async def post_render(project_id: str, req: RenderRequest) -> RenderJobResponse:
    """Trigger a render in the background. Returns the job immediately."""
    _check_rate_limit(f"render:{project_id}", max_requests=5, window_sec=300)
    state = await _require_project(project_id)
    if req.mode not in ("proxy", "final", "overlay"):
        raise HTTPException(status_code=400, detail="mode must be 'proxy', 'final', or 'overlay'")

    project_path = Path(state.path)
    from open_edit.kernel.render_jobs import RenderEnqueueError

    encoder = (req.encoder or "").strip().lower() or None
    if encoder not in (None, "gpu", "cpu"):
        raise HTTPException(status_code=400, detail="encoder must be 'gpu' or 'cpu'")
    quality = (req.quality or "").strip().lower() or None
    if quality is not None and quality not in ("fast", "standard", "high", "archival"):
        raise HTTPException(status_code=400, detail="quality must be fast|standard|high|archival")
    codec = (req.codec or "").strip().lower() or None
    if codec is not None and codec not in ("h264", "hevc", "av1"):
        raise HTTPException(status_code=400, detail="codec must be h264|hevc|av1")
    params = {k: v for k, v in (
        ("profile", req.profile), ("quality", quality), ("crf", req.crf),
        ("vb", req.vb), ("preset", req.preset), ("scale", req.scale), ("codec", codec),
    ) if v is not None}

    try:
        job = DEFAULT_RENDER_JOB_SERVICE.enqueue(
            project_id,
            project_path,
            req.mode,
            expected_revision=req.expected_revision,
            encoder_backend=encoder,
            params=params or None,
        )
    except RenderEnqueueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RenderJobResponse(
        job_id=job.job_id, project_id=job.project_id, mode=job.mode,
        status=job.status, output_path=job.output_path, error=job.error,
        created_at=job.created_at, graph_revision=job.graph_revision,
        edit_graph_hash=job.edit_graph_hash,
    )


@router.get("/api/projects/{project_id}/renders")
async def get_renders(project_id: str) -> list[dict[str, Any]]:
    await _require_project(project_id)
    return await projects_mod.list_renders(project_id)


@router.post("/api/projects/{project_id}/render_jobs/{job_id}/cancel")
async def cancel_render_job(project_id: str, job_id: str) -> dict:
    """Cancel a running render job."""
    await _require_project(project_id)
    state = await _require_project(project_id)
    job = await DEFAULT_RENDER_JOB_SERVICE.cancel(Path(state.path), job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"render job not found: {job_id}")
    if job.status not in ("queued", "running", "cancelling"):
        return {"status": "already_terminal", "job_status": job.status}
    return {"status": "cancelled"}


@router.get("/api/projects/{project_id}/render_jobs/{job_id}")
async def get_render_job(project_id: str, job_id: str) -> RenderJobResponse:
    """Poll a background render job's status."""
    await _require_project(project_id)
    state = await _require_project(project_id)
    job = DEFAULT_RENDER_JOB_SERVICE.get(Path(state.path), job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"render job not found: {job_id}")
    return RenderJobResponse(
        job_id=job.job_id, project_id=job.project_id, mode=job.mode,
        status=job.status, output_path=job.output_path, error=job.error,
        created_at=job.created_at, graph_revision=job.graph_revision,
        edit_graph_hash=job.edit_graph_hash,
    )


@router.get("/api/projects/{project_id}/renders/{render_id}/file")
async def get_render_file(project_id: str, render_id: str) -> FileResponse:
    """Stream a rendered MP4 for in-browser preview (HTTP Range supported)."""
    state = await _require_project(project_id)
    project_path = Path(state.path)
    mp4_path = _resolve_render_mp4(project_path, render_id)
    if mp4_path is None:
        raise HTTPException(status_code=404, detail=f"render not found: {render_id}")
    return FileResponse(
        str(mp4_path),
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes"},
    )


def _resolve_render_mp4(project_path: Path, render_id: str) -> Path | None:
    """Locate a render MP4 under the project; reject path escape."""
    if not render_id or ".." in render_id or "/" in render_id or "\\" in render_id:
        return None
    if ".melt" in render_id.lower():
        return None
    job = DEFAULT_RENDER_JOB_SERVICE.get(project_path, render_id)
    if job is not None and job.output_path:
        candidate = Path(job.output_path).resolve()
        if (
            candidate.is_file()
            and _path_under_project(candidate, project_path)
            and projects_mod._is_complete_render_mp4(candidate)
        ):
            return candidate
    renders_dir = (project_path / ".open_edit" / "renders").resolve()
    for pattern in (f"{render_id}.mp4", f"*{render_id}*.mp4"):
        for hit in renders_dir.glob(pattern):
            resolved = hit.resolve()
            if (
                resolved.is_file()
                and _path_under_project(resolved, project_path)
                and projects_mod._is_complete_render_mp4(resolved)
            ):
                return resolved
    return None


def _path_under_project(path: Path, project_path: Path) -> bool:
    try:
        path.resolve().relative_to(project_path.resolve())
        return True
    except ValueError:
        return False
