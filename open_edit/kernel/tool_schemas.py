"""Hand-written function-calling schemas for the Open Edit agent tools.

These schemas are NOT auto-generated. Each one is a hand-tuned JSON Schema
matching the actual ``args: dict`` shape that the corresponding function in
``open_edit.agent.tools`` expects. Keep them in sync with the tool
docstrings when the underlying tools change.

The 14 individual tools from v1.x have been consolidated into **4 pillar
tools** (Plan D, pillar-tool-consolidation):

- ``query_project`` — 5 read-only queries
- ``edit_project`` — all mutations + creative generation
- ``run_script`` — trusted Python (renamed from ``run_python``)
- ``trigger_render`` — server-side render (unchanged)

Each schema follows the Anthropic tools shape::

    {
        "name": str,
        "description": str,
        "input_schema": { JSON Schema }
    }
"""
from __future__ import annotations

from typing import Any

from open_edit.kernel.tool_registry import build_tool_schemas

# ---------------------------------------------------------------------------
# Pillar tool schemas (generated from the Pydantic registry)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = build_tool_schemas()


# Convenience lookup
TOOL_BY_NAME: dict[str, dict[str, Any]] = {t["name"]: t for t in TOOL_SCHEMAS}


def get_tool_schema(name: str) -> dict[str, Any] | None:
    """Return the schema for a tool by name, or None if unknown."""
    return TOOL_BY_NAME.get(name)


# ---------------------------------------------------------------------------
# "When to use each tool" guide — embedded in the system prompt
# ---------------------------------------------------------------------------

TOOL_USAGE_GUIDE = """\
# Tool usage guide

Skills (preferred over exploring source): skills/open-edit/SKILL.md, also MCP
resource open-edit://skills/open-edit and prompt open-edit. Exact parameters:
open-edit-ops. Notes/style/undo: open-edit-review. Graphics: open-edit-graphics.

Six tools: query_project, edit_project, run_script, trigger_render, plus the
get_render_job / cancel_render_job helpers. Priority:

1. query_project for every read: list_assets, get_transcript_packed,
   get_silence_gaps, get_pending_notes, get_style_profile (PascalCase op_type),
   search_assets, get_editing_context (include_timeline lists clip IDs),
   get_history, get_readiness (call on any missing_dependency error).
2. edit_project for every write (applied immediately). generate=silence_cuts /
   music / sfx / visual returns suggested ops; commit with apply_generated_ops
   (or apply_silence_gaps). Search stock (search_assets + import_asset) before
   generating music, SFX or visuals. capture_style_hint only when confirmed.
3. run_script only when no operation fits: Python using the preloaded ``ir``
   builder (below). It cannot read project state; fetch IDs first.
4. trigger_render (async): proxy for review, final after approval; poll
   get_render_job until terminal and check qc_report.passed/complete.
"""


def _ir_method_lines() -> str:
    """One line per IR builder method, generated so it cannot drift from the API."""
    import inspect

    from open_edit.ir.api import IR

    lines = []
    for name, fn in inspect.getmembers(IR, inspect.isfunction):
        if name.startswith('_') or name == 'append':
            continue
        params = [p for p in inspect.signature(fn).parameters.values()
                  if p.name not in ('self', 'originating_note_id')]
        lines.append(f"- ``ir.{name}({', '.join(str(p).split(':')[0] for p in params)})``")
    return "\n".join(lines)


IR_MODEL_SUMMARY = f"""\
## Open Edit IR summary

The edit graph is an ordered log of IR ops (``open_edit.ir.types``); the
timeline is derived from it. Edits append ops; undo/redo/revert reverse whole
actions. ``run_script`` code builds ops with the preloaded ``ir`` object (the
IR version header is injected) and the ops are validated and appended
atomically. Clip timing fields are ``in_point_sec``/``out_point_sec``/
``position_sec``; transitions join ``clip_a_id``/``clip_b_id`` with type
``cut``, ``fade``, ``dissolve``, ``wipe`` or ``luma``.

``ir`` methods:
{_ir_method_lines()}

Captions, graphics documents and object tracks change through
``edit_project`` (apply_studio_changes, apply_graphics_edits, tracking
operations), not ``run_script``. Review notes are not ops: read them with
``get_pending_notes``; ``add_marker`` creates an agent note. Pinned style
values (``set_pinned_value``) override inferred defaults.
"""
