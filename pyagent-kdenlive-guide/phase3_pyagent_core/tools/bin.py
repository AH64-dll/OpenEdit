"""Tool defs for the project bin (import_media)."""
from __future__ import annotations

from .project import ToolDef


IMPORT_MEDIA = ToolDef(
    name="pyagent_import_media",
    label="Import media",
    description="Add media files to the project bin. Returns the new source ids.",
    op="import_media",
    is_mutating=True,
    parameters_schema={
        "paths": {"type": "array", "items": {"type": "string"}, "minItems": 1},
    },
    required=("paths",),
)


TOOLS = [IMPORT_MEDIA]
