# OpenEdit

An AI-native video editor: **select the moment, describe the edit, review the result**.
The application owns frame timing, media processing, previews and exports. Your
agent owns the creative decisions.

The editor centers on the preview, timeline, AI instructions, media and export.
Edits are reversible and survive reopening. Agents inspect bounded timestamped
frames and transcript ranges instead of repeatedly reading entire videos.

## Download and install

Get the Windows x64 or Linux x64 ZIP and its SHA-256 file from
[GitHub Releases](https://github.com/AH64-dll/OpenEdit/releases).
New builds are also available from the
[Release packages workflow](https://github.com/AH64-dll/OpenEdit/actions/workflows/release.yml).
Extract the archive, then run:

**Windows 10/11 x64 — PowerShell**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

**Linux x64 — Ubuntu 24.04 recommended**

```bash
bash ./install.sh
```

The installer creates a private Python environment, verifies pinned Node and
FFmpeg/MLT runtime downloads, installs the editable graphics worker and Chromium,
and tests actual MCP editing, a transition, an animated overlay, preview, export
and reopening. It reports success only after that workflow passes. Git is not
required for a downloaded release. Python 3.12 is recommended; Windows setup can
install it through winget. Linux may request administrator access for browser
system libraries.

Start the editor with `OpenEdit.cmd` (Windows) or `OpenEdit.sh` (Linux) in the
installation folder. Projects live separately under `~/OpenEditProjects`.
See [INSTALL.md](INSTALL.md) for requirements, existing runtimes, source installs,
updates and uninstalling.

## Connect your agent

The installer writes **mcp.json**, **opencode.json** and **codex.toml** for its
starter project. Merge the relevant entry into your agent host's configuration;
it does not overwrite existing agent settings.

For a different project, use the installed CLI:

```bash
open_edit init /absolute/path/to/your-project
open_edit mcp-config --project /absolute/path/to/your-project
open_edit mcp-config --project /absolute/path/to/your-project --format opencode
open_edit mcp-config --project /absolute/path/to/your-project --format codex
```

Run the commands with the installation's `.venv/bin/open_edit` on Linux or
`.venv\Scripts\open_edit.exe` on Windows if the virtual environment is not active.
The generated command uses that environment's Python and pins the project.
External agents need **no model key inside OpenEdit**. Your agent host handles its
own provider authentication. Once connected, ask it to edit the selected moment;
OpenEdit's MCP startup guidance and on-demand help describe the interfaces.

[Agent connection guide](docs/agent-configure.md) · [MCP reference](docs/MCP.md)

| Interface | Purpose |
|---|---|
| `query_project` | Inspect timeline/media/context; retrieve parameter help |
| `edit_project` | Apply project, clip, graphics and audio changes |
| `run_script` | Compose Python IR edits with timeout and atomic validation |
| `trigger_render` | Generate previews or final output |
| `get_render_job` | Inspect durable job progress and results |
| `cancel_render_job` | Stop queued or running work |

## Editing and rendering

Use **Edit** to select clips, scrub or mark a region for AI. Use **Graphics** for
editable text, shapes and animations. Source editing and advanced controls are
secondary. Preview work prioritizes the playhead and reuses unchanged ranges.
Final exports capture an immutable source revision, preserve audio/video timing,
verify output and leave existing exported files intact. Completed graphics are
reused across exports.

`open_edit doctor` reports installed capabilities. A CPU renderer is always
available in the provisioned runtime; compatible hardware encoders can be selected
when installed. GPU throughput and every driver combination are not guaranteed.

Built-in chat is optional: install with `--with-agent` / `-WithAgent`, then start
`open_edit serve --with-agent`. OpenCode CLI editing connects through the project's
MCP server and streams actual tool results. Local transcription is optional
(`--whisper` / `-Whisper`) and may download model data. Advanced HTML and legacy
Remotion packages are installed only on request with `open_edit setup html` or
`open_edit setup legacy-remotion`.

## Example and verification

The [ten-second explainer](examples/openedit-explainer/README.md) includes original
source, audio, preview and a script that creates its editable project through MCP.
[Architecture decisions and measurements](docs/CORE_REFACTOR.md) and the
[recorded authoring workflow](docs/OPENEDIT_EXPLAINER_WORKFLOW.md) distinguish actual
results from unverified model behavior.

[Release procedure](docs/RELEASING.md) · [Contributing](CONTRIBUTING.md)

## License

OpenEdit code is MIT. Vendored Diffusion source is MPL-2.0; its bundled font is
OFL-1.1. Notices and source accompany the wheel. Independently downloaded Node
and Shotcut runtimes retain their upstream licenses and source references;
see [third-party runtime notes](docs/RUNTIME_LICENSES.md).
Legacy Remotion use has separate [licensing terms](docs/REMOTION_LICENSE.md).
