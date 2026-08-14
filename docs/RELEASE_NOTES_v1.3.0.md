# Open Edit v1.3.0

Open Edit is an AI-native video editor driven over the Model Context Protocol (MCP): agents inspect projects, apply edits, render, and QC through a local MCP stdio server. Everything is local-first — your media and edit history stay on your machine, with no cloud accounts or uploads — and v1.3.0 ships one-command installers for Linux and Windows.

## What's new

- **MCP stdio server** exposing six tools — `query_project`, `edit_project`, `run_script`, `trigger_render`, `get_render_job`, and `cancel_render_job` — so any MCP-capable agent can drive the full edit workflow.
- **SHA-256 CAS ingest**: media is content-addressed on import, so identical files deduplicate automatically and every asset is verified by hash.
- **Word-level transcription** powered by faster-whisper, giving precise per-word timestamps for cutting, silence removal, and search.
- **Append-only IR edit graph** persisted in SQLite (WAL mode) with 28 op kinds — every edit is recorded as an immutable operation; nothing is destructively rewritten.
- **melt + ffmpeg rendering**: fast 640×360 proxy review artifacts for iteration, and full 1080p final exports.
- **Deterministic 10-check QC gate** that must pass before a render is accepted.
- **One-command installers**: `install.sh` for Linux and `install.ps1` for Windows.
- **Agent-driven setup prompts** in `docs/agent-install.md` and `docs/agent-configure.md` — paste them into an agent to install and configure the MCP server in one go.
- **MIT license** — free to use, modify, and distribute.
- **Python >= 3.11** required.

## Install

- Linux: `bash install.sh`
- Windows: `powershell -ExecutionPolicy Bypass -File install.ps1`
- Full setup instructions: see `INSTALL.md` and the agent prompts in `docs/agent-install.md` / `docs/agent-configure.md`.
