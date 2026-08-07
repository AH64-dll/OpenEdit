"""Drive OpenEdit's MCP server over stdio like an agent host (Cursor-style).

Usage:
  python mcp_driver.py <project_dir> list-tools
  python mcp_driver.py <project_dir> call <tool_name> '<json-args>'
  python mcp_driver.py <project_dir> list-resources
  python mcp_driver.py <project_dir> list-prompts
  python mcp_driver.py <project_dir> call-many '<json>'   # {"tool": {...}, ...}

Every call is appended to <project_dir>/.open_edit/mcp_calls.jsonl for audit.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _server_cmd(project_dir: Path) -> list[str]:
    repo = Path(__file__).resolve().parent.parent
    return [
        sys.executable, "-m", "open_edit.mcp.server", "--project", str(project_dir),
    ]


async def _call(session: ClientSession, tool: str, args: dict) -> dict:
    result = await session.call_tool(tool, args or {})
    text = ""
    if result.content:
        text = "".join(c.text for c in result.content if hasattr(c, "text"))
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = {"raw": text[:4000]}
    return {
        "tool": tool,
        "isError": getattr(result, "isError", False),
        "result": parsed,
    }


async def main() -> int:
    project_dir = Path(sys.argv[1]).resolve()
    cmd = sys.argv[2]
    log_path = project_dir / ".open_edit" / "mcp_calls.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    params = StdioServerParameters(
        command=_server_cmd(project_dir)[0],
        args=_server_cmd(project_dir)[1:],
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            if cmd == "list-tools":
                tools = await session.list_tools()
                for t in tools.tools:
                    print(f"{t.name}: {t.description.splitlines()[0] if t.description else ''}")
                return 0

            if cmd == "list-resources":
                res = await session.list_resources()
                for r in res.resources:
                    print(f"{r.uri}: {r.name} — {r.description or ''}")
                return 0

            if cmd == "list-prompts":
                pr = await session.list_prompts()
                for p in pr.prompts:
                    print(f"{p.name}: {p.description or ''}")
                return 0

            if cmd == "call":
                tool = sys.argv[3]
                args = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
                out = await _call(session, tool, args)
                with open(log_path, "a") as fh:
                    fh.write(json.dumps(out) + "\n")
                print(json.dumps(out, indent=1)[:6000])
                return 0

            if cmd == "call-many":
                payload = json.loads(sys.argv[3])
                results = []
                for tool, args in payload.items():
                    out = await _call(session, tool, args)
                    results.append(out)
                    with open(log_path, "a") as fh:
                        fh.write(json.dumps(out) + "\n")
                print(json.dumps(results, indent=1)[:10000])
                return 0

            print(f"unknown command: {cmd}")
            return 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
