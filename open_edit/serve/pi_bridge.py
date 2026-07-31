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
import sys
import traceback
from pathlib import Path
from typing import Any

from open_edit.serve.result_capper import cap_tool_result
from open_edit.kernel.render_overlay import run_trigger_render
from open_edit.kernel.schema_validator import validate_or_error


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
    #
    # The 4 pillar tools (``query_project``, ``edit_project``,
    # ``run_script``, ``trigger_render``) have Pydantic-generated
    # schemas with ``additionalProperties: false`` that do NOT list
    # ``project_id``. Injecting it at the top level would fail schema
    # validation. ``query_project`` / ``edit_project`` dispatches
    # ignore ``project_id`` entirely; ``run_script`` derives it from
    # ``project_path`` inside ``run_python``; ``trigger_render`` is
    # handled by a separate code path below.
    if tool_name not in ("search_assets", "query_project", "edit_project", "run_script"):
        db_path = project_path / ".open_edit" / "edit_graph.db"
        if db_path.exists() and "project_id" not in args:
            try:
                args = {**args, "project_id": EditGraphStore(db_path).project_id}
            except Exception as exc:
                raise RuntimeError(
                    f"failed to inject project_id from {db_path}: {exc}"
                ) from exc

    # Validate AFTER project_id injection so injected fields don't fail
    # schema required-field checks (e.g. add_marker requires project_id
    # but the bridge auto-injects it).
    err = validate_or_error(tool_name, args)
    if err is not None:
        return err

    # Pillar tool routing (Plan D).
    if tool_name == "query_project":
        from open_edit.kernel.pillar_tools import dispatch_query

        return dispatch_query(args.get("query", ""), args.get("params", {}), project_path)

    if tool_name == "edit_project":
        from open_edit.kernel.pillar_tools import dispatch_edit, dispatch_generate

        generate = args.get("generate")
        if generate:
            return dispatch_generate(generate, args.get("generate_params", {}), project_path)
        return dispatch_edit(args.get("operation", ""), args.get("params", {}), project_path)

    fn = getattr(tools_mod, tool_name, None)
    if fn is None or not callable(fn):
        raise RuntimeError(f"tool not found in open_edit.agent.tools: {tool_name!r}")
    result = fn(args, str(project_path))
    return cap_tool_result(result)


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
        from open_edit.kernel.tool_schemas import TOOL_SCHEMAS
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
            result = run_trigger_render(tool_args, project_path)
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
