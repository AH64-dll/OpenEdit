# Open Edit harness skills

Markdown skills for **any** agent host that drives Open Edit (MCP, built-in
serve agent, Pi, Claude Code, Cursor, custom loops). Prefer these files over
exploring `open_edit/**` source.

> Generated — edit `skills/` only. `open_edit/harness_skills/` ships
> byte-identical copies for wheel installs; do not edit them in place.

## Start here

| Skill | File | When to load |
|---|---|---|
| **MCP playbook** | [`open-edit-mcp.md`](open-edit-mcp.md) | Every editing / render session |
| MCP reference | [`open-edit-mcp-reference.md`](open-edit-mcp-reference.md) | Timeline IR / `run_script` details |

## Planning & QC

| Skill | File |
|---|---|
| Edit planning | [`edit-planning.md`](edit-planning.md) |
| Asset catalog & effects | [`asset_catalog_guide.md`](asset_catalog_guide.md) |
| Tool surface (long) | [`tool_surface.md`](tool_surface.md) |
| Style memory | [`style-memory.md`](style-memory.md) |
| Review notes | [`review-notes.md`](review-notes.md) |
| Legacy Remotion migration | [`remotion_motion.md`](remotion_motion.md) |
| Native HyperFrames route | [`hyperframes_native.md`](hyperframes_native.md) |
| Free-form / effects | [`freeform_and_effects.md`](freeform_and_effects.md) |
| QC standards | [`qc-standards.md`](qc-standards.md) |

## How hosts should load them

1. **Filesystem:** read this directory (`OPEN_EDIT_SKILLS_DIR` overrides path).
2. **MCP resources:** `open-edit://skills/open-edit-mcp`,
   `open-edit://skills/review-notes`, etc.
3. **MCP prompts:** `open-edit-playbook`, `open-edit-reference`,
   `open-edit-review-notes`, `open-edit-style-memory`, …
4. **MCP instructions (mandatory on connect):** the server embeds
   `open-edit-mcp`, `tool_surface`, `edit-planning`, `review-notes`, and
   `style-memory` into initialize `instructions` so harnesses do not need to
   explore the repository.

Python helper: `open_edit.mcp.skills.load_skill("open-edit-mcp")`.

Cursor users also get a thin pointer under `.cursor/skills/open-edit-mcp/`;
the **project** files above remain canonical for all harnesses.

## Not agent skills

Python modules under `open_edit/agent/skills/` (e.g. `silence_cutter.py`) are
**runtime libraries** called by tools — not docs for the LLM. Do not read them
to discover the tool API; use the MCP tools + this folder instead.
