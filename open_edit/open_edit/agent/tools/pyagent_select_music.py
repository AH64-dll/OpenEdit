"""pyagent_select_music: returns music track ops for narrative segments.

Per phase4-design-revised.md section 4.4 (W5): the agent calls this tool to
match narrative segments to mood-appropriate music tracks from a library.
The tool returns AddEffectOps targeting the conventional 'audio_music' track
with effect_type='music_bed'.
"""
from __future__ import annotations

import json
from pathlib import Path

from open_edit.agent.tools._helpers import get_asset_store


def select_music(args: dict, project_path: str) -> dict:
    """Return music-bed AddEffectOps for `args['asset_hash']`.

    Args:
        args: {
            "asset_hash": str,
            "library_path": str (optional, path to JSON music library file)
        }
        project_path: path to the project directory (or .kdenlive file).

    Returns:
        {"status": "ok", "ops": [AddEffectOp.model_dump(), ...]}
        or {"status": "error", "error": "..."} on failure.
    """
    try:
        asset_store = get_asset_store(project_path)
        asset = asset_store.get(args["asset_hash"])
        if asset is None:
            return {"status": "error", "error": f"asset {args['asset_hash']} not found"}
        from open_edit.agent.skills.narrative_analyzer import analyze
        from open_edit.agent.skills.music_selector import select
        segments = analyze(asset, use_llm=False)
        library = _load_music_library(args.get("library_path"))
        ops = select(segments, library)
        return {"status": "ok", "ops": [op.model_dump() for op in ops]}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _load_music_library(path: str | None) -> list[MusicTrack]:  # noqa: F821
    """Load music library from a JSON file; empty list if not provided."""
    if not path:
        return []
    from open_edit.agent.skills.music_selector import MusicTrack
    data = json.loads(Path(path).read_text())
    return [MusicTrack(**t) for t in data]
