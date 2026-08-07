"""Asset streaming routes (v1.4 P0-2)."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from open_edit.kernel.asset_proxy_jobs import (
    DEFAULT_ASSET_PROXY_JOB_SERVICE,
    AssetProxyJob,
)
from open_edit.render.source_proxy import DEFAULT_SOURCE_PROXY_PROFILE

from .projects import _require_project

router = APIRouter()

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class AssetProxyRequest(BaseModel):
    profile: str = DEFAULT_SOURCE_PROXY_PROFILE.name


class AssetProxyJobResponse(BaseModel):
    job_id: str
    project_id: str
    asset_hash: str
    profile: str
    status: str
    created_at: float
    updated_at: float
    proxy_hash: str | None = None
    error: str | None = None


def _asset_proxy_job_response(job: AssetProxyJob) -> AssetProxyJobResponse:
    return AssetProxyJobResponse(
        job_id=job.job_id,
        project_id=job.project_id,
        asset_hash=job.asset_hash,
        profile=job.profile,
        status=job.status,
        created_at=job.created_at,
        updated_at=job.updated_at,
        proxy_hash=job.proxy_hash,
        error=job.error,
    )


@router.get("/api/projects/{project_id}/assets/{asset_hash}/file")
async def get_asset_file(project_id: str, asset_hash: str) -> FileResponse:
    """Stream an asset's bytes for the preview player.

    v1.4 P0-2: without this route, the frontend has nothing to set
    ``<video src>`` to and the preview modal is empty. The route
    serves the CAS file with the right ``Content-Type`` (so the
    browser actually plays the response) and supports HTTP Range
    requests (so ``<video>`` can seek — without 206 support, some
    browsers refuse to play).

    The asset hash is validated as a 64-char lowercase hex string
    before being used in a filesystem path so this route can't be
    abused to probe arbitrary files.
    """
    if not _HASH_RE.fullmatch(asset_hash):
        raise HTTPException(status_code=400, detail="invalid asset hash")
    state = await _require_project(project_id)
    project_path = Path(state.path)

    from open_edit.storage.assets import AssetStore

    assets_dir = project_path / ".open_edit" / "assets"
    store = AssetStore(assets_dir)
    asset = store.get(asset_hash)
    if asset is None:
        raise HTTPException(
            status_code=404, detail=f"asset not found: {asset_hash[:12]}"
        )
    # Prefer the sidecar's stored path, but fall back to the deterministic
    # CAS location (assets_dir/<hash[0:2]>/<hash>) when the sidecar path is
    # stale — e.g. a project folder moved between machines/homes and the
    # sidecar still holds an absolute legacy path. Keeps previews working.
    cas_path = Path(asset.stored_path)
    if not cas_path.is_file():
        cas_path = store.path(asset_hash)
    if cas_path is None or not cas_path.is_file():
        raise HTTPException(
            status_code=404, detail=f"asset bytes missing: {asset_hash[:12]}"
        )

    # Pick the mime type from the original filename's extension. The
    # CAS file itself has no extension (it's stored under
    # ``<prefix>/<hash>``), so ``mimetypes.guess_type`` from a bare
    # ``Path("13957...").suffix`` returns ``None``. The original
    # filename (e.g. ``clip_short.mp4``) is preserved in the sidecar.
    media_type = _guess_mime_type(asset)

    return FileResponse(
        str(cas_path),
        media_type=media_type,
        # ``Accept-Ranges: bytes`` is set automatically by Starlette's
        # ``FileResponse`` when the client sends a Range header (it
        # replies with 206 Partial Content). We also set it
        # unconditionally so the browser knows it can ask for a Range
        # up front.
        headers={"Accept-Ranges": "bytes"},
    )


@router.post(
    "/api/projects/{project_id}/assets/{asset_hash}/proxy",
    status_code=202,
)
async def post_asset_proxy(
    project_id: str,
    asset_hash: str,
    request: AssetProxyRequest,
) -> AssetProxyJobResponse:
    """Queue host-side source-proxy generation and return its job id."""
    if not _HASH_RE.fullmatch(asset_hash):
        raise HTTPException(status_code=400, detail="invalid asset hash")
    profile = request.profile.strip()
    if profile != DEFAULT_SOURCE_PROXY_PROFILE.name:
        raise HTTPException(status_code=400, detail=f"unknown source proxy profile: {profile}")

    state = await _require_project(project_id)
    try:
        job = DEFAULT_ASSET_PROXY_JOB_SERVICE.enqueue(
            project_id,
            Path(state.path),
            asset_hash,
            profile=DEFAULT_SOURCE_PROXY_PROFILE,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _asset_proxy_job_response(job)


@router.get(
    "/api/projects/{project_id}/asset_proxy_jobs/{job_id}",
)
async def get_asset_proxy_job(
    project_id: str,
    job_id: str,
) -> AssetProxyJobResponse:
    """Return durable source-proxy job state."""
    state = await _require_project(project_id)
    job = DEFAULT_ASSET_PROXY_JOB_SERVICE.get(Path(state.path), job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"asset proxy job not found: {job_id}")
    return _asset_proxy_job_response(job)


def _guess_mime_type(asset: Asset) -> str:  # noqa: F821
    """Best-effort mime type for a streamed asset.

    Prefers the original filename's extension (``clip_short.mp4`` →
    ``video/mp4``); falls back to ``application/octet-stream`` for
    types we don't know. The stdlib ``mimetypes`` is enough for the
    common formats — we don't need ``python-magic``.
    """
    import mimetypes

    name = asset.original_path or asset.stored_path
    guess, _ = mimetypes.guess_type(name)
    return guess or "application/octet-stream"
