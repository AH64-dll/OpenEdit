# Open Edit

![Python](https://img.shields.io/badge/python-3.11%2B-3776AB)
![License](https://img.shields.io/badge/license-MIT-blue)
![Platform](https://img.shields.io/badge/platform-linux%20%7C%20macos%20%7C%20windows-lightgrey)
![MCP](https://img.shields.io/badge/MCP-server-000000)

**AI-native video editing, driven over MCP.**

![Open Edit Review Studio](docs/hero-full.png)
*The Review Studio, live: preview a cut, inspect renders, and scrub the edit graph.*

![The product timeline](docs/hero-timeline.png)
*The timeline: clips on V1/A1/A2, edit markers, and a playhead that is ready to scrub.*

<video controls loop muted playsinline poster="docs/intro-poster.jpg" width="640">
  <source src="docs/intro-highlight.mp4" type="video/mp4">
  <a href="docs/intro-demo.gif">Open Edit logo intro (animated GIF)</a>
</video>
*The 60-second logo intro — animated in HTML/CSS with the HyperFrames engine and rendered entirely through Open Edit's own pipeline (the agent built the project, added the overlay, and ran the final 1080p30 GPU export).*

## What it is

Open Edit is an AI-native video editor that runs as a **local MCP server** over stdio.
An external agent (Cursor, Claude Code, OpenCode, any MCP client) owns the creative loop;
Open Edit owns the machinery: SHA-256 content-addressed ingest, word-level transcription
(faster-whisper), an append-only IR edit graph in SQLite (WAL), and melt + ffmpeg rendering
with a 640×360 proxy review artifact and a 1080p final export.

The MCP server needs no LLM API key. It is pinned to one project directory and
executes recorded, reversible IR operations. The included Review Studio runs in
review-only mode by default; built-in chat is an optional `--with-agent` mode.

## Downloads

**Python package (pip):**

```bash
pip install open-edit      # installs the open-edit CLI + open-edit-mcp server
```

**Linux / macOS — one command (full render stack):**

```bash
curl -fsSL https://github.com/AH64-dll/OpenEdit/releases/download/v1.3.1/install.sh | bash
```

**Windows (PowerShell):**

```powershell
irm https://github.com/AH64-dll/OpenEdit/releases/download/v1.3.1/install.ps1 | iex
```

**Source (v1.3.1):** [zip](https://github.com/AH64-dll/OpenEdit/archive/refs/tags/v1.3.1.zip) · [tar.gz](https://github.com/AH64-dll/OpenEdit/archive/refs/tags/v1.3.1.tar.gz)

The release installers also provision the render runtime (Node.js + the bundled HyperFrames overlay engine, plus ffmpeg/melt/Chrome checks) and print a readiness summary — see [INSTALL.md → Runtime requirements](INSTALL.md#runtime-requirements).

## The agent way

Use the local workspace directly or let an external agent operate the same project. Paste the install prompt into
your agent and it will clone, install, verify end to end, and report back. Then paste the
configure prompt to register the MCP server in your host and confirm all six tools appear.

- [docs/agent-install.md](docs/agent-install.md) — agent-driven install prompt
- [docs/agent-configure.md](docs/agent-configure.md) — agent-driven MCP configuration

## The normal way

**Linux / macOS**

```bash
git clone https://github.com/AH64-dll/OpenEdit.git
cd OpenEdit
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .        # extras: [whisper] for transcription; [agent] for optional built-in chat
```

**Windows (PowerShell)**

```powershell
git clone https://github.com/AH64-dll/OpenEdit.git C:\OpenEdit
cd C:\OpenEdit
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install -U pip
pip install -e .
```

Check the entry point, create a project, and start the review studio:

```bash
.venv/bin/open-edit-mcp --help            # Windows: .\.venv\Scripts\open-edit-mcp.exe --help
mkdir -p ~/OpenEditProjects               # Windows: New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\OpenEditProjects"
open_edit init ~/OpenEditProjects/my-talk
open_edit serve --review-only --port 8000 # → http://127.0.0.1:8000
```

Register the server in Cursor (`~/.cursor/mcp.json` on Linux/macOS, `%USERPROFILE%\.cursor\mcp.json` on Windows) and reload MCP:

```json
// Linux / macOS
{
  "mcpServers": {
    "open-edit": {
      "command": "/ABSOLUTE/PATH/TO/OpenEdit/.venv/bin/open-edit-mcp",
      "args": ["--project", "/home/YOU/OpenEditProjects/my-talk"],
      "env": { "OPEN_EDIT_RENDER_BACKEND": "cpu" }
    }
  }
}

// Windows
{
  "mcpServers": {
    "open-edit": {
      "command": "C:\\OpenEdit\\.venv\\Scripts\\open-edit-mcp.exe",
      "args": ["--project", "C:\\Users\\YOU\\OpenEditProjects\\my-talk"],
      "env": { "OPEN_EDIT_RENDER_BACKEND": "cpu" }
    }
  }
}
```

## Editing workspace

The workspace has **Review**, **Graphics** and **Code** views, with the timeline
below and selection properties in the right inspector. Select a clip to adjust
its placement, source range, volume or playback rate. Source editing stays
available in Code; graphics JSX is under **Edit graphics source**.

Previews update automatically using cached, dirty timeline ranges. The status
reads **Current**, **Updating…** or **Outdated**; the last checked preview stays
playable while an update runs. Undo/Redo reverts a whole action, including edits
made by MCP agents, and survives reopening a project. Keyboard shortcuts are
Ctrl/Cmd+Z and Ctrl/Cmd+Shift+Z outside text fields.

For an object in imported footage, choose **Select region** over the preview and
draw around the target. In **Tracked objects**, choose the clip, target mode,
direction and time range, then **Track selected region**. Tracking runs locally
in the background. Choose **Use track** to add its editable motion source.
Add a following highlight, label, cover, blur or pixelation effect; adjust its
color, strength, padding, offsets and size independently. Correct a box at any
source time, or draw a new region and retrack. Each object/effect can be disabled,
locked or deleted, and changes share Undo/Redo and AI request history.

The AI receives a compact target summary and can edit by object/effect ID.
Analysis accepts ranges up to five minutes, tracks foreground appearance or the
exact selected region, and reports target loss. Following effects use rectangular
regions; semantic object naming, precise segmentation and background inpainting
are separate capabilities. Bake speed/spatial changes before tracking them.
Preview and configurable local export consume the same editable source.

Open **Setup** for readiness checks and install instructions, or run:

```bash
open_edit doctor
open_edit setup media           # clip properties and literal source edits
open_edit setup graphics        # default editable graphics, with Chromium
open_edit setup html            # optional advanced HTML/CSS/JS overlays
open_edit setup legacy-remotion # existing Remotion projects only
```

A full FFmpeg build with ffprobe/libx264 and MLT/melt enables timeline preview
and export. Optional Node workers use tested Node.js 24 and locked packages.
The default Python installation and MCP startup download no Node dependencies.
The normal `npm ci` package only supplies HyperFrames; Remotion and React have
an independent compatibility package. Export defaults to automatic encoder
selection; manual CPU/GPU preferences are in advanced settings.

Built-in chat/provider management loads only with `open_edit serve --with-agent`
and optional `pip install 'open-edit[agent]'`. External MCP agents need no LLM
key in OpenEdit. See [the workspace guide](docs/EDITING_WORKSPACE.md).

## What you get

| Tool | Role |
|---|---|
| `query_project` | Read-only project queries |
| `edit_project` | Mutations + creative generation |
| `run_script` | Trusted Python IR edits in a subprocess with timeout and atomic validation |
| `trigger_render` | Enqueue proxy / final / preview-chunks renders |
| `get_render_job` | Poll a durable render job by `job_id` |
| `cancel_render_job` | Cancel queued or running jobs |

**Render modes:** `proxy` (640×360 review artifact, whole-file) → `final` (1080p).
Every render passes a deterministic 10-check QC gate before it is offered to you.

## Live guide

The product is documented and illustrated in the live guide: **[open-edit guide](https://ah64-dll.github.io/OpenEdit/)** — what it is, how it works, and how to install it on Linux and Windows.

## Docs

- [INSTALL.md](INSTALL.md) — full Linux + Windows setup, smoke checks, update/uninstall
- [docs/MCP.md](docs/MCP.md) — MCP tools, Cursor config, review UI, render workflow
- [skills/](skills/) — agent playbook and harness skills (also shipped in the wheel)
- [docs/DIFFUSION_INTEGRATION.md](docs/DIFFUSION_INTEGRATION.md) — compiler reuse assessment and adapter contract
- [docs/DIFFUSION_AUTHORING.md](docs/DIFFUSION_AUTHORING.md) — optional JSX media editing through MCP
- [docs/DIFFUSION_IMPLEMENTATION_PLAN.md](docs/DIFFUSION_IMPLEMENTATION_PLAN.md) — remaining integration milestones and acceptance checks
- [docs/REMOTION_LICENSE.md](docs/REMOTION_LICENSE.md) — Remotion licensing

## Contributing

Bugs, ideas, and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md)
(fork → branch → PR; CI runs tests on every pull request).

## License

OpenEdit's own code is MIT — see [LICENSE](LICENSE). The optional Diffusion
workers include unchanged MPL-2.0 source with licenses and provenance in
`open_edit/integrations/diffusion/worker/NOTICE.md` and
`open_edit/integrations/diffusion/browser/vendor/NOTICE.md`. The graphics font
is covered by `open_edit/integrations/diffusion/browser/fonts/OFL.txt`.
Experimental prototype; behavior may change between
releases. Editable motion graphics use the optional pinned Diffusion worker. HyperFrames
provides advanced HTML/CSS/JS overlays (`open_edit setup html`). Remotion is
legacy/migration-only (`open_edit setup legacy-remotion`).
Legacy Remotion templates may require a company license — see
[docs/REMOTION_LICENSE.md](docs/REMOTION_LICENSE.md).

### Optional Diffusion authoring and graphics

The [JSX editor](docs/DIFFUSION_AUTHORING.md) and
[Graphics studio](docs/DIFFUSION_GRAPHICS.md) edit the same revision-checked
SQLite graph as MCP. Install the compiler with
`python -m open_edit.integrations.diffusion.setup`; add `--graphics --chromium`
for text, shapes, animation and canvas previews. Python media workflows remain
usable without Node. See the [execution and validation report](docs/DIFFUSION_EXECUTION_VALIDATION.md)
for platform coverage, timing boundaries and upgrade behavior.
