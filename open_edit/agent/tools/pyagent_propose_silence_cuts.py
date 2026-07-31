"""pyagent_propose_silence_cuts: returns inter-word silence gaps as cut suggestions.

Per phase4-design-revised.md section 4.2 (W3): the agent calls this tool to
find silence gaps in an asset's word-level alignment. The tool returns
gap suggestions; the agent decides whether to apply them as IR ops.
"""
from __future__ import annotations

from open_edit.agent.tools._contract import get_asset_or_error, require_alignment, tool_result


@tool_result
def propose_silence_cuts(args: dict, project_path: str) -> dict:
    """Return silence-cut suggestions for ``args['asset_hash']``.

    Args:
        args: {
            "asset_hash": str (required),
            "threshold_ms": int (optional, default 400),
            "min_segment_s": float (optional, default 0.0; merge gaps
                separated by shorter speech)
        }
        project_path: path to the project directory (or .kdenlive file).

    Returns:
        ``{"status": "ok", "gaps": [...]}`` on success,
        ``{"status": "error", "error": "..."}`` on failure, or
        ``{"status": "retry", "error": "..."}`` when the asset has no
        alignment yet (transcription may still be in progress).
    """
    asset_hash = args.get("asset_hash")
    if not asset_hash:
        return {"status": "error", "error": "asset_hash is required"}
    asset, err = get_asset_or_error(project_path, asset_hash)
    if err:
        return err
    err = require_alignment(asset)
    if err:
        return err
    from open_edit.agent.skills.silence_cutter import propose_cuts
    gaps = propose_cuts(
        asset,
        silence_threshold_ms=args.get("threshold_ms", 400),
        min_segment_s=args.get("min_segment_s", 0.0),
    )
    return {"status": "ok", "gaps": gaps}
