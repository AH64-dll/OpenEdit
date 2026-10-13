# Connect an agent to OpenEdit

Create or choose a project, then run the installed CLI:

```bash
open_edit init /absolute/path/to/project
open_edit mcp-config --project /absolute/path/to/project --format mcp
```

The generated configuration contains the installation's Python executable and
absolute project path. It retains the virtual environment and automatically
loads its provisioned media/Node runtime. Paths with spaces are supported.
Use `--output FILE` to write UTF-8 rather than copying console output.

| Host | Format and destination |
|---|---|
| Cursor | `--format mcp`; merge `mcpServers.openedit` into your project or user MCP JSON |
| Claude Desktop / standard MCP host | `--format mcp`; merge the `mcpServers` entry into the host's configuration |
| OpenCode | `--format opencode`; merge `mcp.openedit` into `opencode.json` |
| Codex CLI | `--format codex`; merge `[mcp_servers.openedit]` into `~/.codex/config.toml` |

The installer saves all three formats for its starter project. It does not
replace host settings, add model credentials or change unrelated agent tools.
Reload the host's MCP servers and confirm `query_project`, `edit_project`,
`run_script`, `trigger_render`, `get_render_job` and `cancel_render_job` are listed.

Try: “Inspect this project's timeline and make a precise edit to my selection.”
The server supplies compact startup instructions. Your agent can ask
`query_project` with `query: "describe"` for parameter examples when needed.
It does not need to read the application repository to learn how to edit.

MCP uses local stdio. No HTTP server or provider key in OpenEdit is required.
The same project can be opened by `open_edit serve` for human review. Keep your
agent host's authentication separate; cloud destination policies can still block
its chosen model provider even when local MCP connects successfully.

For OpenEdit's optional built-in OpenCode panel, start `open_edit serve --with-agent`
and select the installed OpenCode CLI/model. That app-owned editing agent gets a
project MCP connection and reports real tool results. An independently launched
OpenCode instance uses its own configuration and permissions.

To change projects, generate a new entry with the desired `--project` path. To
remove the connection, remove only the OpenEdit entry from your host's settings.
