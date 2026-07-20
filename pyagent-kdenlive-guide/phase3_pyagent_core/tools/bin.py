"""Tool defs for the project bin (import_media).

Phase 4 Task 7: repointed to AssetStore.ingest_paths.
"""
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


def import_media(args: dict, project_path: str) -> dict:
    """Ingest one or more media paths via the project's AssetStore."""
    from open_edit.agent.tools._helpers import get_asset_store

    paths = args["paths"]
    if not paths:
        raise ValueError("paths must be a non-empty list")
    store = get_asset_store(project_path)
    assets = store.ingest_paths(paths)
    return {
        "asset_hashes": [a.asset_hash for a in assets],
        "assets": [a.model_dump(mode="json") for a in assets],
    }
