"""Kernel-side overlay render trigger.

This module hosts the ``trigger_render`` tool implementation that the
serve layer previously kept in ``serve.pi_bridge``. It was moved here
so kernel no longer lazily imports ``serve`` (the last kernel→serve
dependency, see ``kernel/render_jobs.py``).

The composited HTML-overlay pipeline (``open_edit.render.html_overlay``)
is a pure HTML/ffmpeg compositor with no serve state, so it lives in
``open_edit/render`` and is imported from here without violating the
layering invariant.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from open_edit.kernel.schema_validator import validate_or_error
from open_edit.kernel.tool_result import build_failure_tool_result
from open_edit.render import html_overlay
from open_edit.render.env import RENDER_TIMEOUT_S, get_overlay_config

_LOG = logging.getLogger("open_edit.kernel.render_overlay")


def _probe_duration(mp4_path: Path) -> float:
    """Return the duration in seconds of ``mp4_path`` using ffprobe.

    Raises ``RuntimeError`` if no video stream is found or ffprobe fails.
    """
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(mp4_path),
        ],
        capture_output=True, text=True, check=False, shell=False, timeout=30,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(f"no video stream in {mp4_path}")
    try:
        return float(proc.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"ffprobe returned non-numeric duration: {proc.stdout!r}") from exc


def make_should_cancel():
    """Return a cancellation predicate for the composited render pipeline.

    The pi bridge runs as a short-lived subprocess, so there is no
    long-running WebSocket to poll. The returned predicate always returns
    False.
    """
    return lambda: False


def _read_mlt_profile(project_path: Path) -> dict[str, Any]:
    """Read the project's render profile (width/height/fps/duration_sec).

    Falls back to 1080p30 defaults when the edit graph is missing or empty.
    """
    from open_edit.ir.derive import derive_timeline
    from open_edit.ir.types import Project
    from open_edit.storage.edit_graph import EditGraphStore

    db = project_path / ".open_edit" / "edit_graph.db"
    if db.is_file():
        store = EditGraphStore(db)
        ops = store.load_all()
        applied_ops = [op for op in ops if op.status == "applied"]
        if applied_ops:
            project = Project(name=project_path.name)
            project.edit_graph = applied_ops
            timeline = derive_timeline(project)
            return {
                "width": 1920,
                "height": 1080,
                "fps": 30,
                "duration_sec": timeline.duration_sec,
            }
    return {"width": 1920, "height": 1080, "fps": 30, "duration_sec": 0.0}


def _should_use_composited(args: dict, project_path: Path, render_spec: dict) -> bool:
    """Decide whether the composited HTML-overlay path is the right one.

    True iff the user asked for mode=='overlay' AND the project has at
    least one HtmlOverlay in its timeline. Otherwise return False and
    use the v1.5 bare-MLT path.
    """
    if (args.get("mode") or "").lower() != "overlay":
        return False
    try:
        timeline = _load_timeline(project_path)
        return bool(timeline.overlays)
    except Exception:
        return False


def _load_timeline(project_path: Path):
    """Load the Timeline from the project's edit graph; returns an empty
    Timeline if the project has no overlays."""
    from open_edit.ir.derive import derive_timeline
    from open_edit.ir.types import Project, Timeline
    from open_edit.storage.edit_graph import EditGraphStore

    db = project_path / ".open_edit" / "edit_graph.db"
    if not db.is_file():
        return Timeline(overlays=[])
    store = EditGraphStore(db)
    ops = store.load_all()
    applied_ops = [op for op in ops if op.status == "applied"]
    if not applied_ops:
        return Timeline(overlays=[])
    project = Project(name=project_path.name)
    project.edit_graph = applied_ops
    timeline = derive_timeline(project)
    return timeline


def _build_render_spec(project_path: Path, mode: str, hyperframes_timeout: int) -> dict:
    """Build the RenderSpec TypedDict for one render."""
    overlay_cfg = get_overlay_config()
    profile = _read_mlt_profile(project_path)
    # ``overlay_cfg["hyperframes_bin"]`` is ``None`` when the env var is
    # unset (see render.env.get_overlay_config); the ``or`` short-circuit
    # falls back to the runtime resolver in that case. The contract is
    # the same as for the previous ``""`` sentinel: any falsy value
    # triggers the auto-resolve. The resolver honours env > pinned > npx.
    return {
        "width": profile["width"],
        "height": profile["height"],
        "fps": profile["fps"],
        "duration_sec": profile["duration_sec"],
        "mode": mode,
        "hyperframes_bin": overlay_cfg["hyperframes_bin"] or html_overlay._resolve_hyperframes_bin(),
        "hyperframes_timeout_s": overlay_cfg["hyperframes_timeout_s"],
        "tmpdir": (Path(overlay_cfg["overlay_tmpdir"]) if overlay_cfg["overlay_tmpdir"]
                   else project_path / ".open_edit" / "tmp" / "overlay"),
    }


def _run_mlt_only_render(args: dict[str, Any], project_path: Path) -> dict[str, Any]:
    """Existing v1.5 bare-MLT render path.

    Shells out to ``open_edit render`` and returns the structured result.
    The ``render_spec`` argument was dropped in v1.6 — the MLT path
    does not need overlay rendering parameters.
    """
    mode = (args.get("mode") or "proxy").lower()
    if mode not in ("proxy", "final"):
        mode = "proxy"
    render_id = f"render_{os.urandom(6).hex()}"

    try:
        proc = subprocess.run(
            ["open_edit", "render", "--mode", mode],
            cwd=str(project_path),
            check=False,
            capture_output=True,
            text=True,
            timeout=RENDER_TIMEOUT_S,
            shell=False,
        )
    except FileNotFoundError:
        return build_failure_tool_result("render_failed", render_id, detail="`open_edit` CLI not found on PATH.")
    except subprocess.TimeoutExpired as exc:
        return build_failure_tool_result("timeout", render_id, detail=f"after {exc.timeout}s")

    if proc.returncode != 0:
        return build_failure_tool_result(
            "render_failed", render_id,
            detail=f"exit {proc.returncode}: {proc.stderr.strip() or proc.stdout.strip()}",
        )

    last_line = ""
    for line in reversed(proc.stdout.splitlines()):
        if line.strip():
            last_line = line.strip()
            break
    output_path = last_line if (last_line and ("/" in last_line or "\\" in last_line)) else ""
    if not output_path:
        renders_dir = project_path / ".open_edit" / "renders"
        if renders_dir.exists():
            mp4s = sorted(renders_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
            if mp4s:
                output_path = str(mp4s[0])

    if not output_path:
        return build_failure_tool_result("empty_render", render_id)

    p = Path(output_path)
    if not p.exists() or p.stat().st_size == 0:
        return build_failure_tool_result("empty_render", render_id, path=output_path)

    try:
        duration_s = _probe_duration(p)
    except RuntimeError as exc:
        return build_failure_tool_result("no_video_stream", render_id, detail=str(exc))

    return {
        "output_path": output_path,
        "mode": mode,
        "duration_s": duration_s,
        "render_id": render_id,
    }


def run_trigger_render(args: dict[str, Any], project_path: Path) -> dict[str, Any]:
    """Server-side virtual tool: shell out to ``open_edit render``.

    v1.6: when args['mode'] == 'overlay' AND the project has overlays,
    run the composited pipeline (bg + hyperframes + ffmpeg). Otherwise
    the existing v1.5 path runs unchanged.

    When invoked from the in-process agent loop (a running event loop),
    we can't call ``asyncio.run`` directly; the bug it would raise is
    ``RuntimeError: asyncio.run() cannot be called from a running
    event loop``. We detect the running loop and dispatch the coroutine
    to a worker thread so it blocks waiting for its result.
    """
    err = validate_or_error("trigger_render", args)
    if err is not None:
        return err

    mode = (args.get("mode") or "proxy").lower()
    if mode not in ("proxy", "final", "overlay"):
        mode = "proxy"
    render_spec = _build_render_spec(project_path, mode, get_overlay_config()["hyperframes_timeout_s"])
    if _should_use_composited(args, project_path, render_spec):
        coro = html_overlay.render_composited(
            timeline=_load_timeline(project_path),
            project_workdir=project_path,
            render_spec=render_spec,
            bg_renderer=lambda: _run_mlt_only_render({"mode": mode}, project_path)["output_path"],
            should_cancel=make_should_cancel(),
        )
        try:
            asyncio.get_running_loop()
            in_loop = True
        except RuntimeError:
            in_loop = False
        try:
            if in_loop:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    result_path = ex.submit(asyncio.run, coro).result()
            else:
                result_path = asyncio.run(coro)
        except html_overlay.OverlayRenderError as exc:
            _LOG.warning(
                "overlay render failed, returning %s: %s",
                "MLT bg" if exc.bg_path else "fallback MLT",
                exc,
            )
            if exc.bg_path:
                return {
                    "output_path": str(exc.bg_path),
                    "mode": mode,
                    "duration_s": 0.0,
                    "render_id": "render_overlay_fallback",
                }
            return build_failure_tool_result(
                "overlay_render_failed", "render_overlay_fallback",
                detail=str(exc),
            )
        return {
            "output_path": str(result_path),
            "mode": mode,
            "duration_s": 0.0,
            "render_id": f"render_{os.urandom(6).hex()}",
        }
    return _run_mlt_only_render(args, project_path)
