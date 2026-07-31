"""Asset streaming routes (v1.4 P0-2)."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .projects import _require_project

router = APIRouter()

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


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
    cas_path = Path(asset.stored_path)
    if not cas_path.exists():
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
