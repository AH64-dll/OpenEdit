"""pyagent_get_timeline_view: on-demand filmstrip+waveform+words composite PNG.

Video-use merge: the agent edits video by READING it — the packed transcript
for structure, and a timeline_view PNG at decision points (cut sanity,
retake comparison, and self-eval of rendered output at cut boundaries).
Works for the CAS asset (``asset_hash``) or any project-relative media file
(``path``, e.g. ``.open_edit/renders/project_xxx.mp4`` for self-eval of a
render) — no vision model required to make the call; a vision-capable model
(or the user) reads the returned image.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from open_edit.agent.tools._contract import tool_result
from open_edit.render.timeline_view import build_timeline_view


@tool_result
def get_timeline_view(args: dict, project_path: str | Path) -> dict[str, Any]:
    """Render a timeline-view composite PNG for a media file / asset range.

    Args:
        args: {"asset_hash": str} XOR {"path": "project/relative.mp4"},
              "start_sec": float (default 0.0),
              "end_sec": float (default 10.0 or asset duration),
              "n_frames": int (default 10),
              "width": int (default 1920),
              "label": str (optional, header text override)}
        project_path: project root directory.

    Returns:
        {"status": "ok", "image_path": str, "start_sec", "end_sec",
         "legend": str} or a structured error.
    """
    from open_edit.storage.assets import list_assets_from_disk
    from open_edit.storage.paths import ProjectPaths

    project_root = ProjectPaths.for_project(project_path).root

    media_path: Path | None = None
    words: list[Any] | None = None
    duration_hint: float | None = None

    asset_hash = args.get("asset_hash")
    rel_path = args.get("path")
    if asset_hash and rel_path:
        return {"status": "error", "error": "provide exactly one of asset_hash or path"}
    if not asset_hash and not rel_path:
        return {"status": "error", "error": "asset_hash or path is required"}

    if asset_hash:
        for asset in list_assets_from_disk(project_root):
            if asset.asset_hash == asset_hash:
                media_path = Path(asset.stored_path or asset.original_path)
                words = asset.alignment
                duration_hint = getattr(asset, "duration_sec", None)
                break
        if media_path is None:
            return {"status": "error", "error": f"asset not found: {asset_hash}"}
    else:
        candidate = (project_root / str(rel_path)).resolve()
        if not candidate.is_relative_to(project_root.resolve()):
            return {"status": "error", "error": "path escapes project"}
        if not candidate.is_file():
            return {"status": "error", "error": f"media file not found: {rel_path}"}
        media_path = candidate

    try:
        start_sec = float(args.get("start_sec", 0.0))
        end_sec = float(args.get("end_sec", duration_hint or 10.0))
    except (TypeError, ValueError):
        return {"status": "error", "error": "start_sec/end_sec must be numbers"}
    if start_sec < 0 or end_sec <= start_sec:
        return {"status": "error", "error": "end_sec must be > start_sec >= 0"}
    n_frames = int(args.get("n_frames", 10))
    width = int(args.get("width", 1920))
    if not (2 <= n_frames <= 20):
        return {"status": "error", "error": "n_frames must be in [2, 20]"}
    if not (640 <= width <= 4096):
        return {"status": "error", "error": "width must be in [640, 4096]"}

    out_dir = project_root / ".open_edit" / "timeline_views"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = (asset_hash or Path(str(rel_path)).stem).replace("/", "_")[:40]
    out_path = out_dir / f"{stem}_{start_sec:.2f}-{end_sec:.2f}.png"

    try:
        build_timeline_view(
            media_path, start_sec, end_sec,
            words=words, n_frames=n_frames, width=width, out_path=out_path,
        )
    except Exception as exc:  # ffmpeg/PIL failures -> structured retry
        return {"status": "retry", "error": f"timeline view render failed: {exc}"}

    return {
        "status": "ok",
        "image_path": str(out_path),
        "start_sec": start_sec,
        "end_sec": end_sec,
        "n_frames": n_frames,
        "legend": "shaded bands = silences >= 400ms; labels = word boundaries",
    }
