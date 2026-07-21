"""Python bridge between the pi extension and ``open_edit.agent.tools``.

The TypeScript pi extension calls this script as a subprocess for every
tool invocation:

    python -m open_edit.serve.pi_bridge \\
        --tool add_marker \\
        --project /home/.../my-project \\
        --args '{"timestamp": 3.2, "text": "tighten this cut"}'

It looks up the named tool in ``open_edit.agent.tools``, invokes it with
the supplied args, and prints the JSON result on stdout. Errors are
printed as JSON ``{"error": "..."}`` on stdout (so the TS extension can
read them as a tool result, not a process failure).

For the special tool ``trigger_render``, we shell out to
``open_edit render`` directly (it's not in ``open_edit.agent.tools``).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

from open_edit.serve import html_overlay  # noqa: E402
from open_edit.serve.serve_env import get_overlay_config  # noqa: E402
from open_edit.serve.visual_verify import build_failure_tool_result

_LOG = logging.getLogger("open_edit.serve.pi_bridge")


def _emit(obj: dict[str, Any]) -> None:
    """Print a JSON object to stdout, flush, exit 0."""
    sys.stdout.write(json.dumps(obj, default=str) + "\n")
    sys.stdout.flush()


def _emit_error(message: str, **extra: Any) -> None:
    """Print a structured error to stdout, exit 0 (so the TS layer sees
    the error in the tool result, not as a process failure)."""
    _emit({"error": message, **extra})


def _resolve_project_path(project: str) -> Path:
    """Convert a project string (id, name, or path) into a Path."""
    p = Path(project).expanduser()
    if p.is_dir():
        return p.resolve()
    # Maybe it's a project id — try to resolve via the projects registry.
    try:
        from open_edit.serve.projects import _resolve_project_by_id
        resolved = _resolve_project_by_id(project)
        if resolved is not None:
            return resolved
    except Exception:
        pass
    raise FileNotFoundError(f"project not found: {project}")


def _run_agent_tool(tool_name: str, args: dict[str, Any], project_path: Path) -> dict[str, Any]:
    """Run one of the real tools in ``open_edit.agent.tools``.

    The real tool functions take ``(args: dict, project_path: str)`` and
    expect ``args`` to contain the project-specific fields the function
    needs (``project_id``, ``asset_hash``, etc.). Some of these can be
    derived from the project path (e.g. ``project_id`` is the UUID stored
    in ``edit_graph.db``). We inject those derivable fields here so the
    TS extension doesn't need to know about them.

    v1.4 P1-1: ``search_assets`` is project-agnostic — the
    ``project_id`` injection is harmless (the tool ignores it) but we
    skip the edit_graph.db lookup for that tool to avoid forcing a
    project to exist for a global search.
    """
    import open_edit.agent.tools as tools_mod
    from open_edit.storage.edit_graph import EditGraphStore

    # ``search_assets`` doesn't write to the project, so we skip the
    # project_id auto-inject for it. The tool ignores ``project_id``
    # anyway; skipping the DB read keeps a global search callable
    # even on a fresh server (before any project has been created).
    if tool_name != "search_assets":
        db_path = project_path / ".open_edit" / "edit_graph.db"
        if db_path.exists() and "project_id" not in args:
            try:
                args = {**args, "project_id": EditGraphStore(db_path).project_id}
            except Exception as exc:
                # Don't silently swallow — surface the failure so the user
                # can see why project_id didn't get injected.
                raise RuntimeError(
                    f"failed to inject project_id from {db_path}: {exc}"
                ) from exc

    fn = getattr(tools_mod, tool_name, None)
    if fn is None or not callable(fn):
        raise RuntimeError(f"tool not found in open_edit.agent.tools: {tool_name!r}")
    return fn(args, str(project_path))


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


def _make_should_cancel():
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
    from open_edit.ir.apply import derive_timeline
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
    from open_edit.ir.apply import derive_timeline
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
            timeout=1800,
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


def _run_trigger_render(args: dict[str, Any], project_path: Path) -> dict[str, Any]:
    """Server-side virtual tool: shell out to ``open_edit render``.

    v1.6: when args['mode'] == 'overlay' AND the project has overlays,
    run the composited pipeline (bg + hyperframes + ffmpeg). Otherwise
    the existing v1.5 path runs unchanged.
    """
    mode = (args.get("mode") or "proxy").lower()
    render_spec = _build_render_spec(project_path, mode, get_overlay_config()["hyperframes_timeout_s"])
    if _should_use_composited(args, project_path, render_spec):
        try:
            return asyncio.run(html_overlay.render_composited(
                timeline=_load_timeline(project_path),
                project_workdir=project_path,
                render_spec=render_spec,
                bg_renderer=lambda: _run_mlt_only_render({"mode": mode}, project_path)["output_path"],
                should_cancel=_make_should_cancel(),
            ))
        except html_overlay.OverlayRenderError as exc:
            _LOG.warning(
                "overlay render failed, returning %s: %s",
                "MLT bg" if exc.bg_path else "fallback MLT",
                exc,
            )
            if exc.bg_path:
                return {"output_path": str(exc.bg_path), "mode": mode, "duration_s": 0.0, "render_id": "render_overlay_fallback"}
            return _run_mlt_only_render(args, project_path)
    return _run_mlt_only_render(args, project_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="open_edit.serve.pi_bridge",
        description="Bridge between the pi extension and open_edit.agent.tools.",
    )
    parser.add_argument("--tool", help="Tool name to invoke")
    parser.add_argument(
        "--project",
        help="Project id, name, or path. The tool will operate on this project.",
    )
    parser.add_argument(
        "--args",
        default="{}",
        help="JSON object of tool arguments (default: {})",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="Print the list of available tool names as JSON, then exit.",
    )
    args = parser.parse_args(argv)

    if args.list_tools:
        from open_edit.serve.tool_schemas import TOOL_SCHEMAS
        _emit({"tools": [t["name"] for t in TOOL_SCHEMAS]})
        return 0

    if not args.tool or not args.project:
        parser.error("--tool and --project are required (unless --list-tools)")

    try:
        tool_args = json.loads(args.args) if args.args else {}
        if not isinstance(tool_args, dict):
            raise ValueError(f"--args must be a JSON object, got {type(tool_args).__name__}")
    except (json.JSONDecodeError, ValueError) as exc:
        _emit_error(f"invalid --args JSON: {exc}")
        return 0

    try:
        project_path = _resolve_project_path(args.project)
    except (FileNotFoundError, KeyError) as exc:
        _emit_error(f"project resolution failed: {exc}")
        return 0

    try:
        if args.tool == "trigger_render":
            result = _run_trigger_render(tool_args, project_path)
        else:
            result = _run_agent_tool(args.tool, tool_args, project_path)
    except Exception as exc:  # noqa: BLE001 — surface anything to the TS layer
        _emit_error(
            f"tool {args.tool!r} failed: {exc}",
            traceback=traceback.format_exc(limit=5),
        )
        return 0

    _emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
