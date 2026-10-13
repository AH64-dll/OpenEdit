"""Small, project-bound configurations for common MCP hosts."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .context import resolve_project_path


def host_config(project: str | Path, format_: str = 'mcp') -> str:
    root = resolve_project_path(Path(project).expanduser().resolve())
    # Resolve directories, but retain the venv interpreter symlink itself.
    command = os.path.abspath(sys.executable)
    args = ['-I', '-X', 'utf8', '-m', 'open_edit.mcp.server', '--project', str(root)]
    if format_ == 'codex':
        return ('[mcp_servers.openedit]\ncommand = ' + json.dumps(command)
                + '\nargs = ' + json.dumps(args) + '\n')
    if format_ == 'opencode':
        value = {'mcp': {'openedit': {'type': 'local', 'command': [command, *args], 'enabled': True}}}
    elif format_ == 'mcp':
        value = {'mcpServers': {'openedit': {'command': command, 'args': args}}}
    else:
        raise ValueError(f'Unknown MCP configuration format: {format_}')
    return json.dumps(value, indent=2) + '\n'
