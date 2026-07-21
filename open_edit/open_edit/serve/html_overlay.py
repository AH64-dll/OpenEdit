"""v1.6 HTML overlay compositing.

The composited render is a 4-stage pipeline that runs concurrently where
possible (spec §2):

    trigger_render({mode: "overlay"})
       │
       │  pi_bridge._run_trigger_render checks: overlays?  mode=="overlay"?
       │  → if both: composited path. Otherwise: existing MLT path (v1.5).
       │
       ├─ Stage 1: bg render              ─┐
       │  (existing _run_mlt_only_render)  │  concurrent
       │                                  │
       ├─ Stage 2: composition HTML gen   ─┤
       │  (generate_composition_html)     │
       │                                  │
       ├─ Stage 3: overlay render         ─┘
       │  (hyperframes render → overlay.mov, ProRes 4444)
       │
       └─ Stage 4: ffmpeg composite
            ffmpeg -i bg.mp4 -i overlay.mov
              -filter_complex "[0:v][1:v]overlay=eof_action=pass"
              -map 0:a -map [outv] -c:a copy
            → final.mp4

The v1.5 visual verification loop runs unchanged on `final.mp4`.

Public surface (all 4 functions + 1 exception):

  * :func:`generate_composition_html` — pure HTML generator
  * :func:`render_overlay_layer` — subprocess wrapper for hyperframes
  * :func:`composite_with_background` — subprocess wrapper for ffmpeg
  * :func:`render_composited` — async orchestrator
  * :exc:`OverlayRenderError` — raised on any failure (carries `bg_path`)

This module has zero new Python dependencies (stdlib only). The only
new binary dependency is `hyperframes@0.7.65` pinned in `package.json`.
"""
from __future__ import annotations

import html
import logging
import os
import re
from pathlib import Path
from typing import Any

from open_edit.ir.types import HtmlOverlay, Timeline  # noqa: F401  (re-exported)

_LOG = logging.getLogger("open_edit.serve.html_overlay")


class OverlayRenderError(Exception):
    """Raised when the composited render fails.

    Carries ``bg_path`` when the bg render succeeded but a downstream step
    failed — lets ``pi_bridge``'s fallback reuse the completed bg without
    re-running the MLT encode (the bg encode is the slow part).
    """

    def __init__(self, message: str, bg_path: Path | None = None) -> None:
        super().__init__(message)
        self.bg_path = bg_path


def _resolve_hyperframes_bin() -> str:
    """Return the path to the hyperframes binary.

    Order of resolution (spec §5):
      1. ``OPEN_EDIT_HYPERFRAMES_BIN`` env var, if set — used verbatim.
      2. ``node_modules/.bin/hyperframes`` if it exists (set up by
         ``npm install`` at the repo root).
      3. Bare ``npx hyperframes`` (network resolution + version-drift risk;
         a WARNING is logged so the operator notices).

    Never raises.
    """
    env_bin = os.environ.get("OPEN_EDIT_HYPERFRAMES_BIN", "").strip()
    if env_bin:
        return env_bin
    pinned = Path("node_modules/.bin/hyperframes")
    if pinned.is_file():
        return str(pinned.resolve())
    _LOG.warning(
        "hyperframes pinned binary not found at %s; falling back to npx hyperframes "
        "(network resolution + version drift risk). Run npm install at repo root.",
        pinned,
    )
    return "npx hyperframes"


# ---------------------------------------------------------------------------
# HTML composition generator (spec §4)
# ---------------------------------------------------------------------------

# Whitelist of variable types we inline at HTML-generation time. Non-primitive
# values raise OverlayRenderError in v1.6 (no JSON-blob support).
_PRIMITIVE_TYPES = (str, int, float, bool)


def _inline_variables(template_html: str, variables: dict[str, Any]) -> str:
    """Replace {{key}} placeholders in template_html with html.escape()'d values.

    Non-primitive values (dicts, lists, None) raise OverlayRenderError.
    Missing keys are left literal (logged at WARNING level).
    """
    def replace(match: re.Match) -> str:
        key = match.group(1).strip()
        if key not in variables:
            _LOG.warning("template references missing variable: %s", key)
            return match.group(0)
        value = variables[key]
        if not isinstance(value, _PRIMITIVE_TYPES):
            raise OverlayRenderError(
                f"non-primitive variable not supported in v1.6: key={key!r} type={type(value).__name__}"
            )
        return html.escape(str(value), quote=True)

    return re.sub(r"\{\{\s*([a-zA-Z_][\w\.]*)\s*\}\}", replace, template_html)


def _resolve_template_path(template_path: str, project_workdir: Path) -> Path:
    """Resolve a template path; reject absolute, parent-traversal, and symlink escapes.

    Lookup order: project_workdir/<template_path>, then built-in templates.
    Returns the resolved Path. Raises OverlayRenderError on rejection or not-found.
    """
    candidate_path = Path(template_path)
    if candidate_path.is_absolute():
        raise OverlayRenderError(f"absolute template_path not allowed: {template_path}")
    if any(part == ".." for part in candidate_path.parts):
        raise OverlayRenderError(f"template_path with .. not allowed: {template_path}")

    project_root = project_workdir.resolve()
    project_candidate = (project_workdir / template_path).resolve()
    if project_candidate.is_file():
        if not project_candidate.is_relative_to(project_root):
            raise OverlayRenderError(
                f"template_path escapes project dir via symlink: {template_path}"
            )
        return project_candidate

    builtin_root = (Path(__file__).parent / "templates" / "overlay").resolve()
    builtin_candidate = (builtin_root / template_path).resolve()
    if builtin_candidate.is_file():
        if not builtin_candidate.is_relative_to(builtin_root):
            raise OverlayRenderError(
                f"template_path escapes builtin dir via symlink: {template_path}"
            )
        return builtin_candidate

    raise OverlayRenderError(f"template_not_found: {template_path}")


def _assign_tracks(overlays: list[HtmlOverlay]) -> list[tuple[HtmlOverlay, int]]:
    """Greedy non-overlapping track assignment.

    Sort by position_sec. For each overlay, find the lowest track index whose
    last overlay has already ended; if none exists, allocate a new track.
    """
    sorted_overlays = sorted(overlays, key=lambda o: (o.position_sec, o.id))
    track_end: list[float] = []  # track_end[i] = end time of the last overlay on track i
    result: list[tuple[HtmlOverlay, int]] = []
    for overlay in sorted_overlays:
        assigned = False
        for i, end in enumerate(track_end):
            if end <= overlay.position_sec:
                track_end[i] = overlay.position_sec + overlay.duration_sec
                result.append((overlay, i))
                assigned = True
                break
        if not assigned:
            track_end.append(overlay.position_sec + overlay.duration_sec)
            result.append((overlay, len(track_end) - 1))
    return result


def _clip_id(overlay: HtmlOverlay) -> str:
    """Return a stable clip <div> id derived from overlay.id."""
    return f"overlay_{overlay.id}"


def generate_composition_html(
    timeline: Timeline,
    project_workdir: Path,
    render_spec: dict,
) -> str:
    """Generate the HyperFrames composition HTML for a Timeline's overlays.

    No subprocess is spawned. Template files are read from disk. Returns a
    string ready to be written to <tmpdir>/compositions/overlay.html.

    Raises OverlayRenderError on:
      * template path validation failure (absolute, .., symlink escape, not found)
      * non-primitive variable in any overlay
    """
    overlays = list(timeline.overlays)

    width = int(render_spec["width"])
    height = int(render_spec["height"])
    fps = int(render_spec["fps"])
    total_duration = float(render_spec["duration_sec"])

    track_assignment = _assign_tracks(overlays)

    clip_divs: list[str] = []
    for overlay, track_idx in track_assignment:
        template_path = _resolve_template_path(overlay.template_path, project_workdir)
        template_html = template_path.read_text(encoding="utf-8")
        inlined = _inline_variables(template_html, overlay.variables)
        clip_id = _clip_id(overlay)
        clip_divs.append(
            f'    <div class="clip" id="{clip_id}" '
            f'data-start="{overlay.position_sec}" '
            f'data-duration="{overlay.duration_sec}" '
            f'data-track-index="{track_idx}">\n'
            f'      {inlined.strip()}\n'
            f'    </div>'
        )

    clips_block = "\n".join(clip_divs) if clip_divs else ""
    return (
        f'<!DOCTYPE html>\n'
        f'<html lang="en">\n'
        f'<head>\n'
        f'  <meta charset="UTF-8">\n'
        f'  <meta name="viewport" content="width={width}, height={height}">\n'
        f'  <title>open_edit_overlay</title>\n'
        f'  <style>\n'
        f'    html, body, [data-composition-id] {{ margin: 0; padding: 0; background: transparent; }}\n'
        f'    html, body {{ width: {width}px; height: {height}px; overflow: hidden; }}\n'
        f'    .clip {{ position: absolute; inset: 0; }}\n'
        f'  </style>\n'
        f'</head>\n'
        f'<body>\n'
        f'  <div id="root"\n'
        f'       data-composition-id="open_edit_overlay"\n'
        f'       data-start="0"\n'
        f'       data-duration="{total_duration}"\n'
        f'       data-width="{width}"\n'
        f'       data-height="{height}"\n'
        f'       data-fps="{fps}"\n'
        f'       data-no-timeline>\n'
        f'{clips_block}\n'
        f'  </div>\n'
        f'</body>\n'
        f'</html>\n'
    )


__all__ = [
    "OverlayRenderError",
    "_resolve_hyperframes_bin",
    "generate_composition_html",
]
