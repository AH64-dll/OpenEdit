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
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any


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


def _run_trigger_render(args: dict[str, Any], project_path: Path) -> dict[str, Any]:
    """Server-side virtual tool: shell out to ``open_edit render``."""
    mode = (args.get("mode") or "proxy").lower()
    if mode not in ("proxy", "final"):
        mode = "proxy"

    try:
        proc = subprocess.run(
            ["open_edit", "render", "--mode", mode],
            cwd=str(project_path),
            check=True,
            capture_output=True,
            text=True,
            timeout=1800,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("`open_edit` CLI not found on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"`open_edit render --mode {mode}` failed (exit {exc.returncode}): "
            f"{exc.stderr.strip() or exc.stdout.strip()}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"render timed out after {exc.timeout}s") from exc

    # The CLI prints the output path on the last non-empty line of stdout.
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

    return {
        "mode": mode,
        "output_path": output_path,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


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
