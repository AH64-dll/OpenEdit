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

import logging
import os
from pathlib import Path

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


__all__ = [
    "OverlayRenderError",
    "_resolve_hyperframes_bin",
]
