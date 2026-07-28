"""pyagent_propose_silence_cuts: returns inter-word silence gaps as cut suggestions.

Per phase4-design-revised.md section 4.2 (W3): the agent calls this tool
to find silence gaps in an asset's word-level alignment. The tool returns
gap suggestions; the agent decides whether to apply them as IR ops.

This is the PREFERRED way to find silence gaps. Do NOT hand-roll
``ffmpeg silencedetect`` on raw asset files — that bypasses the
alignment that was already computed server-side, often uses wrong asset
paths, and produces gaps that are not merged / breath-filtered /
min-segment-protected.
"""
from __future__ import annotations

from open_edit.agent.tools._helpers import get_asset_store


def propose_silence_cuts(args: dict, project_path: str) -> dict:
    """Return silence-cut suggestions for ``args['asset_hash']``.

    Args:
        args: {
            "asset_hash": str (required),
            "threshold_ms": int (optional, default 400) — minimum gap
                to even consider as silence,
            "keep_breath_ms": int (optional, default 600) — gaps below
                this are treated as breaths and NOT proposed as cuts,
            "min_segment_s": float (optional, default 2.0) — speech
                fragments shorter than this are protected: cuts that
                would create them are dropped or merged with adjacent
                cuts.
        }
        project_path: path to the project directory (or .kdenlive file).

    Returns:
        ``{"status": "ok", "gaps": [...]}`` on success, or
        ``{"status": "error", "error": "...", "retry": bool}`` on
        failure.

    When the asset has no alignment, the response includes
    ``"retry": True`` and an error message hinting that server-side
    transcription may still be in progress. The agent should wait
    briefly and retry rather than concluding the asset has no
    transcript and falling back to raw ffmpeg.
    """
    try:
        asset_hash = args.get("asset_hash")
        if not asset_hash:
            return {"status": "error", "error": "asset_hash is required"}

        asset_store = get_asset_store(project_path)
        asset = asset_store.get(asset_hash)
        if asset is None:
            return {
                "status": "error",
                "error": f"asset {asset_hash} not found",
            }
        if not asset.alignment:
            return {
                "status": "error",
                "error": (
                    "asset has no word-level alignment yet. Transcription "
                    "may still be running server-side. Wait a few seconds "
                    "and retry; do NOT fall back to raw ffmpeg "
                    "silencedetect on the asset file."
                ),
                "retry": True,
            }

        from open_edit.agent.skills.silence_cutter import propose_cuts

        gaps = propose_cuts(
            asset,
            silence_threshold_ms=args.get("threshold_ms", 400),
            keep_breath_ms=args.get("keep_breath_ms", 600),
            min_segment_s=args.get("min_segment_s", 2.0),
        )
        return {"status": "ok", "gaps": gaps}
    except Exception as e:
        return {"status": "error", "error": str(e)}
