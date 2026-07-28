# Install Open Edit

**Repository:** [https://github.com/AH64-dll/OpenEdit](https://github.com/AH64-dll/OpenEdit)

This guide covers cloning the repo and installing the **Open Edit MCP server**
(for Cursor / OpenCode / Claude Code) on **Linux** and **Windows**.

The Python package lives in the `open_edit/` folder. You also need a separate
**edit project** directory (created with `open_edit init`) where media and the
edit graph live.

For deeper MCP details see [`docs/MCP.md`](docs/MCP.md).

---

## Prerequisites

| Tool | Linux | Windows | Required for |
|---|---|---|---|
| Git | yes | yes | clone |
| Python 3.11+ | yes | yes | MCP server |
| ffmpeg / ffprobe | recommended | recommended | media probe, overlays |
| melt (MLT) | recommended | recommended | proxy/final render |
| Node.js 24 (optional) | optional | optional | Remotion compositions |
| bubblewrap / Rust sandbox | Linux only | **not used** | free-form jail (Linux) |

On Windows, `run_script` defaults to unsandboxed `dev` mode. Moviepy
`generate_visual_for_segment` is unsupported on Windows.

---

## 1. Clone

### Linux / macOS

```bash
git clone https://github.com/AH64-dll/OpenEdit.git
cd OpenEdit
```

### Windows (PowerShell)

```powershell
git clone https://github.com/AH64-dll/OpenEdit.git
cd OpenEdit
```

Example install location: `C:\OpenEdit` (or `C:\open_edit` if you rename the folder).

---

## 2. Install the Python package (MCP)

### Linux / macOS

```bash
cd open_edit
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[mcp]"
```

Optional extras:

```bash
pip install -e ".[mcp,serve]"     # review UI
pip install -e ".[mcp,whisper]"   # local transcription
```

### Windows (PowerShell)

```powershell
cd open_edit
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[mcp]"
```

If execution policy blocks activation:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Optional extras:

```powershell
pip install -e ".[mcp,serve]"
pip install -e ".[mcp,whisper]"
```

Confirm the console script exists:

```powershell
.\.venv\Scripts\open-edit-mcp.exe --help
```

Linux:

```bash
.venv/bin/open-edit-mcp --help
```

---

## 3. Create an edit project

The MCP server needs a project folder that contains `.open_edit/`.

### Linux / macOS

```bash
mkdir -p ~/OpenEditProjects
open_edit init ~/OpenEditProjects/my-talk
```

### Windows (PowerShell)

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\OpenEditProjects"
open_edit init "$env:USERPROFILE\OpenEditProjects\my-talk"
```

---

## 4. Configure Cursor MCP

Edit user MCP config:

- Linux / macOS: `~/.cursor/mcp.json`
- Windows: `%USERPROFILE%\.cursor\mcp.json`

### Linux / macOS

```json
{
  "mcpServers": {
    "open-edit": {
      "command": "/ABSOLUTE/PATH/TO/OpenEdit/open_edit/.venv/bin/open-edit-mcp",
      "args": ["--project", "/home/YOU/OpenEditProjects/my-talk"],
      "env": {
        "OPEN_EDIT_RENDER_BACKEND": "cpu",
        "OPEN_EDIT_INGEST_ALLOWLIST": "/home/YOU/Videos:/home/YOU/Music"
      }
    }
  }
}
```

### Windows

```json
{
  "mcpServers": {
    "open-edit": {
      "command": "C:\\OpenEdit\\open_edit\\.venv\\Scripts\\open-edit-mcp.exe",
      "args": ["--project", "C:\\Users\\YOU\\OpenEditProjects\\my-talk"],
      "env": {
        "OPEN_EDIT_RENDER_BACKEND": "cpu",
        "OPEN_EDIT_INGEST_ALLOWLIST": "C:\\Users\\YOU\\Videos;C:\\Users\\YOU\\Music"
      }
    }
  }
}
```

Notes:

- Use **absolute** paths.
- On Windows, ingest allowlist roots are separated by `;` (not `:`).
- Reload MCP in Cursor (Settings → MCP → refresh) or restart Cursor.
- You should see tools: `query_project`, `edit_project`, `run_script`,
  `trigger_render`, `get_render_job`, `cancel_render_job`.

---

## 5. Optional: review UI

### Linux / macOS

```bash
cd open_edit
source .venv/bin/activate
pip install -e ".[mcp,serve]"
open_edit serve --review-only --port 8000
```

Open `http://127.0.0.1:8000` and select the same project.

### Windows (PowerShell)

```powershell
cd open_edit
.\.venv\Scripts\Activate.ps1
pip install -e ".[mcp,serve]"
open_edit serve --review-only --port 8000
```

Open `http://127.0.0.1:8000`.

---

## 6. Smoke check

1. Cursor lists the `open-edit` MCP server as connected.
2. Call `query_project` (e.g. list assets / pending notes).
3. `edit_project` with `ingest_local` on a file under the project or allowlist.
4. `run_script` with a minimal `ir.add_clip(...)` (works on Windows via `dev`).
5. `trigger_render` with `"mode": "proxy"` if `melt` and `ffmpeg` are on PATH.
6. On Windows, moviepy `generate_visual` is expected to report unsupported.

---

## Updating from GitHub

### Linux / macOS

```bash
cd OpenEdit
git pull
cd open_edit
source .venv/bin/activate
pip install -e ".[mcp]"
```

### Windows (PowerShell)

```powershell
cd C:\OpenEdit
git pull
cd open_edit
.\.venv\Scripts\Activate.ps1
pip install -e ".[mcp]"
```

Then reload MCP in Cursor.

---

## Uninstall / remove from Windows

1. Remove the `open-edit` entry from `%USERPROFILE%\.cursor\mcp.json`.
2. Delete the clone folder (e.g. `C:\OpenEdit`).
3. Optionally delete edit projects under `%USERPROFILE%\OpenEditProjects`.
4. Restart Cursor.

---

## More docs

- [`docs/MCP.md`](docs/MCP.md) — MCP tools, skills, security notes
- [`open_edit/README.md`](open_edit/README.md) — package overview and limits
- [`docs/architecture-boundary.md`](docs/architecture-boundary.md) — Open Edit vs Go pipeline
