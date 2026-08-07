"""pyagent_get_silence_gaps: structured silence + filler spans for an asset.

Video-use merge: exposes the transcript-derived cut candidates as DATA
(silence tiers + filler-word spans) so editing agents — including non-vision
models — can reason about cuts without watching the video. This is the
structured counterpart of the packed-transcript reading view.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from open_edit.agent.skills.silence_cutter import (
    find_filler_spans,
    find_silence_gaps,
)
from open_edit.agent.tools._contract import get_asset_or_error, require_alignment, tool_result


@tool_result
def get_silence_gaps(args: dict, project_path: str | Path) -> dict[str, Any]:
    """Return structured silence gaps (and optional filler spans) for an asset.

    Args:
        args: {"asset_hash": str,
               "threshold_ms": int (optional, default 400),
               "min_segment_s": float (optional, default 2.0),
               "keep_breath_ms": int (optional, default 600),
               "include_fillers": bool (optional, default true)}
        project_path: path to the project directory.

    Returns:
        {"status": "ok", "asset_hash", "duration_sec",
         "gaps": [{"t_start","t_end","kind"}],
         "fillers": [{"t_start","t_end","text"}]}
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

    threshold_ms = int(args.get("threshold_ms", 400))
    min_segment_s = float(args.get("min_segment_s", 2.0))
    keep_breath_ms = int(args.get("keep_breath_ms", 600))
    include_fillers = bool(args.get("include_fillers", True))

    gaps = find_silence_gaps(
        asset.alignment,
        threshold_ms=threshold_ms,
        duration=getattr(asset, "duration_sec", None),
        min_segment_s=min_segment_s,
        keep_breath_ms=keep_breath_ms,
    )
    fillers: list[dict[str, Any]] = []
    if include_fillers:
        for fs, fe in find_filler_spans(asset.alignment, include_contextual=True):
            words = [w.word for w in asset.alignment
                     if w.t_start >= fs - 0.05 and w.t_end <= fe + 0.05]
            fillers.append({"t_start": round(fs, 3), "t_end": round(fe, 3),
                            "text": " ".join(words)})

    return {
        "status": "ok",
        "asset_hash": asset_hash,
        "duration_sec": getattr(asset, "duration_sec", None),
        "gaps": [
            {"t_start": round(g0, 3), "t_end": round(g1, 3), "kind": "silence"}
            for g0, g1 in gaps
        ],
        "fillers": fillers,
    }
