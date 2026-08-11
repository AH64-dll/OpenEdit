# Contributing to Open Edit

Thanks for considering a contribution. Open Edit is an AI-native video editor
driven as a local MCP server — a small, focused project, so a few conventions
keep it maintainable.

## How to propose changes

1. **Fork** https://github.com/AH64-dll/OpenEdit and create a branch:
   `git checkout -b fix/my-change`
2. Make your change. Keep it focused — one logical change per PR.
3. Open a **pull request** to `main`. Fill in the PR template (what changed,
   why, how you verified it).
4. CI runs on every PR (`pytest` on the core suite). A green check is required
   before merge.

Alternatively, if the change is small and you'd rather discuss first, open an
issue describing it before writing code.

## Local development setup

```bash
git clone https://github.com/AH64-dll/OpenEdit.git
cd OpenEdit
python3 -m venv .venv
source .venv/bin/activate            # Windows: .\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -e ".[mcp,dev]"          # includes test deps
npm install --no-audit --no-fund     # HyperFrames overlay engine (Node 22+)
```

> Node.js 22+ is required for motion-graphics rendering (pinned
> `hyperframes@0.7.65`). The MCP server itself runs without it.

## Before opening a PR

- Run the CI test set locally:
  ```bash
  pytest -q tests/test_tool_executor.py tests/test_ir tests/test_storage \
    tests/test_mcp_server.py --tb=short
  ```
  (CI runs the full list in `.github/workflows/ci.yml`.)
- Keep diffs focused; no unrelated reformatting.
- **No secrets.** Never commit tokens, keys, or credentials — anywhere.

## Code conventions

- Python 3.11+, type hints on public APIs, docstrings on modules and public
  functions.
- The render stack is **HyperFrames-native** (HTML/CSS/JS overlay engine).
  Remotion is legacy/migration-only — do not add new Remotion compositions.
- Platform differences are gated in code (see `INSTALL.md` → parity table),
  not duplicated per-OS.

## Review process

- Maintainer reviews within a few days. You may be asked for changes —
  that's normal; push updates to the same branch.
- Once CI is green and the change is reviewed, it is squashed and merged.

Questions? Open an issue — or ask your agent to read `docs/PIPELINE_ARCHITECTURE_MAP.md`.
