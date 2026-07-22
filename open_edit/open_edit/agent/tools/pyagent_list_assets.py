"""pyagent_list_assets: list all ingested assets in the project.

Replaces the phantom ``list_assets`` tool referenced in the
TOOL_USAGE_GUIDE (tool_schemas.py) that was never built.
"""
from __future__ import annotations

import json
from typing import Any

from open_edit.agent.tools._helpers import get_asset_store


def list_assets(args: dict, project_path: str) -> dict[str, Any]:
    """Return all ingested assets for the project.

    Scans ``<project>/.open_edit/assets/*/*.meta.json`` sidecar files.
    Returns a list of dicts with keys: hash, filename, duration_s,
    type, width, height, fps, codec, has_audio.
    """
    store = get_asset_store(project_path)
    assets_root = store.assets_dir
    assets: list[dict[str, Any]] = []

    if not assets_root.exists():
        return {"assets": assets}

    for meta_path in sorted(assets_root.glob("*/*.meta.json")):
        try:
            obj = json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        assets.append({
            "hash": obj.get("asset_hash", ""),
            "filename": obj.get("original_path", "").split("/")[-1] or meta_path.parent.name,
            "duration_s": obj.get("duration_sec", 0),
            "type": obj.get("type", "unknown"),
            "width": obj.get("width"),
            "height": obj.get("height"),
            "fps": obj.get("fps"),
            "codec": obj.get("codec"),
            "has_audio": obj.get("has_audio", False),
        })

    return {"assets": assets}
