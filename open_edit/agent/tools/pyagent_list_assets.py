"""pyagent_list_assets: list all ingested assets in the project.

Exported as ``list_assets`` from ``open_edit.agent.tools``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from open_edit.agent.tools._helpers import get_asset_store

# Remotion materialize CAS names look like: <uuid>_<12hex>.mov|.webm
_DERIVATIVE_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_[0-9a-f]+\.(mov|webm)$",
    re.IGNORECASE,
)


def _is_derivative(filename: str, codec: Any) -> bool:
    name = filename or ""
    if _DERIVATIVE_RE.match(name):
        return True
    # Extra guard: rematerialized ProRes/VP8 overlays with uuid prefixes
    if codec in ("prores", "vp8", "vp9") and "-" in name and "_" in name:
        head = name.split("_", 1)[0]
        if len(head) == 36 and head.count("-") == 4:
            return True
    return False


def list_assets(args: dict, project_path: str) -> dict[str, Any]:
    """Return ingested assets for the project.

    By default **excludes** Remotion rematerialized CAS derivatives and
    returns compact rows (hash/filename/duration). Pass
    ``include_derivatives: true`` and/or ``detail: true`` when needed.
    """
    try:
        store = get_asset_store(project_path)
        assets_root = store.assets_dir
        assets: list[dict[str, Any]] = []
        include_derivatives = bool(
            (args or {}).get("include_derivatives", False)
        )
        detail = bool((args or {}).get("detail", False))

        if not assets_root.exists():
            return {
                "assets": assets,
                "filtered": True,
                "include_derivatives": include_derivatives,
                "detail": detail,
            }

        skipped = 0
        for meta_path in sorted(assets_root.glob("*/*.meta.json")):
            try:
                obj = json.loads(meta_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            original = obj.get("original_path", "") or ""
            filename = Path(original).name if original else meta_path.parent.name
            codec = obj.get("codec")
            if not include_derivatives and _is_derivative(filename, codec):
                skipped += 1
                continue
            row: dict[str, Any] = {
                "hash": obj.get("asset_hash", ""),
                "filename": filename,
                "duration_s": obj.get("duration_sec", 0),
            }
            if detail:
                row.update({
                    "type": obj.get("type", "unknown"),
                    "width": obj.get("width"),
                    "height": obj.get("height"),
                    "fps": obj.get("fps"),
                    "codec": codec,
                    "has_audio": obj.get("has_audio", False),
                })
            assets.append(row)

        return {
            "assets": assets,
            "filtered": not include_derivatives,
            "skipped_derivatives": skipped,
            "include_derivatives": include_derivatives,
            "detail": detail,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
