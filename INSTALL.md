# Install OpenEdit

The download releases target **Windows 10/11 x64** and **Linux x64 (Ubuntu 24.04
recommended)**. Release CI installs each ZIP on its native platform and checks
actual media editing, animated compositing, previews, export and reopening.
macOS and ARM are source-install targets; no tested download package is advertised
for them.

## Download release

Download the ZIP and matching `.zip.sha256` from GitHub Releases. Verify its hash
before running the installer. Linux: `sha256sum -c OpenEdit-1.4.0-linux-x64.zip.sha256`.
Windows: compare `Get-FileHash .\OpenEdit-1.4.0-windows-x64.zip -Algorithm SHA256`
with the downloaded checksum. Extract the archive.

Linux:

```bash
bash ./install.sh
~/OpenEdit/OpenEdit.sh
```

Windows PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
& "$env:USERPROFILE\OpenEdit\OpenEdit.cmd"
```

The one-process execution-policy option permits this downloaded script; the
installer does not change the machine's persistent PowerShell policy. Managed
machines may require an approved or signed installer under their own policy.

Python **3.11.8 or newer**, with **3.12 recommended**, is needed. On Windows the
installer offers installation through winget when Python is absent. On Debian or
Ubuntu it installs `python3-venv` and Chromium system libraries through apt with
administrator access. Other Linux distributions need their equivalent browser
libraries and Python venv support. The installer never reports a partial setup
as verified.

Node 24 and the complete FFmpeg/MLT runtime are downloaded into `.runtime` under
the chosen installation, using pinned SHA-256 checksums. The Linux media binaries
use the upstream environment wrappers; Windows uses the matching MLT and Qt
plugin directories. This provides native Windows timeline rendering without
requiring users to build MLT or install WSL. The default graphics worker is locked
and patched through the package's setup command. Chromium is installed unless a
valid explicit `OPEN_EDIT_CHROMIUM` override or installed Playwright browser exists.

## Options and existing prerequisites

| Linux | Windows | Meaning |
|---|---|---|
| `--dir PATH` | `-InstallDir PATH` | Installation folder |
| `--no-project` | `-NoProject` | Skip the starter project |
| `--system-runtime` | `-SystemRuntime` | Use existing Node 24, npm, ffmpeg, ffprobe and melt |
| `--media-only` | `-MediaOnly` | Install the clip/source compiler; omit graphics/Chromium |
| `--with-agent` | `-WithAgent` | Add optional built-in provider SDKs |
| `--whisper` | `-Whisper` | Add optional local transcription dependencies |
| `--skip-system-deps` | — | Browser libraries and Python venv are already installed |

`--system-runtime` still checks binaries and executes the media workflow. Audio EQ
needs MLT 7.28 or newer; the pinned download provides 7.41. A system runtime's
capabilities are shown by `open_edit doctor`. `--media-only` does not claim that
editable graphics are installed. Optional transcription requires suitable disk
space and downloads its selected model when used.

The install creates `install-report.json` and an actual `install-report.mp4`.
A failure stops setup with a nonzero exit. Rerunning the same installer repairs
or verifies its environment and preserves the starter project's editing history.

## Connect an agent

The installation creates `mcp.json` (Cursor/Claude Desktop and standard hosts),
`opencode.json` and `codex.toml`. Merge their OpenEdit entry with your existing
host configuration. Those files are examples; no agent configuration is overwritten.
An external MCP host needs no provider key in OpenEdit.

For a new project, run the installation's `open_edit init PATH` and
`open_edit mcp-config --project PATH --format mcp` (or `opencode` / `codex`).
Use absolute paths and reload the agent's MCP servers. Confirm all six OpenEdit
tools appear. [Detailed host instructions](docs/agent-configure.md).

## Install from source

For Windows/Linux x64, clone this repository and run `bash install.sh` or the
PowerShell installer. It builds the checkout as a normal installed package.
For macOS, other architectures or an editable development environment, supply
the native runtimes and install manually; check readiness before editing:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -c requirements/release-constraints.txt -e '.[dev]'
# Supply Node 24, ffmpeg, ffprobe and MLT (macOS: brew install node ffmpeg mlt).
open_edit setup graphics
open_edit doctor
open_edit serve
```

A source checkout alone does not install browser/system prerequisites. Linux
headless containers may need `OPEN_EDIT_CHROMIUM_NO_SANDBOX=1`; do not use that
container-specific setting as a normal desktop requirement.

## Update and uninstall

Stop the editor and connected MCP processes. Download and extract the new release,
then run its installer with the same installation folder. Do not run an old
release's installer to obtain a newer version. For source updates, preserve local
edits, `git pull --ff-only`, then rerun the installer.

Remove the installation directory to uninstall. Projects under `OpenEditProjects`
and exported files remain separate; remove them only if you intentionally want
to delete your work. Agent host entries referencing the removed installation
should be removed from that host's configuration.
