"""pyagent_generate_visual_for_segment: render a templated motion graphic.

Per phase4-design-revised.md section 4.3 (W7): the agent picks a beat
(``hook`` / ``turn`` / ``scope`` / ``mechanism`` / ``cost`` / ``tease`` /
``button``) and a template name, calls this tool, and gets back an
``AddClipOp`` referencing a freshly rendered video asset.
"""
from __future__ import annotations

from open_edit.agent.tools._helpers import get_asset_store


def generate_visual_for_segment(args: dict, project_path: str) -> dict:
    """Return an AddClipOp for a templated motion graphic.

    Args:
        args: {
            "asset_hash": str,            # source asset for narrative analysis
            "beat_type": str,             # which beat to render
            "template": str,              # template function name
            "params": dict,               # MotionTemplateParams kwargs
            "project_id": str,            # for tracing
        }
        project_path: path to the project directory (or .kdenlive file).

    Returns:
        {"status": "ok", "op": AddClipOp.model_dump()}
        or {"status": "error", "error": "..."} on failure.
    """
    asset_store = get_asset_store(project_path)
    asset = asset_store.get(args["asset_hash"])
    if asset is None:
        return {"status": "error", "error": f"asset {args['asset_hash']} not found"}
    from open_edit.agent.skills.motion_graphics.engine import generate_visual
    from open_edit.agent.skills.narrative_analyzer import analyze
    segments = analyze(asset, use_llm=False)
    beat_type = args.get("beat_type")
    segment = next((s for s in segments if s.beat_type == beat_type), None)
    if segment is None:
        return {
            "status": "error",
            "error": f"no narrative segment with beat_type {beat_type!r}",
        }
    from pathlib import Path
    workdir = Path(project_path).parent if Path(project_path).is_file() else Path(project_path)
    try:
        op = generate_visual(
            segment=segment,
            template=args["template"],
            params=args.get("params", {}),
            project_id=args["project_id"],
            workdir=workdir,
        )
    except (RuntimeError, FileNotFoundError, ValueError) as e:
        return {"status": "error", "error": str(e)}
    return {"status": "ok", "op": op.model_dump()}
