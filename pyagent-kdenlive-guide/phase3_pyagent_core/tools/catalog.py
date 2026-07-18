"""Tool defs for catalog lookups."""
from __future__ import annotations

from .project import ToolDef


LIST_CATALOG = ToolDef(
    name="pyagent_list_catalog",
    label="List catalog",
    description=(
        "Look up available effects, transitions, or generators from the catalog. "
        "Use kind='effects'|'transitions'|'generators' and an optional filter substring."
    ),
    op="list_catalog",
    is_mutating=False,
    parameters_schema={
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["effects", "transitions", "generators"]},
            "filter": {"type": "string"},
        },
        "required": ["kind"],
    },
)


TOOLS = [LIST_CATALOG]
