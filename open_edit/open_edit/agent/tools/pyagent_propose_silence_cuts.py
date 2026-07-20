"""pyagent_propose_silence_cuts: returns inter-word silence gaps as cut suggestions.

Per phase4-design-revised.md section 4.2 (W3): the agent calls this tool to
find silence gaps in an asset's word-level alignment. The tool returns
gap suggestions; the agent decides whether to apply them as IR ops.
"""
from __future__ import annotations

from open_edit.agent.tools._helpers import get_asset_store


def propose_silence_cuts(args: dict, project_path: str) -> dict:
    """Return silence-cut suggestions for `args['asset_hash']`.

    Args:
        args: {"asset_hash": str, "threshold_ms": int (optional, default 400)}
        project_path: path to the project directory (or .kdenlive file).

    Returns:
        {"status": "ok", "gaps": [{"t_start", "t_end", "suggested_kind"}, ...]}
        or {"status": "error", "error": "..."} on failure.
    """
    asset_store = get_asset_store(project_path)
    asset = asset_store.get(args["asset_hash"])
    if asset is None:
        return {"status": "error", "error": f"asset {args['asset_hash']} not found"}
    if not asset.alignment:
        return {
            "status": "error",
            "error": "asset has no word-level alignment (Whisper not run?)",
        }
    from open_edit.agent.skills.silence_cutter import propose_cuts
    gaps = propose_cuts(asset, silence_threshold_ms=args.get("threshold_ms", 400))
    return {"status": "ok", "gaps": gaps}
