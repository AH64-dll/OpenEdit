"""pyagent_ingest_local: ingest local media files into the project CAS.

Paths must be absolute. Any readable local media file may be ingested;
symlinks are resolved before the source is copied into the project CAS.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from open_edit.agent.tools._contract import tool_result
from open_edit.agent.tools._helpers import get_asset_store

_MEDIA_SUFFIXES = {
    ".mp4", ".mkv", ".mov", ".webm", ".m4v",
    ".mp3", ".wav", ".aac", ".flac", ".m4a",
    ".jpg", ".jpeg", ".png", ".webp",
}


@tool_result
def ingest_local(args: dict, project_path: str) -> dict[str, Any]:
    """Ingest local files into ``.open_edit/assets``.

    Args:
        args: {
            "paths": list[str] (required) — absolute file paths,
            "transcribe": bool (optional, default True),
        }
        project_path: Open Edit project directory.
    """
    raw_paths = args.get("paths")
    if not isinstance(raw_paths, list) or not raw_paths:
        return {
            "status": "error",
            "error": "paths must be a non-empty list of absolute file paths",
            "expected_keys": ["paths"],
        }

    do_transcribe = bool(args.get("transcribe", True))
    store = get_asset_store(project_path)

    ingested: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for item in raw_paths:
        if not isinstance(item, str) or not item.strip():
            errors.append({"path": str(item), "error": "path must be a non-empty string"})
            continue
        path = Path(item).expanduser()
        if not path.is_absolute():
            errors.append({"path": item, "error": "path must be absolute"})
            continue
        if not path.is_file():
            errors.append({"path": item, "error": "file not found"})
            continue
        if path.suffix.lower() not in _MEDIA_SUFFIXES:
            errors.append({
                "path": item,
                "error": f"unsupported media suffix: {path.suffix}",
            })
            continue
        try:
            asset = store.ingest(str(path.resolve()), transcribe=do_transcribe)
        except Exception as exc:
            errors.append({"path": item, "error": str(exc)})
            continue
        ingested.append({
            "hash": asset.asset_hash,
            "filename": path.name,
            "duration_s": asset.duration_sec,
            "type": asset.type,
            "has_audio": asset.has_audio,
            "words": len(asset.alignment or []),
        })

    status = "ok" if ingested and not errors else ("partial" if ingested else "error")
    return {
        "status": status,
        "ingested": ingested,
        "errors": errors,
        "count": len(ingested),
    }
