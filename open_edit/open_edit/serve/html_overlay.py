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

import asyncio
import html
import logging
import os
import re
import shlex
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

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


# ---------------------------------------------------------------------------
# Subprocess wrappers (spec §5)
# ---------------------------------------------------------------------------


def _run_subprocess_with_cancel(
    cmd: list[str],
    output_path: Path,
    timeout_s: int,
    should_cancel: Callable[[], bool] | None,
    operation: str,
    binary_label: str,
    timeout_label: str,
    nonzero_label: str,
    cwd: str | os.PathLike[str] | None = None,
) -> Path:
    """Run ``cmd`` via :class:`subprocess.Popen` with cancellation support.

    Polls ``should_cancel`` before launching the child.  While the child is
    running a watcher thread checks ``should_cancel`` every 100 ms and kills
    the process if it returns ``True``.  On success, verifies that
    ``output_path`` exists and is non-empty.

    Raises ``OverlayRenderError`` on cancellation, missing binary, timeout,
    non-zero exit, or missing/empty output.
    """
    if should_cancel and should_cancel():
        raise OverlayRenderError(f"cancelled before {operation}")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
            cwd=cwd,
        )
    except FileNotFoundError as exc:
        raise OverlayRenderError(f"{binary_label} binary not found: {exc}") from exc

    cancelled = threading.Event()

    def _cancel_watcher() -> None:
        while not cancelled.is_set():
            if proc.poll() is not None:
                break
            if should_cancel and should_cancel():
                cancelled.set()
                try:
                    proc.kill()
                except OSError:
                    pass
                break
            time.sleep(0.1)

    watcher = threading.Thread(target=_cancel_watcher, daemon=True)
    watcher.start()

    try:
        stdout, stderr = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            pass
        cancelled.set()
        raise OverlayRenderError(f"{timeout_label} after {timeout_s}s")
    finally:
        watcher.join(timeout=2.0)

    if cancelled.is_set():
        raise OverlayRenderError(f"cancelled during {operation}")

    if should_cancel and should_cancel():
        raise OverlayRenderError(f"cancelled during {operation}")

    if proc.returncode != 0:
        raise OverlayRenderError(
            f"{nonzero_label} ({proc.returncode}): stderr={stderr.strip()[:500]}"
        )

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise OverlayRenderError(
            f"{operation} succeeded but output file is missing or empty: {output_path}"
        )

    return output_path


def _estimate_overlay_size_mb(timeline: Timeline) -> int:
    """Estimate the overlay.mov size in MB.

    Rough heuristic per spec §5: 1 MB/s for static content (measured in
    spec §16 — 2.0s @ 1920x1080 of static content = 2.1 MB). For
    full-motion content this is a significant underestimate (~30 MB/s);
    the preflight is intentionally biased toward false-negatives on
    full-motion (we'd rather render and find out than false-positive
    block a 5-minute static title card).
    """
    total_seconds = sum(o.duration_sec for o in timeline.overlays)
    return int(round(total_seconds * 1.0))  # 1 MB/s


def _disk_footprint_check(estimated_mb: int, tmpdir: Path) -> None:
    """Log a WARNING if the estimate is large; raise OverlayRenderError if too large.

    Thresholds from spec §5: soft warn at 500 MB, hard cap at 2 GB.
    """
    if estimated_mb > 2048:
        raise OverlayRenderError(
            f"overlay_render_too_large: ~{estimated_mb} MB exceeds 2048 MB cap. "
            f"Shorten the overlay duration or render in segments."
        )
    if estimated_mb > 500:
        _LOG.warning(
            "overlay estimated ~%d MB; tmpdir=%s. This may take a while and use significant disk.",
            estimated_mb, tmpdir,
        )


def render_overlay_layer(
    comp_html_path: Path,
    output_path: Path,
    render_spec: dict,
    should_cancel: Callable[[], bool] | None = None,
) -> Path:
    """Run the hyperframes CLI to render `comp_html_path` to `output_path`.

    Returns the `output_path` on success. Raises `OverlayRenderError` on
    any failure (binary missing, timeout, non-zero exit, missing/empty output).
    Polls `should_cancel` before launching the subprocess and monitors the
    child with a watcher thread; if `should_cancel` returns `True`, the
    child process is killed and `OverlayRenderError` is raised (with no bg_path).
    """
    output_path = output_path.resolve()
    # Build the project tmpdir and mirror the composition HTML into it so
    # the relative -c flag resolves without an absolute path.
    tmp_project_dir = Path(render_spec["tmpdir"])
    tmp_project_dir.mkdir(parents=True, exist_ok=True)
    target_html = tmp_project_dir / "overlay.html"
    try:
        target_html.write_text(
            comp_html_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
    except FileNotFoundError as exc:
        raise OverlayRenderError(f"composition HTML not found: {exc}") from exc

    # Verify CLI syntax (spec §16): positional [DIR], -c <html>, -f <fps>,
    # --format mov, -o <out>, -q standard, --strict.
    bin_argv = shlex.split(render_spec["hyperframes_bin"])
    cmd = bin_argv + [
        "render",
        "-c", "overlay.html",
        "-f", str(int(render_spec["fps"])),
        "--format", "mov",
        "-o", str(output_path),
        "-q", "standard",
        "--strict",
        str(tmp_project_dir.resolve()),
    ]

    _LOG.info("render_overlay_layer: %s", cmd)
    return _run_subprocess_with_cancel(
        cmd,
        output_path=output_path,
        timeout_s=int(render_spec["hyperframes_timeout_s"]),
        should_cancel=should_cancel,
        operation="overlay render",
        binary_label="hyperframes",
        timeout_label="hyperframes timed out",
        nonzero_label="hyperframes non-zero exit",
        cwd=str(tmp_project_dir.resolve()),
    )


def composite_with_background(
    bg_path: Path,
    overlay_path: Path,
    output_path: Path,
    render_spec: dict,
    should_cancel: Callable[[], bool] | None = None,
) -> Path:
    """Composite the overlay MOV over the bg MP4 via ffmpeg.

    Verifies the ffmpeg filter from spec §5: `[0:v][1:v]overlay=eof_action=pass`,
    explicit `-map 0:a -map [outv] -c:a copy` so bg's audio wins and isn't
    re-encoded. Returns the `output_path`. Raises OverlayRenderError on
    any failure (binary missing, timeout, non-zero exit, missing/empty output).
    Polls `should_cancel` before launching the subprocess and monitors the
    child with a watcher thread; if `should_cancel` returns `True`, the
    child process is killed and `OverlayRenderError` is raised (with no bg_path).
    """
    bg_path = bg_path.resolve()
    overlay_path = overlay_path.resolve()
    output_path = output_path.resolve()
    cmd = [
        "ffmpeg", "-y",
        "-i", str(bg_path),
        "-i", str(overlay_path),
        "-filter_complex", "[0:v][1:v]overlay=eof_action=pass",
        "-map", "0:a",
        "-map", "[outv]",
        "-c:a", "copy",
        "-c:v", "libx264",
        str(output_path),
    ]

    _LOG.info("composite_with_background: %s", cmd)
    return _run_subprocess_with_cancel(
        cmd,
        output_path=output_path,
        timeout_s=int(render_spec["hyperframes_timeout_s"]),
        should_cancel=should_cancel,
        operation="ffmpeg composite",
        binary_label="ffmpeg",
        timeout_label="ffmpeg composite timed out",
        nonzero_label="ffmpeg failed",
    )


# ---------------------------------------------------------------------------
# Async orchestrator (spec §6)
# ---------------------------------------------------------------------------


async def render_composited(
    timeline: Timeline,
    project_workdir: Path,
    render_spec: dict,
    bg_renderer: Callable[[], str | Path],
    should_cancel: Callable[[], bool] | None = None,
) -> Path:
    """Concurrent composited-render pipeline.

    Runs the bg render, composition HTML gen, and overlay render concurrently
    where possible. The final ffmpeg composite waits for both the bg and
    overlay to complete.

    Returns the path to the final composited MP4.

    Raises:
        OverlayRenderError on any failure. The exception carries ``bg_path``
        when the bg render succeeded but a downstream step failed — lets
        pi_bridge's fallback return the completed bg without re-encoding.
    """
    tmpdir = Path(render_spec["tmpdir"])
    tmpdir.mkdir(parents=True, exist_ok=True)
    # Composition HTML lives at <tmpdir>/overlay.html — Task 3's
    # render_overlay_layer runs hyperframes with `-c overlay.html`
    # from this directory, so the file must be at the tmpdir root
    # (not in a subdir).
    comp_html_path = tmpdir / "overlay.html"

    bg_path_holder: dict[str, Path | None] = {"path": None}
    success = False

    # Stage 1: bg render (in a thread, via bg_renderer).
    # Poll should_cancel before dispatching so cancellation works
    # even if the bg renderer's call site can't poll internally.
    async def _bg():
        if should_cancel and should_cancel():
            raise OverlayRenderError("cancelled before bg render", bg_path=None)
        bg_result = await asyncio.to_thread(bg_renderer)
        if should_cancel and should_cancel():
            raise OverlayRenderError("cancelled after bg render", bg_path=Path(bg_result) if bg_result else None)
        return bg_result

    # Stage 2: composition HTML generation.
    async def _gen_comp_html():
        return await asyncio.to_thread(generate_composition_html, timeline, project_workdir, render_spec)

    # Stage 3: overlay render (hyperframes subprocess).
    async def _overlay():
        return await asyncio.to_thread(
            render_overlay_layer, comp_html_path, tmpdir / "overlay.mov", render_spec, should_cancel,
        )

    # Stage 4: ffmpeg composite.
    async def _composite(bg_path: Path, overlay_path: Path):
        return await asyncio.to_thread(
            composite_with_background, bg_path, overlay_path, tmpdir / "final.mp4", render_spec, should_cancel,
        )

    try:
        if should_cancel and should_cancel():
            raise OverlayRenderError("cancelled before render", bg_path=None)

        # Pre-flight: disk footprint check (uses timeline, doesn't need a render).
        estimated_mb = _estimate_overlay_size_mb(timeline)
        _disk_footprint_check(estimated_mb, tmpdir)

        # Run bg and composition HTML concurrently. asyncio.TaskGroup
        # auto-cancels in-flight siblings on any exception — critical so a
        # failure in one task (e.g. comp_html) doesn't leave bg_renderer
        # running for up to 30 minutes (its subprocess timeout).
        async with asyncio.TaskGroup() as tg:
            bg_task = tg.create_task(_bg())
            comp_html_task = tg.create_task(_gen_comp_html())
            comp_html = await comp_html_task
            comp_html_path.write_text(comp_html, encoding="utf-8")
            # Start overlay render as soon as the composition HTML is ready.
            overlay_task = tg.create_task(_overlay())
            # Wait for bg.
            bg_path = await bg_task
            bg_path_holder["path"] = bg_path
            # Wait for overlay.
            overlay_path = await overlay_task
            # Final ffmpeg composite.
            if should_cancel and should_cancel():
                raise OverlayRenderError("cancelled before ffmpeg composite", bg_path=bg_path)
            final_path = await asyncio.create_task(
                _composite(bg_path, overlay_path)
            )
        success = True
        return final_path
    except ExceptionGroup as eg:
        # TaskGroup wraps the failure in ExceptionGroup. Extract the first
        # OverlayRenderError and propagate it with bg_path set if known.
        overlay_errors = [e for e in eg.exceptions if isinstance(e, OverlayRenderError)]
        if overlay_errors:
            exc = overlay_errors[0]
            if bg_path_holder["path"] is not None and exc.bg_path is None:
                exc.bg_path = bg_path_holder["path"]
            raise exc from eg
        first = eg.exceptions[0]
        exc = OverlayRenderError(str(first) or type(first).__name__, bg_path=bg_path_holder["path"])
        raise exc from eg
    except Exception as e:
        raise OverlayRenderError(str(e), bg_path=bg_path_holder["path"]) from e
    finally:
        # Always clean up the temp composition HTML and overlay.mov.
        comp_html_path.unlink(missing_ok=True)
        (tmpdir / "overlay.mov").unlink(missing_ok=True)
        # On failure, also unlink partial final.mp4 so it doesn't accumulate
        # in a persistent tmpdir (OPEN_EDIT_OVERLAY_TMPDIR). On success, keep it.
        if not success:
            (tmpdir / "final.mp4").unlink(missing_ok=True)
            # Only unlink bg.mp4 if no bg_path is being propagated to the
            # exception — pi_bridge's fallback reuses the completed bg.
            if bg_path_holder["path"] is None:
                for candidate in (tmpdir / "bg.mp4",):
                    if candidate.exists():
                        candidate.unlink()


__all__ = [
    "OverlayRenderError",
    "_resolve_hyperframes_bin",
    "generate_composition_html",
    "render_overlay_layer",
    "composite_with_background",
    "render_composited",
]
