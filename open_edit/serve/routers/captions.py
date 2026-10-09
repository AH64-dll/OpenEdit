"""Caption interchange, identical preview raster and local project font import."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from open_edit.kernel.captions import format_srt, from_transcript, parse_srt, store_font
from open_edit.kernel.export_service import project_timeline
from open_edit.kernel.studio_service import commit_studio
from open_edit.render.captions import caption_image
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import GraphRevisionConflict

from .projects import _require_project

router = APIRouter()


class SubtitleSource(BaseModel):
    source: str = Field(max_length=2 * 1024 * 1024)


@router.post("/api/projects/{project_id}/captions/parse")
async def parse(project_id: str, request: SubtitleSource):
    await _require_project(project_id)
    try:
        return {"changes": parse_srt(request.source)}
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.get("/api/projects/{project_id}/captions.srt")
async def download(project_id: str):
    project = await _require_project(project_id)
    timeline = await run_in_threadpool(project_timeline, Path(project.path))
    return Response(
        format_srt([c for c in timeline.captions.values() if c.enabled]),
        media_type="application/x-subrip",
        headers={"Content-Disposition": 'attachment; filename="captions.srt"'},
    )


@router.get("/api/projects/{project_id}/captions/{caption_id}/image")
async def image(project_id: str, caption_id: str, width: int = 1280, height: int = 720):
    project = await _require_project(project_id)
    timeline = await run_in_threadpool(project_timeline, Path(project.path))
    cue = timeline.captions.get(caption_id)
    if not cue:
        raise HTTPException(404, "Caption is unavailable")
    try:
        path = await run_in_threadpool(caption_image, Path(project.path), cue, width, height)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-cache"})


@router.post("/api/projects/{project_id}/captions/from-clip/{clip_id}")
async def from_clip(project_id: str, clip_id: str, transcribe: bool = False):
    project = await _require_project(project_id)
    root = Path(project.path)
    timeline = await run_in_threadpool(project_timeline, root)
    clip = next((c for t in timeline.tracks for c in t.clips if c.clip_id == clip_id), None)
    store = AssetStore(root / ".open_edit/assets")
    asset = store.get(clip.asset_hash) if clip else None
    if not clip or not asset or not asset.has_audio:
        raise HTTPException(400, "Select a media clip with audio")
    words = asset.alignment
    if transcribe and not words:
        from open_edit.storage.transcription import _has_whisper
        from open_edit.storage.transcription import transcribe as analyze

        if not _has_whisper():
            raise HTTPException(
                400, "Install the optional faster-whisper package to transcribe locally"
            )
        words = await run_in_threadpool(analyze, store.path(asset.asset_hash))
        if words:
            await run_in_threadpool(store.update_alignment, asset.asset_hash, words)
    if not words:
        raise HTTPException(
            400, "This clip has no transcript; use local transcription or import SRT"
        )
    return {
        "changes": from_transcript(
            words,
            position_sec=clip.position_sec,
            in_sec=clip.in_point_sec,
            out_sec=clip.out_point_sec,
        )
    }


@router.post("/api/projects/{project_id}/fonts", status_code=201)
async def font(
    project_id: str,
    file: Annotated[UploadFile, File()],
    expected_revision: int = Form(...),
    label: str = Form(...),
):
    project = await _require_project(project_id)
    root = Path(project.path)
    try:
        content = await file.read(8 * 1024 * 1024 + 1)
        identity = await run_in_threadpool(store_font, root, content)
        return await run_in_threadpool(
            commit_studio,
            root,
            expected_revision=expected_revision,
            changes=[
                {
                    "kind": "font",
                    "object_id": "font-" + identity[:32],
                    "data": {"font_id": identity, "label": label},
                }
            ],
            label="Import project font",
        )
    except GraphRevisionConflict as error:
        raise HTTPException(409, str(error)) from error
    except (ValueError, OSError) as error:
        raise HTTPException(400, str(error)) from error
