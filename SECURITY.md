# Security Policy

Open Edit is an experimental, local-first tool. It runs as a local MCP server
on your own machine and never phones home — no cloud accounts, no telemetry,
no uploads. Security-sensitive surface: the MCP stdio server, `open_edit serve`
(HTTP review UI), the `run_script` sandbox (bwrap on Linux / `dev` on
Windows), and the render subprocesses.

## Reporting a vulnerability

Please report privately via **GitHub private vulnerability reporting**:

1. Go to https://github.com/AH64-dll/OpenEdit
2. *Security → Report a vulnerability* (or open a draft advisory)

Do **not** open a public issue for security findings. Include:

- The affected component and version (release tag or commit)
- A minimal reproduction (commands, project files if small)
- Impact and any suggested fix

## What to expect

- Acknowledgment within 3 business days.
- A fix or a clear mitigation plan within 14 days for confirmed issues.
- Credit in the release notes for the fix (if you want it).

## Scope

In scope: the Python package (`open_edit/`), installers (`install.sh`,
`install.ps1`), and the GitHub Pages guide. Out of scope: dependencies
reported through their own channels, and the optional `whisper` models
(faster-whisper handles model loading).

## Safe defaults

- MCP runs over local stdio only; bind `serve` to 127.0.0.1 unless you know
  why not (`OPEN_EDIT_SERVE_HOST`).
- `serve` enforces a bearer token (`OPEN_EDIT_TOKEN`) for non-localhost
  clients.
- `run_script` uses bwrap sandboxing on Linux when available.
- No secrets are stored by the project; credentials live only in your own
  host configuration (e.g. `~/.config/gh/hosts.yml`).
