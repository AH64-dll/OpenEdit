"""pyagent_ingest_local: ingest local media files into the project CAS.

Paths must be absolute and resolve under the project directory or under
``OPEN_EDIT_INGEST_ALLOWLIST`` (``os.pathsep``-separated absolute roots;
``:`` on POSIX, ``;`` on Windows).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from open_edit.agent.tools._contract import tool_result
from open_edit.agent.tools._helpers import get_asset_store

_MEDIA_SUFFIXES = {
    ".mp4", ".mkv", ".mov", ".webm", ".m4v",
    ".mp3", ".wav", ".aac", ".flac", ".m4a",
    ".jpg", ".jpeg", ".png", ".webp",
}


def _allowlist_roots(project_path: Path) -> list[Path]:
    roots = [project_path.resolve()]
    raw = (os.environ.get("OPEN_EDIT_INGEST_ALLOWLIST") or "").strip()
    for part in raw.split(os.pathsep):
        part = part.strip()
        if not part:
            continue
        roots.append(Path(part).expanduser().resolve())
    return roots


def _path_allowed(path: Path, roots: list[Path]) -> bool:
    resolved = path.resolve()
    for root in roots:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


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

    project = Path(project_path).resolve()
    roots = _allowlist_roots(project)
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
        if not _path_allowed(path, roots):
            errors.append({
                "path": item,
                "error": (
                    "path escapes project and OPEN_EDIT_INGEST_ALLOWLIST; "
                    "set OPEN_EDIT_INGEST_ALLOWLIST to a colon-separated "
                    "list of allowed absolute roots"
                ),
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
