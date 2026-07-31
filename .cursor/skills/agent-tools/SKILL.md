---
name: agent-tools
description: >-
  Debug and extend Open Edit agent tools (sandbox, skills, style memory,
  TOOL_TABLE). Use when working on open_edit/agent/, run_script/sandbox,
  style profiles, search_assets, or the 26 tool callables.
disable-model-invocation: true
---

# Open Edit — Agent Tools

## Orient

1. Read [`architecture/BLUEPRINT.md`](../../../architecture/BLUEPRINT.md) (Agent Tools band).
2. Prefer host playbooks under [`skills/`](../../../skills/) over exploring `open_edit/**`.
3. Runtime libraries live in `open_edit/agent/skills/`; LLM-facing Markdown skills live in `skills/`.

## Rules

- **Keep the sandbox** — required for `run_python` / `run_script` / free-form and motion-graphics `run_render`. Improve diagnostics; do not remove.
- **Search before generate** — call `search_assets` (+ `import_asset`) for stock video/photo/audio before `generate_visual_for_segment` / music / SFX generate when licensed stock fits.
- **Style memory** — follow [`skills/style-memory.md`](../../../skills/style-memory.md): read profile early; capture confirmed user preferences via `capture_style_hint` / pins; do not silently invent style.
- **One dispatcher** — serve / MCP / Pi all go through `kernel.tool_executor` → `agent.tools.TOOL_TABLE`.

## Symptom → package

| Symptom | Go to |
|---------|--------|
| `run_script` / free-form fails | `agent/sandbox/` (`bridge`, `backends`, `bootstrap`, `staging`) |
| Silence / narrative / music / SFX wrong | `agent/skills/` + matching `pyagent_*` |
| Style forgotten across turns | `style/`, `agent/style_inject.py`, `skills/style-memory.md` |
| Tool call errors | `kernel/tool_executor.py` → `agent/tools/pyagent_*.py` |
| Stock search bad | `agent/tools/pyagent_search_assets.py` |

## Do not

- Explore source to rediscover pillar tools — use `skills/open-edit-mcp.md` / `tool_surface.md`.
- Strip sandbox “for safety later.”
- Edit `open_edit/harness_skills/` directly — edit `skills/` then sync copies.
