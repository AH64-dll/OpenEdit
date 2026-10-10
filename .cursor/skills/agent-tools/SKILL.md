---
name: agent-tools
description: >-
  Debug and extend Open Edit agent tools (script runner, runtime skills, style
  memory, TOOL_TABLE, MCP skills). Use when working on open_edit/agent/,
  run_script, style profiles, search_assets, or the agent-facing skills/.
disable-model-invocation: true
---

# Open Edit — Agent Tools

## Orient

1. Read [`architecture/BLUEPRINT.md`](../../../architecture/BLUEPRINT.md) (Agent Tools band).
2. LLM-facing skills live in [`skills/<name>/SKILL.md`](../../../skills/README.md);
   runtime libraries live in `open_edit/agent/skills/` (not docs).

## Rules

- **Keep the script runner** for `run_script` / free-form; improve diagnostics, don't remove it.
- **Search before generate:** `search_assets` (+ `import_asset`) before music / SFX / visual generation.
- **Style memory:** follow [`skills/open-edit-review`](../../../skills/open-edit-review/SKILL.md).
- **One dispatcher:** serve and MCP both go through `kernel.tool_executor` → `agent.tools.TOOL_TABLE` (37 callables).
- **Skills are a contract:** when you add or rename a query/operation, update
  `skills/open-edit-ops/SKILL.md`, run `python tools/sync_harness_skills.py`,
  and keep `tests/test_skills_contract.py` green.

## Symptom → package

| Symptom | Go to |
|---------|--------|
| `run_script` / free-form fails | `agent/script_runner/` (`bridge`, `bootstrap`, `execution`, `staging`) |
| Silence / narrative / music / SFX wrong | `agent/skills/` + matching `pyagent_*` |
| Style forgotten across turns | `style/`, `agent/style_inject.py` |
| Tool call errors | `kernel/tool_executor.py`, `kernel/pillar_tools.py` → `agent/tools/pyagent_*.py` |
| Missing node/melt/browser | `integrations/binaries.py`, `integrations/readiness.py` |
| Stock search bad | `agent/tools/pyagent_search_assets.py` |

## Do not

- Edit `open_edit/harness_skills/` directly: edit `skills/`, then sync.
- Strip the script runner "for safety later."
