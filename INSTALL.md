# Install Open Edit

**Repository:** [https://github.com/AH64-dll/OpenEdit](https://github.com/AH64-dll/OpenEdit)

Clone this repo, install the Python package at the **repo root**, then point
Cursor (or another MCP host) at `open-edit-mcp`.

You also need a separate **edit project** directory (created with
`open_edit init`) where media and the edit graph live.

More MCP detail: [`docs/MCP.md`](docs/MCP.md).

---

## Prerequisites

| Tool | Linux | Windows | Required for |
|---|---|---|---|
| Git | yes | yes | clone |
| Python 3.11+ | yes | yes | MCP server |
| ffmpeg / ffprobe | recommended | recommended | media probe, overlays |
| melt (MLT) | recommended | recommended | proxy/final render |
| Node.js 24 (optional) | optional | optional | Remotion compositions |

On Windows, `run_script` defaults to unsandboxed `dev` mode. Moviepy
`generate_visual_for_segment` is unsupported on Windows. The Rust bwrap
sandbox is **not** shipped in this repo.

**Same codebase for Linux and Windows.** Platform-specific behavior is gated
in code (not separate trees):

| Area | Linux / macOS | Windows |
|---|---|---|
| Remotion alpha overlays | WebM / VP8 (`libvpx`) | ProRes 4444 (WebM alpha is unreliable) |
| Remotion CLI | `node_modules/.bin/remotion` | prefers `remotion.cmd` + `shell` spawn |
| Sandbox default | `bwrap` when available | `dev` subprocess |
| GPU encode | NVENC / VAAPI / QSV when present | NVENC / AMF / QSV when present |

Shared fixes (final High-quality encode, long-render timeouts, MCP timeline
ops, preview/hash alignment, melt base-track + ffmpeg overlay burn-in) apply
to both platforms.

---

## 1. Clone

### Linux / macOS

```bash
git clone https://github.com/AH64-dll/OpenEdit.git
cd OpenEdit
```

### Windows (PowerShell)

```powershell
git clone https://github.com/AH64-dll/OpenEdit.git C:\OpenEdit
cd C:\OpenEdit
```

---

## 2. Install the Python package (MCP)

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[mcp]"
```

Optional:

```bash
pip install -e ".[mcp,serve]"     # review UI
pip install -e ".[mcp,whisper]"   # local transcription
```

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[mcp]"
```

If activation is blocked:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Confirm:

```powershell
.\.venv\Scripts\open-edit-mcp.exe --help
```

Linux:

```bash
.venv/bin/open-edit-mcp --help
```

---

## 3. Create an edit project

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

- Linux / macOS: `~/.cursor/mcp.json`
- Windows: `%USERPROFILE%\.cursor\mcp.json`

### Linux / macOS

```json
{
  "mcpServers": {
    "open-edit": {
      "command": "/ABSOLUTE/PATH/TO/OpenEdit/.venv/bin/open-edit-mcp",
      "args": ["--project", "/home/YOU/OpenEditProjects/my-talk"],
      "env": {
        "OPEN_EDIT_RENDER_BACKEND": "cpu"
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
      "command": "C:\\OpenEdit\\.venv\\Scripts\\open-edit-mcp.exe",
      "args": ["--project", "C:\\Users\\YOU\\OpenEditProjects\\my-talk"],
      "env": {
        "OPEN_EDIT_RENDER_BACKEND": "cpu"
      }
    }
  }
}
```

Use absolute paths. Reload MCP in Cursor after editing the configuration.

Tools: `query_project`, `edit_project`, `run_script`, `trigger_render`,
`get_render_job`, `cancel_render_job`.

---

## 5. Optional: review UI

```bash
source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -e ".[mcp,serve]"
open_edit serve --review-only --port 8000
```

Open `http://127.0.0.1:8000` and select the same project.

---

## 6. Smoke check

1. Cursor shows `open-edit` MCP connected.
2. `query_project` works.
3. `edit_project` / `ingest_local` on any readable absolute media file.
4. `run_script` minimal `ir.add_clip(...)`.
5. `trigger_render` proxy if melt+ffmpeg are on PATH.

---

## Updating

```bash
cd OpenEdit
git pull
source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -e ".[mcp]"
```

Reload MCP in Cursor.

---

## Uninstall (Windows)

1. Remove the `open-edit` entry from `%USERPROFILE%\.cursor\mcp.json`.
2. Delete `C:\OpenEdit`.
3. Optionally delete `%USERPROFILE%\OpenEditProjects`.
4. Restart Cursor.
