"""Project-scoped preview-chunk manifest, file, and wipe routes."""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from open_edit.kernel.render_jobs import DEFAULT_RENDER_JOB_SERVICE, public_job
from open_edit.render.preview_cache import PreviewChunkCache
from open_edit.render.preview_manifest import PreviewManifest

from .. import projects as projects_mod
from ..auth import _check_rate_limit
from .projects import _require_project

router = APIRouter()

_ACTIVE_JOB_STATUSES = frozenset({"queued", "running", "cancelling"})
_PREVIEW_CACHE_NAME = "preview_chunks"


def _cache_for_project(project_path: Path) -> PreviewChunkCache:
    project_root = project_path.resolve()
    open_edit_root = project_root / ".open_edit"
    cache_root = open_edit_root / _PREVIEW_CACHE_NAME
    # Do not follow a project-controlled symlink into another project's cache
    # or an arbitrary host directory.
    if open_edit_root.is_symlink() or cache_root.is_symlink():
        raise HTTPException(status_code=404, detail="preview cache unavailable")
    cache = PreviewChunkCache(cache_root)
    if not _path_under_project(cache.root, project_root):
        raise HTTPException(status_code=404, detail="preview cache unavailable")
    return cache


def preview_artifact_url(project_id: str, artifact_id: str) -> str:
    """Return a browser URL that identifies an artifact, never its path."""
    return (
        f"/api/projects/{quote(project_id, safe='')}/preview-chunks/files/"
        f"{quote(artifact_id, safe='')}"
    )


def _manifest_payload(
    manifest: PreviewManifest | None,
    project_id: str,
) -> dict[str, Any] | None:
    if manifest is None or manifest.project_id != project_id:
        return None

    payload = manifest.model_dump(mode="json")
    for chunk in payload.get("chunks", []):
        if not isinstance(chunk, dict):
            continue
        for plane in ("video", "audio", "playback"):
            state = chunk.get(plane)
            if not isinstance(state, dict):
                continue
            for state_name in ("current", "fallback"):
                artifact = state.get(state_name)
                if not isinstance(artifact, dict):
                    continue
                artifact_id = artifact.get("artifact_id")
                if isinstance(artifact_id, str):
                    artifact["url"] = preview_artifact_url(project_id, artifact_id)
    return payload


def _project_job_rows(project_path: Path, project_id: str) -> list[Any]:
    """Return only jobs bound to this project path and public project ID."""
    return [
        job
        for job in DEFAULT_RENDER_JOB_SERVICE.list_jobs(project_path)
        if getattr(job, "project_id", None) == project_id
    ]


def _active_preview_job(project_path: Path, project_id: str) -> dict[str, Any] | None:
    jobs = [
        job
        for job in _project_job_rows(project_path, project_id)
        if getattr(job, "mode", None) == "preview-chunks"
        and getattr(job, "status", None) in _ACTIVE_JOB_STATUSES
    ]
    if not jobs:
        return None
    job = max(jobs, key=lambda item: getattr(item, "created_at", 0.0))
    return public_job(job)


def _path_under_project(path: Path, project_path: Path) -> bool:
    try:
        path.resolve().relative_to(project_path.resolve())
        return True
    except ValueError:
        return False


def _proxy_fallback(
    project_path: Path,
    project_id: str,
    manifest: PreviewManifest | None,
) -> dict[str, Any] | None:
    """Return the newest safe whole-file proxy for stale-chunk fallback."""
    candidates: list[tuple[float, dict[str, Any]]] = []
    for job in _project_job_rows(project_path, project_id):
        if (
            getattr(job, "mode", None) != "proxy"
            or getattr(job, "status", None) != "succeeded"
        ):
            continue
        output_path = getattr(job, "output_path", None)
        if not isinstance(output_path, str) or not output_path:
            continue
        path = Path(output_path).resolve()
        if (
            not _path_under_project(path, project_path)
            or not path.is_file()
            or not projects_mod._is_complete_render_mp4(path)
        ):
            continue
        graph_hash = getattr(job, "edit_graph_hash", None)
        candidates.append(
            (
                float(getattr(job, "updated_at", 0.0)),
                {
                    "job_id": job.job_id,
                    "url": (
                        f"/api/projects/{quote(project_id, safe='')}/renders/"
                        f"{quote(job.job_id, safe='')}/file"
                    ),
                    "status": job.status,
                    "graph_revision": getattr(job, "graph_revision", None),
                    "edit_graph_hash": graph_hash,
                    "stale": (
                        manifest is not None
                        and graph_hash is not None
                        and graph_hash != manifest.edit_graph_hash
                    ),
                },
            )
        )

    if candidates:
        return max(candidates, key=lambda item: item[0])[1]

    # Older projects may have a proxy file without a durable job row.  Keep
    # this fallback path project-scoped and use the filename as the existing
    # render-file route's ID; no filesystem path is returned to the browser.
    renders_dir = (project_path / ".open_edit" / "renders").resolve()
    if not renders_dir.is_dir():
        return None
    files = [
        path.resolve()
        for path in renders_dir.glob("*.mp4")
        if path.is_file()
        and _path_under_project(path, project_path)
        and projects_mod._is_complete_render_mp4(path)
    ]
    if not files:
        return None
    path = max(files, key=lambda item: item.stat().st_mtime)
    return {
        "job_id": path.stem,
        "url": (
            f"/api/projects/{quote(project_id, safe='')}/renders/"
            f"{quote(path.stem, safe='')}/file"
        ),
        "status": "succeeded",
        "graph_revision": None,
        "edit_graph_hash": None,
        "stale": manifest is not None,
    }


def _artifact_mime(cache: PreviewChunkCache, artifact_id: str, path: Path) -> str:
    entry = getattr(cache, "_index", {}).get(artifact_id)
    if isinstance(entry, dict) and isinstance(entry.get("mime"), str):
        return entry["mime"]
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


@router.get("/api/projects/{project_id}/preview-chunks")
async def get_preview_chunks(project_id: str) -> dict[str, Any]:
    """Return the project manifest, active preview job, and proxy fallback."""
    state = await _require_project(project_id)
    project_path = Path(state.path)
    cache = _cache_for_project(project_path)
    manifest = cache.read_manifest()
    return {
        "manifest": _manifest_payload(manifest, project_id),
        "active_job": _active_preview_job(project_path, project_id),
        "proxy_fallback": _proxy_fallback(project_path, project_id, manifest),
    }


@router.get("/api/projects/{project_id}/preview-chunks/files/{artifact_id}")
async def get_preview_chunk_file(project_id: str, artifact_id: str) -> FileResponse:
    """Stream an indexed preview artifact without accepting a client path."""
    state = await _require_project(project_id)
    project_path = Path(state.path)
    cache = _cache_for_project(project_path)
    # Loading the manifest first also reconstructs indexes from older caches.
    cache.read_manifest()
    artifact_path = cache.resolve_artifact(artifact_id)
    if (
        artifact_path is None
        or not artifact_path.is_file()
        or not _path_under_project(artifact_path, cache.root)
    ):
        raise HTTPException(status_code=404, detail="preview artifact not found")
    return FileResponse(
        str(artifact_path),
        media_type=_artifact_mime(cache, artifact_id, artifact_path),
        headers={"Accept-Ranges": "bytes"},
    )


@router.delete("/api/projects/{project_id}/preview-chunks")
async def delete_preview_chunks(project_id: str) -> dict[str, int]:
    """Wipe only this project's preview cache."""
    _check_rate_limit(f"preview-wipe:{project_id}", max_requests=5, window_sec=300)
    state = await _require_project(project_id)
    return _cache_for_project(Path(state.path)).wipe()
