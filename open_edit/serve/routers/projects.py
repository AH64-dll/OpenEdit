"""Project routes: CRUD, ingest, notes, thumbnails."""
from __future__ import annotations

import asyncio
import logging
import subprocess
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from open_edit.ir.ids import new_id, now_iso8601

from .. import projects as projects_mod
from ..errors import ErrorCodes, make_error
from ..upload import UploadTooLargeError, _copy_upload_limited, _max_upload_bytes

_LOG = logging.getLogger("open_edit.serve.routers.projects")

router = APIRouter()


class CreateProjectRequest(BaseModel):
    name: str


class CreateNoteRequest(BaseModel):
    text: str
    t_start: float
    t_end: float | None = None
    source: str = "typed"
    track_kind: str = "any"  # "video" | "audio" | "any"
    track_id: str | None = None


class UpdateNoteRequest(BaseModel):
    text: str | None = None
    t_start: float | None = None
    t_end: float | None = None
    track_kind: str | None = None
    track_id: str | None = None
    status: str | None = None


async def _require_project(project_id: str) -> projects_mod.ProjectState:
    """Return the project state or raise 404."""
    try:
        return await projects_mod.get_project_state(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def _notes_store_for(project_path: Path):
    from open_edit.storage.notes import NotesStore

    return NotesStore(project_path / "notes.db")


def _canonical_note_project_id(project_id: str, project_path: Path) -> str:
    db_path = project_path / ".open_edit" / "edit_graph.db"
    if db_path.exists():
        try:
            from open_edit.storage.edit_graph import EditGraphStore
            return EditGraphStore(db_path).project_id
        except Exception:
            pass
    return project_id


def _normalize_track_kind(raw: str | None) -> str:
    kind = (raw or "any").strip().lower()
    return kind if kind in ("video", "audio", "any") else "any"


@router.get("/api/projects")
async def get_projects() -> list[projects_mod.ProjectInfo]:
    return await projects_mod.list_projects()


@router.post("/api/projects", status_code=201)
async def post_create_project(req: CreateProjectRequest) -> Any:
    try:
        return await projects_mod.create_project(req.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        return JSONResponse(
            status_code=500,
            content=make_error(
                ErrorCodes.PROJECT_INITIALIZATION_FAILED,
                str(exc),
                retriable=True,
            ),
        )


@router.get("/api/projects/{project_id}")
async def get_project(project_id: str) -> projects_mod.ProjectState:
    try:
        return await projects_mod.get_project_state(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/api/projects/{project_id}/ingest", status_code=202)
async def post_ingest(
    project_id: str,
    files: list[UploadFile] = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> dict[str, Any]:
    """Ingest one or more files under the canonical ``files`` form field.

    Each file is isolated in a unique inbox path and bounded while streaming.
    The operation intentionally allows partial success: a bad file never
    removes already ingested assets from the same user selection.
    """
    state = await _require_project(project_id)
    project_path = Path(state.path)
    from open_edit.storage.assets import AssetStore

    assets_dir = project_path / ".open_edit" / "assets"
    inbox_dir = project_path / ".open_edit" / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    store = AssetStore(assets_dir)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    max_bytes = _max_upload_bytes()

    for upload in files:
        safe_name = Path(upload.filename or "upload.bin").name or "upload.bin"
        # Preserve the original basename in asset metadata while ensuring
        # concurrent uploads never share a temporary source path.
        temp_path = inbox_dir / f"{uuid.uuid4().hex}_{safe_name}"
        try:
            await asyncio.to_thread(_copy_upload_limited, upload.file, temp_path, max_bytes)
            asset = await asyncio.to_thread(store.ingest, str(temp_path), False)
        except subprocess.CalledProcessError as exc:
            _LOG.info("rejected invalid media upload %s", safe_name)
            rejected.append({"filename": safe_name, "error": "not a recognised media file"})
        except UploadTooLargeError as exc:
            rejected.append({"filename": safe_name, "error": str(exc)})
        except ValueError as exc:
            rejected.append({"filename": safe_name, "error": str(exc)})
        except OSError:
            _LOG.exception("failed to ingest upload %s", safe_name)
            rejected.append({"filename": safe_name, "error": "upload processing failed"})
        else:
            asset_info = projects_mod._asset_to_info(asset, project_id).model_dump(mode="json")
            accepted.append({
                "filename": safe_name,
                "asset": asset_info,
                "transcribing": asset.has_audio,
            })
            if asset.has_audio:
                background_tasks.add_task(
                    _transcribe_in_background, assets_dir, asset.asset_hash, asset.stored_path
                )
        finally:
            await asyncio.to_thread(temp_path.unlink, missing_ok=True)
            await upload.close()

    return {
        "project_id": project_id,
        "accepted": accepted,
        "rejected": rejected,
    }


def _transcribe_in_background(
    assets_dir: Path, asset_hash: str, stored_path: str
) -> None:
    """Background Whisper pass: transcribe and patch the asset sidecar."""
    try:
        from open_edit.storage.assets import AssetStore
        from open_edit.storage.transcription import transcribe

        alignment = transcribe(Path(stored_path))
        AssetStore(assets_dir).update_alignment(asset_hash, alignment)
        _LOG.info(
            "background transcription done: %s (%d words)",
            asset_hash[:8],
            len(alignment),
        )
    except Exception as exc:  # never break the response that already shipped
        _LOG.warning(
            "background transcription failed for %s: %s", asset_hash[:8], exc
        )


@router.post("/api/projects/{project_id}/notes", status_code=201)
async def post_project_note(project_id: str, req: CreateNoteRequest) -> JSONResponse:
    """Append a timestamp-anchored review note (readable by MCP get_pending_notes)."""
    state = await _require_project(project_id)
    project_path = Path(state.path)
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    t_start = max(0.0, float(req.t_start))
    t_end = float(req.t_end) if req.t_end is not None else t_start
    if t_end < t_start:
        t_end = t_start
    track_kind = _normalize_track_kind(req.track_kind)
    track_id = (req.track_id or "").strip() or None

    from open_edit.storage.notes import (
        NoteSource,
        NoteStatus,
        ReviewNote,
        TimestampAnchor,
    )

    store = _notes_store_for(project_path)
    note_project_id = _canonical_note_project_id(project_id, project_path)
    note = ReviewNote(
        note_id=new_id(),
        project_id=note_project_id,
        anchor=TimestampAnchor(
            t_start=t_start,
            t_end=t_end,
            track_kind=track_kind,  # type: ignore[arg-type]
            track_id=track_id,
        ),
        text=text,
        source=NoteSource.typed if req.source == "typed" else NoteSource.typed,
        status=NoteStatus.pending,
        created_at=now_iso8601(),
    )
    store.append(note)
    return JSONResponse({
        "note_id": note.note_id,
        "t_start": t_start,
        "t_end": t_end,
        "text": text,
        "status": note.status.value,
        "track_kind": track_kind,
        "track_id": track_id,
    })


@router.patch("/api/projects/{project_id}/notes/{note_id}")
async def patch_project_note(
    project_id: str, note_id: str, req: UpdateNoteRequest
) -> JSONResponse:
    """Edit an existing review note (text / time / track target / status)."""
    state = await _require_project(project_id)
    project_path = Path(state.path)
    from open_edit.storage.notes import NoteStatus, TimestampAnchor

    store = _notes_store_for(project_path)
    existing = store.get(note_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="note not found")

    text = existing.text
    if req.text is not None:
        text = req.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="text is required")

    status = existing.status
    if req.status is not None:
        try:
            status = NoteStatus(req.status)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid status") from exc

    anchor = existing.anchor
    if getattr(anchor, "anchor_type", None) == "timestamp" or hasattr(anchor, "t_start"):
        t_start = float(req.t_start) if req.t_start is not None else float(anchor.t_start)
        t_end = float(req.t_end) if req.t_end is not None else float(getattr(anchor, "t_end", t_start))
        if t_end < t_start:
            t_end = t_start
        track_kind = _normalize_track_kind(
            req.track_kind if req.track_kind is not None else getattr(anchor, "track_kind", "any")
        )
        track_id = (
            (req.track_id.strip() or None)
            if req.track_id is not None
            else getattr(anchor, "track_id", None)
        )
        anchor = TimestampAnchor(
            t_start=max(0.0, t_start),
            t_end=t_end,
            track_kind=track_kind,  # type: ignore[arg-type]
            track_id=track_id,
        )

    store.update(note_id, text=text, status=status, anchor=anchor)
    updated = store.get(note_id)
    info = projects_mod._note_to_info(updated) if updated else None
    return JSONResponse(info.model_dump() if info else {"note_id": note_id})


@router.delete("/api/projects/{project_id}/notes/{note_id}", status_code=200)
async def delete_project_note(project_id: str, note_id: str) -> JSONResponse:
    """Permanently delete a review note."""
    state = await _require_project(project_id)
    project_path = Path(state.path)
    store = _notes_store_for(project_path)
    existing = store.get(note_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="note not found")
    store.delete([note_id])
    return JSONResponse({"ok": True, "note_id": note_id})


@router.get("/api/projects/{project_id}/thumbnail")
async def get_thumbnail(project_id: str) -> Any:
    """Serve the project's thumbnail.

    Looks for ``.open_edit/thumbnail.png`` (or .jpg) in the project folder.
    """
    state = await _require_project(project_id)
    project_path = Path(state.path)
    for name in ("thumbnail.png", "thumbnail.jpg", "thumbnail.jpeg"):
        f = project_path / ".open_edit" / name
        if f.exists():
            return FileResponse(str(f))
    raise HTTPException(status_code=404, detail="no thumbnail available")
