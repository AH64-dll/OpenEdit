# Agent prompt: configure Open Edit as an MCP server

This prompt wires Open Edit into your MCP host: it detects the host (Cursor,
Claude Code, OpenCode, or another MCP client), resolves the absolute paths
to the MCP binary and the edit project, and registers the server in the
host's configuration. The agent verifies the server speaks MCP on stdio and
reports exactly which file it wrote and the paths it used. It must not
modify anything outside the clone and the new project folder.

```text
Open Edit is installed and an edit project exists (the folder that contains .open_edit/). Configure your MCP host to launch Open Edit as an MCP server. Do it yourself, then verify.

1. Detect the host you are running in: Cursor, Claude Code, OpenCode, or another MCP client.
2. Resolve the absolute path to the Open Edit MCP binary:
   Linux / macOS: <clone>/.venv/bin/open-edit-mcp
   Windows: <clone>\.venv\Scripts\open-edit-mcp.exe
   Substitute the real clone path from the install step.
3. Resolve the absolute path to the edit project folder (the one containing .open_edit/).
4. Register the server:
   - Cursor: edit ~/.cursor/mcp.json (Linux/macOS) or %USERPROFILE%\.cursor\mcp.json (Windows). If the file exists, back it up, then merge the new server into its mcpServers object without removing other servers.
   - Claude Code: the same mcpServers shape goes into the project's .mcp.json.
   - OpenCode: use OpenCode's own MCP config format (a per-server object with type and command). Do not paste the Cursor shape into OpenCode's config.
   The entry to add (Cursor and Claude Code), with real absolute paths substituted:
   {
     "mcpServers": {
       "open-edit": {
         "command": "<absolute path to open-edit-mcp>",
         "args": ["--project", "<absolute path to the edit project>"],
         "env": { "OPEN_EDIT_RENDER_BACKEND": "cpu" }
       }
     }
   }
   On Windows, JSON strings escape backslashes, so the command value looks like: C:\\OpenEdit\\.venv\\Scripts\\open-edit-mcp.exe
5. Verify: run the configured command once (open-edit-mcp --project "<project>") and confirm it speaks MCP on stdio, or reload the host's MCP list and confirm the open-edit server appears with its six tools: query_project, edit_project, run_script, trigger_render, get_render_job, cancel_render_job.
6. Tell the user to reload MCP servers in their host (Cursor: Cmd/Ctrl+Shift+P, then "Reload MCP Servers"). Report exactly which file you wrote, the absolute command path, and the pinned project path.
```
