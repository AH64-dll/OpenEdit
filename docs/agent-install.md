# Agent prompt: install Open Edit

This prompt hands the whole installation to your agent: it detects the OS,
clones the repository, creates a virtual environment, installs the package,
and creates an edit project, then verifies the MCP entry point end to end.
It works with any agent that can run shell commands and read files,
including Cursor, Claude Code, and OpenCode. The agent reports the absolute
clone, venv, and project paths it used, and it must not modify anything
outside the clone and the new project folder.

```text
You are installing Open Edit, a local AI video editor that runs as an MCP server. Do the entire install yourself, then verify it end to end.

1. Detect the operating system: Linux or macOS, or Windows.
2. Confirm prerequisites are on PATH: git, and Python 3.11+ (python3 on Linux/macOS, python on Windows). If either is missing, stop and tell the user what to install.
3. Clone the repository and enter it:
   git clone https://github.com/AH64-dll/OpenEdit.git
   cd OpenEdit
4. Create a virtual environment and install the package:
   Linux / macOS:
     python3 -m venv .venv
     source .venv/bin/activate
     pip install -U pip
     pip install -e ".[mcp]"
   Windows (PowerShell):
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     python -m pip install -U pip
     pip install -e ".[mcp]"
   If PowerShell blocks activation, first run: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   If your shell does not keep the venv active between commands, call the venv binaries directly: .venv/bin/open_edit and .venv/bin/open-edit-mcp on Linux/macOS, or .\.venv\Scripts\open_edit.exe and .\.venv\Scripts\open-edit-mcp.exe on Windows.
5. Install the optional extras (review UI and local transcription):
   pip install -e ".[mcp,serve]"
   pip install -e ".[mcp,whisper]"
6. Verify the MCP server entry point runs:
   Linux / macOS: .venv/bin/open-edit-mcp --help
   Windows: .\.venv\Scripts\open-edit-mcp.exe --help
   It must print usage with a --project option. If it errors, fix the cause before continuing.
7. Create an edit project. The folder must exist before init:
   Linux / macOS:
     mkdir -p ~/OpenEditProjects/my-talk
     open_edit init ~/OpenEditProjects/my-talk
   Windows:
     New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\OpenEditProjects\my-talk"
     open_edit init "$env:USERPROFILE\OpenEditProjects\my-talk"
8. Report back: the absolute clone path, the venv path, the absolute project path (the folder that contains .open_edit/), and confirmation that steps 6 and 7 succeeded. Do not skip or fake the verification. Do not modify anything outside the clone and the new project folder.
```
