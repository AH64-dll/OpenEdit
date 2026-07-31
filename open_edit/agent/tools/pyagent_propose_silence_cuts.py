"""pyagent_propose_silence_cuts: returns inter-word silence gaps as cut suggestions.

Per phase4-design-revised.md section 4.2 (W3): the agent calls this tool to
find silence gaps in an asset's word-level alignment. The tool returns
gap suggestions; the agent decides whether to apply them as IR ops.

With ``compress: true`` the tool also runs the proposed gaps through
``render.silence_compress.compress_silence`` (stream-copy ffconcat trim),
ingests the result as a new CAS asset, and returns its hash so the agent
can swap it in as the clip source.
"""
from __future__ import annotations

from pathlib import Path

from open_edit.agent.tools._contract import get_asset_or_error, require_alignment, tool_result
from open_edit.agent.tools._helpers import get_asset_store


@tool_result
def propose_silence_cuts(args: dict, project_path: str) -> dict:
    """Return silence-cut suggestions for ``args['asset_hash']``.

    Args:
        args: {
            "asset_hash": str (required),
            "threshold_ms": int (optional, default 400),
            "min_segment_s": float (optional, default 2.0; merge gaps
                separated by shorter speech — protects sub-2s fragments),
            "compress": bool (optional, default false; when true, trim the
                proposed gaps from the asset via compress_silence, ingest
                the result as a new asset, and return its hash in
                ``compressed_asset_hash`` alongside ``gaps``)
        }
        project_path: path to the project directory (or .kdenlive file).

    Returns:
        ``{"status": "ok", "gaps": [...]}`` on success (with
        ``compressed_asset_hash`` and ``compression`` stats added when
        ``compress`` is true and the output differs from the source),
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
        min_segment_s=args.get("min_segment_s", 2.0),
        keep_breath_ms=args.get("keep_breath_ms", 600),
    )
    result = {"status": "ok", "gaps": gaps}
    if not args.get("compress"):
        return result

    from open_edit.render.silence_compress import compress_silence

    store = get_asset_store(project_path)
    tmp_dir = store.assets_dir.parent / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(asset.stored_path).suffix or ".mp4"
    output_path = tmp_dir / f"silence-compress-{asset_hash}{suffix}"
    try:
        stats = compress_silence(
            asset.stored_path,
            output_path,
            gaps=[(g["t_start"], g["t_end"]) for g in gaps],
        )
        if stats.get("changed"):
            new_asset = store.ingest(str(output_path))
            result["compressed_asset_hash"] = new_asset.asset_hash
    finally:
        output_path.unlink(missing_ok=True)
    result["compression"] = stats
    return result
