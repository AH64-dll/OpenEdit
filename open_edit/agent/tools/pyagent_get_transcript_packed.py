"""pyagent_get_transcript_packed: returns silence-aware phrase-packed transcript for an asset."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from open_edit.agent.tools._helpers import get_asset_store
from open_edit.storage.transcription import pack_transcript


def get_transcript_packed(args: dict, project_path: str | Path) -> dict[str, Any]:
    """Return packed transcript string for target asset.

    Args:
        args: {"asset_hash": str, "pause_threshold_sec": float (optional, default 0.5)}
        project_path: path to the project directory.

    Returns:
        {"status": "ok", "asset_hash": str, "transcript_packed": str}
        or {"status": "error", "error": str} on failure.
    """
    try:
        asset_hash = args.get("asset_hash")
        if not asset_hash:
            return {"status": "error", "error": "asset_hash is required"}

        store = get_asset_store(project_path)
        asset = store.get(asset_hash)
        if asset is None:
            return {"status": "error", "error": f"asset {asset_hash} not found"}

        pause_thresh = float(
            args.get("pause_threshold_sec", args.get("pause_threshold_s", 0.5))
        )
        if not asset.alignment:
            return {
                "status": "error",
                "error": (
                    "asset has no word-level alignment yet. "
                    "Transcription may still be running server-side. "
                    "Wait a few seconds and retry."
                ),
                "retry": True,
            }

        packed = pack_transcript(asset.alignment, pause_threshold_sec=pause_thresh)

        # Single field — avoid 3× transcript token burn in MCP responses.
        return {
            "status": "ok",
            "asset_hash": asset_hash,
            "transcript_packed": packed,
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
