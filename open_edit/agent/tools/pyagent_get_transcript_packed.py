"""pyagent_get_transcript_packed: returns silence-aware phrase-packed transcript for an asset."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from open_edit.agent.tools._contract import get_asset_or_error, require_alignment, tool_result
from open_edit.agent.tools._helpers import page_window
from open_edit.storage.transcription import pack_transcript


@tool_result
def get_transcript_packed(args: dict, project_path: str | Path) -> dict[str, Any]:
    """Return packed transcript string for target asset.

    Args:
        args: asset_hash, pause_threshold_sec (default 0.5), offset/limit in
            words (default page 500, maximum 2000). Follow next_offset.
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
    if not math.isfinite(pause_thresh) or pause_thresh < 0:
        return {"status": "error", "error": "pause_threshold_sec must be finite and nonnegative"}
    offset, limit = page_window(args, default_limit=500, max_limit=2000)
    err = require_alignment(asset)
    if err:
        return err

    packed = pack_transcript(asset.alignment[offset:offset + limit], pause_threshold_sec=pause_thresh)

    # Return one transcript representation and a cursor for longer recordings.
    return {
        "status": "ok",
        "asset_hash": asset_hash,
        "transcript_packed": packed,
        "total_words": len(asset.alignment),
        "offset": offset,
        "next_offset": offset + limit if offset + limit < len(asset.alignment) else None,
    }
