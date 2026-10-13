# Ask an agent to install OpenEdit

Use the tested download archive for Windows x64 or Linux x64 from GitHub Releases,
or clone this repository for a source installation. Paste this into an agent
that can run local commands:

> Install OpenEdit for this operating system using INSTALL.md. Prefer the
> platform's released ZIP and verify its SHA-256. Run install.ps1 on Windows or
> install.sh on Linux. Keep my projects and agent configuration intact. Let the
> installer provision its pinned runtime and finish its actual editing,
> animated preview, export and reopen checks. Report the install-report.json
> result and any concrete failure; do not call a partial installation ready.
> Generate the configuration for my agent host with open_edit mcp-config,
> merge only its OpenEdit entry into my existing settings, then confirm all six
> project editing tools are available. No provider key is needed in OpenEdit
> for an external MCP agent.

A first install needs Internet access for Python packages, checksum-verified Node
and media runtimes, and the locked graphics worker/browser dependencies. Windows
can install Python with winget; Linux browser libraries may need administrator
access. Optional Whisper, HTML, legacy Remotion and built-in provider SDKs are not
part of the normal installation.

Installation and agent connection are independently verifiable. An agent host's
blocked model API does not mean the local MCP server failed to connect.
