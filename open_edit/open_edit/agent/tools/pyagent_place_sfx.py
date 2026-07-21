"""pyagent_place_sfx: returns SFX placement ops at beat transitions.

Per phase4-design-revised.md section 4.5 (W6): the agent calls this tool to
place sound effects at narrative beat transitions, with optional
synchronization to music downbeats. The tool returns AddEffectOps targeting
the conventional 'audio_sfx' track with effect_type='sfx'.
"""
from __future__ import annotations

import json
from pathlib import Path

from open_edit.agent.tools._helpers import get_asset_store


def place_sfx(args: dict, project_path: str) -> dict:
    """Return SFX AddEffectOps for `args['asset_hash']`.

    Args:
        args: {
            "asset_hash": str,
            "library_path": str (optional, path to JSON SFX library file),
            "music_downbeats": list[float] (optional, defaults to [])
        }
        project_path: path to the project directory (or .kdenlive file).

    Returns:
        {"status": "ok", "ops": [AddEffectOp.model_dump(), ...]}
        or {"status": "error", "error": "..."} on failure.
    """
    asset_store = get_asset_store(project_path)
    asset = asset_store.get(args["asset_hash"])
    if asset is None:
        return {"status": "error", "error": f"asset {args['asset_hash']} not found"}
    from open_edit.agent.skills.narrative_analyzer import analyze
    from open_edit.agent.skills.sfx_placer import place
    segments = analyze(asset, use_llm=False)
    library = _load_sfx_library(args.get("library_path"))
    ops = place(segments, music_downbeats=args.get("music_downbeats", []), library=library)
    return {"status": "ok", "ops": [op.model_dump() for op in ops]}


def _load_sfx_library(path: str | None) -> list[SfxClip]:
    """Load SFX library from a JSON file; empty list if not provided."""
    if not path:
        return []
    from open_edit.agent.skills.sfx_placer import SfxClip
    data = json.loads(Path(path).read_text())
    return [SfxClip(**s) for s in data]
