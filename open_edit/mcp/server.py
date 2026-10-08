"""stdio MCP entry point for Open Edit.

Usage:
  open-edit-mcp --project /path/to/proj
  open_edit mcp --project /path/to/proj
  OPEN_EDIT_PROJECT=/path/to/proj open-edit-mcp
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from open_edit.mcp.adapters import dispatch_mcp_tool, mcp_tool_schemas, result_to_json
from open_edit.mcp.context import ProjectPathError, resolve_project_path
from open_edit.mcp.skills import (
    MCP_SKILL_STEMS,
    load_skill,
    mcp_instructions,
    resource_uri,
    stem_from_uri,
)


def _require_mcp():
    try:
        import mcp as _mcp_pkg

        mcp_file = Path(getattr(_mcp_pkg, "__file__", "") or "").resolve()
        # Editable installs rooted at open_edit/ put this package on sys.path as
        # top-level ``mcp``, shadowing the real MCP SDK.
        if mcp_file.parent.resolve() == Path(__file__).resolve().parent:
            raise ImportError(
                "import 'mcp' resolved to open_edit.mcp (self-shadow). "
                "Install the MCP SDK (pip install 'mcp>=1.30,<2') with the "
                "editable install rooted at the repo (packages=['open_edit'])."
            )
        from mcp.server import Server
        from mcp.server.lowlevel.helper_types import ReadResourceContents
        from mcp.server.stdio import stdio_server
        from mcp.types import (
            CallToolResult,
            GetPromptResult,
            Prompt,
            PromptMessage,
            Resource,
            TextContent,
            Tool,
        )
    except ImportError as exc:
        raise SystemExit(
            "MCP SDK not installed. From the repo root run:\n"
            '  pip install -e ".[mcp]"\n'
            f"({exc})"
        ) from exc
    return (
        Server,
        stdio_server,
        TextContent,
        Tool,
        Resource,
        ReadResourceContents,
        Prompt,
        GetPromptResult,
        PromptMessage,
        CallToolResult,
    )


def build_server(project_path: Path):
    """Construct an MCP ``server`` bound to ``project_path``."""
    (
        server_class,
        _stdio_server,
        text_content,
        tool,
        resource,
        read_resource_contents,
        prompt,
        get_prompt_result,
        prompt_message,
        call_tool_result,
    ) = _require_mcp()

    server = server_class(
        "open-edit",
        instructions=mcp_instructions(),
    )

    @server.list_tools()
    async def list_tools() -> list[Any]:
        tools: list[Any] = []
        for schema in mcp_tool_schemas():
            tools.append(
                tool(
                    name=schema["name"],
                    description=schema.get("description") or "",
                    inputSchema=schema.get("input_schema") or {"type": "object"},
                )
            )
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict | None) -> Any:
        result = await dispatch_mcp_tool(name, arguments, project_path)
        failed = result.get("ok") is False or result.get("status") in {"error", "retry"} or bool(result.get("error"))
        return call_tool_result(
            content=[text_content(type="text", text=result_to_json(result))],
            isError=failed,
        )

    @server.list_resources()
    async def list_resources() -> list[Any]:
        resources: list[Any] = []
        for stem in MCP_SKILL_STEMS:
            try:
                load_skill(stem)
            except FileNotFoundError:
                continue
            resources.append(
                resource(
                    uri=resource_uri(stem),
                    name=stem,
                    description=f"Open Edit harness skill: {stem}",
                    mimeType="text/markdown",
                )
            )
        return resources

    @server.read_resource()
    async def read_resource(uri: Any) -> list[Any]:
        uri_str = str(uri)
        stem = stem_from_uri(uri_str)
        if stem is None:
            raise ValueError(f"Unknown resource URI: {uri_str}")
        return [
            read_resource_contents(
                content=load_skill(stem),
                mime_type="text/markdown",
            )
        ]

    @server.list_prompts()
    async def list_prompts() -> list[Any]:
        return [
            prompt(
                name="open-edit-playbook",
                description=(
                    "Load the Open Edit MCP playbook (tools, when to use them, "
                    "recipes). Prefer this over exploring source code."
                ),
            ),
            prompt(
                name="open-edit-reference",
                description=(
                    "Load IR / run_script recipes for timeline construction."
                ),
            ),
            prompt(
                name="open-edit-style-memory",
                description=(
                    "Capture and reuse user style preferences "
                    "(get_style_profile, capture_style_hint, pins)."
                ),
            ),
            prompt(
                name="open-edit-review-notes",
                description=(
                    "Read/act on timeline review notes (including audio-targeted "
                    "notes). Prefer get_pending_notes over exploring source."
                ),
            ),
            prompt(
                name="open-edit-tool-surface",
                description=(
                    "4-pillar tool surface reference (query/edit/run_script/render)."
                ),
            ),
            prompt(
                name="open-edit-edit-planning",
                description=(
                    "Edit planning playbook: silence, music, SFX, narrative order."
                ),
            ),
        ]

    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict | None = None) -> Any:
        del arguments  # no prompt args yet
        stem_map = {
            "open-edit-playbook": "open-edit-mcp",
            "open-edit-reference": "open-edit-mcp-reference",
            "open-edit-style-memory": "style-memory",
            "open-edit-review-notes": "review-notes",
            "open-edit-tool-surface": "tool_surface",
            "open-edit-edit-planning": "edit-planning",
        }
        stem = stem_map.get(name)
        if stem is None:
            raise ValueError(f"Unknown prompt: {name}")
        text = load_skill(stem)
        return get_prompt_result(
            description=f"Open Edit skill: {stem}",
            messages=[
                prompt_message(
                    role="user",
                    content=text_content(type="text", text=text),
                )
            ],
        )

    return server


async def run_stdio(project_path: Path) -> None:
    """Serve MCP over stdin/stdout for the pinned project."""
    _server_cls, stdio_server, *_rest = _require_mcp()
    server = build_server(project_path)
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
    finally:
        from open_edit.kernel.render_jobs import DEFAULT_RENDER_JOB_SERVICE
        await DEFAULT_RENDER_JOB_SERVICE.shutdown()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="open-edit-mcp",
        description=(
            "Local stdio MCP server for Open Edit. "
            "Pin a project with --project or OPEN_EDIT_PROJECT."
        ),
    )
    parser.add_argument(
        "--project",
        default=None,
        help="Absolute path to an Open Edit project (contains .open_edit/). "
             "Defaults to OPEN_EDIT_PROJECT.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        project_path = resolve_project_path(args.project)
    except ProjectPathError as exc:
        print(f"open-edit-mcp: {exc}", file=sys.stderr)
        return 2

    try:
        asyncio.run(run_stdio(project_path))
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
