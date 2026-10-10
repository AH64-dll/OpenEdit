# Open Edit agent skills

Skills for any agent that drives Open Edit through its MCP server (Claude Code,
Cursor, OpenCode, Codex, custom hosts). Each is a standard `<name>/SKILL.md`
with `name`/`description` frontmatter, so the folders can also be copied into a
host's own skills directory.

| Skill | Load when |
|---|---|
| [`open-edit`](open-edit/SKILL.md) | Every session: workflow, defaults, error recovery |
| [`open-edit-ops`](open-edit-ops/SKILL.md) | You need an exact parameter, return shape or run_script method |
| [`open-edit-editing`](open-edit-editing/SKILL.md) | Planning/revising a cut, effects, QC failures |
| [`open-edit-graphics`](open-edit-graphics/SKILL.md) | Creating or editing any graphic |
| [`open-edit-review`](open-edit-review/SKILL.md) | Review notes, style preferences, undo/revert |

## How hosts get them

- **MCP resources:** `open-edit://skills/<name>`; **MCP prompts:** same names.
- **Startup instructions:** a short summary that points at these resources;
  full skills are never inserted into every session.
- **Filesystem:** this directory (`OPEN_EDIT_SKILLS_DIR` overrides it).

Operator configuration (cache/QC variables, preview routes, binary
resolution) is in [`docs/OPERATIONS.md`](../docs/OPERATIONS.md), not here.

## Editing

Edit only `skills/`, then run `python tools/sync_harness_skills.py` to refresh
the packaged mirror in `open_edit/harness_skills/`. Tests fail when the mirror
drifts, when a skill names an operation the server does not have, or when a
skill grows past its token budget.
