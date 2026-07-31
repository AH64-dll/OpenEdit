"""pyagent_get_transcript_packed: returns silence-aware phrase-packed transcript for an asset."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from open_edit.agent.tools._contract import get_asset_or_error, require_alignment, tool_result
from open_edit.storage.transcription import pack_transcript


@tool_result
def get_transcript_packed(args: dict, project_path: str | Path) -> dict[str, Any]:
    """Return packed transcript string for target asset.

    Args:
        args: {"asset_hash": str, "pause_threshold_sec": float (optional, default 0.5)}
        project_path: path to the project directory.

    Returns:
        {"status": "ok", "asset_hash": str, "transcript_packed": str}
        or {"status": "error", "error": str} on failure.
    """
    asset_hash = args.get("asset_hash")
    if not asset_hash:
        return {"status": "error", "error": "asset_hash is required"}

    asset, err = get_asset_or_error(project_path, asset_hash)
    if err:
        return err

    pause_thresh = float(args.get("pause_threshold_sec", 0.5))
    err = require_alignment(asset)
    if err:
        return err

    packed = pack_transcript(asset.alignment, pause_threshold_sec=pause_thresh)

    # Single field — avoid 3× transcript token burn in MCP responses.
    return {
        "status": "ok",
        "asset_hash": asset_hash,
        "transcript_packed": packed,
    }
