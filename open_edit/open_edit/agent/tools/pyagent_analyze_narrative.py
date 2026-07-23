"""pyagent_analyze_narrative: returns narrative segments for the asset.

Per phase4-design-revised.md section 4.1 (W4): the agent calls this tool to
segment an asset's word-level alignment into 7 narrative beat types. The
agent decides how to use the segments (e.g., for motion-graphics planning).
"""
from __future__ import annotations

from open_edit.agent.tools._helpers import get_asset_store


def analyze_narrative(args: dict, project_path: str) -> dict:
    """Return narrative segments for `args['asset_hash']`.

    Args:
        args: {"asset_hash": str (optional, omit to analyse whole timeline),
               "use_llm": bool (optional, default False)}
        project_path: path to the project directory (or .kdenlive file).

    Returns:
        {"status": "ok", "segments": [NarrativeSegment.model_dump(), ...]}
        or {"status": "error", "error": "..."} on failure.
    """
    try:
        asset_hash = args.get("asset_hash")
        if not asset_hash:
            return {"status": "error", "error": "asset_hash is required"}
        asset_store = get_asset_store(project_path)
        asset = asset_store.get(asset_hash)
        if asset is None:
            return {"status": "error", "error": f"asset {asset_hash} not found"}
        if not asset.alignment:
            return {"status": "error", "error": "asset has no word-level alignment"}
        from open_edit.agent.skills.narrative_analyzer import analyze
        segments = analyze(asset, use_llm=args.get("use_llm", False))
        return {"status": "ok", "segments": [s.model_dump() for s in segments]}
    except Exception as e:
        return {"status": "error", "error": str(e)}
