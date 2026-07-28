"""pyagent_analyze_narrative: returns narrative segments for an asset.

Per phase4-design-revised.md section 4.1 (W4): the agent calls this tool
to segment an asset's word-level alignment into narrative beats. The
agent decides how to use the segments (e.g., for motion-graphics
planning or to inform cut boundaries).

The default path is RULE-BASED: segments are sentence-aligned with
positional beat labels (``hook`` / ``turn`` / ``scope`` / ``mechanism``
/ ``button``). The labels are heuristics, not semantic classifications
— use them for cut-boundary hints, not for structural reordering.

``use_llm=True`` is accepted but currently routes to the same rule-based
path with a warning (LLM classification is not implemented).
"""
from __future__ import annotations

from open_edit.agent.tools._helpers import get_asset_store


def analyze_narrative(args: dict, project_path: str) -> dict:
    """Return narrative segments for ``args['asset_hash']``.

    Args:
        args: {
            "asset_hash": str (required),
            "use_llm": bool (optional, default False; currently a no-op
                that routes to the rule-based path with a warning)
        }
        project_path: path to the project directory (or .kdenlive file).

    Returns:
        ``{"status": "ok", "segments": [NarrativeSegment.model_dump(), ...]}``
        on success, or
        ``{"status": "error", "error": "...", "retry": bool}`` on
        failure.

    When the asset has no alignment, the response includes
    ``"retry": True`` and an error message hinting that server-side
    transcription may still be in progress. The agent should wait
    briefly and retry rather than concluding the asset has no
    transcript.

    Each segment has the shape::

        {
          "beat_type": "hook" | "turn" | "scope" | "mechanism" |
                        "cost" | "tease" | "button",
          "t_start": float,
          "t_end": float,
          "text": str,
          "suggested_visual_concept": str,
          "gap_after_s": float | None
        }

    ``gap_after_s`` is the silence (in seconds) between this segment's
    end and the next segment's start. ``None`` on the last segment.
    Segments with a large ``gap_after_s`` are natural cut candidates.
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
                    "and retry before concluding the asset has no "
                    "transcript."
                ),
                "retry": True,
            }

        from open_edit.agent.skills.narrative_analyzer import analyze

        segments = analyze(asset, use_llm=args.get("use_llm", False))
        return {
            "status": "ok",
            "segments": [s.model_dump() for s in segments],
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
