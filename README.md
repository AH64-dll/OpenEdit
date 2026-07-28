# Open Edit

AI-native video editor driven as a local **MCP server** (Cursor, OpenCode, Claude Code).

**GitHub:** https://github.com/AH64-dll/OpenEdit

## What this repo is

Functional Open Edit product code only:

- IR / edit graph (`open_edit/ir`, `open_edit/storage`)
- Tool kernel (`open_edit/kernel`)
- MCP stdio server (`open_edit/mcp`)
- Render pipeline: melt / ffmpeg / Remotion (`open_edit/render`)
- Agent tools + skills (`open_edit/agent`, `skills/`)
- Optional review UI (`open_edit/serve`)

Not included (removed as dead / out of scope):

- Go `mlt-pipeline` CLIs
- Rust bwrap sandbox crate (use `OPEN_EDIT_SANDBOX_BACKEND=dev`; default on Windows)
- Planning dumps, agent scratch, Kdenlive guide forks

## Install

See **[INSTALL.md](INSTALL.md)** for Linux and Windows (clone → venv → Cursor `mcp.json`).

```bash
git clone https://github.com/AH64-dll/OpenEdit.git
cd OpenEdit
python -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -e ".[mcp]"
```

## Docs

- [INSTALL.md](INSTALL.md) — Linux + Windows setup
- [docs/MCP.md](docs/MCP.md) — MCP tools and Cursor config
- [docs/REMOTION_LICENSE.md](docs/REMOTION_LICENSE.md) — Remotion licensing
- [skills/open-edit-mcp.md](skills/open-edit-mcp.md) — agent playbook

## License / status

Experimental prototype. Remotion usage may require a company license — see `docs/REMOTION_LICENSE.md`.
