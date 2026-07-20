"""Tool defs for project-level reads.

Also defines the `ToolDef` dataclass that every other tools/*.py module
re-uses. Keep it here so the dataclass has a single home.

`parameters_schema` holds the *properties* object only (the dict that
TypeBox's `Type.Object(properties, ...)` expects). The `required` tuple
carries the list of required parameter names separately. The TS side
(`extension.ts`) wires them together via `buildTypeBoxSchema`.

Storing them split avoids the bug where the JSON-Schema top-level keys
("type", "properties", "required") get treated as parameter names by
Type.Object().

Phase 4 Task 7: read-back bodies use Project.load_all + derive_timeline.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolDef:
    name: str
    label: str
    description: str
    is_mutating: bool
    parameters_schema: dict  # just the properties object, NOT a full JSON Schema document
    op: str = ""  # backend op name to dispatch to; "" for tools that call phase6 directly
    required: tuple[str, ...] = ()  # names of required parameters; empty tuple = all optional


GET_PROJECT_INFO = ToolDef(
    name="pyagent_get_project_info",
    label="Get project info",
    description="Get the current .kdenlive project's metadata (name, fps, dimensions, duration, etc).",
    op="get_project_info",
    is_mutating=False,
    parameters_schema={},
    required=(),
)


GET_TIMELINE_SUMMARY = ToolDef(
    name="pyagent_get_timeline_summary",
    label="Get timeline summary",
    description=(
        "Get the current timeline: tracks, clips, transitions, markers. "
        "Call this BEFORE planning any edit (per the system prompt rules)."
    ),
    op="get_timeline_summary",
    is_mutating=False,
    parameters_schema={},
    required=(),
)


TOOLS = [GET_PROJECT_INFO, GET_TIMELINE_SUMMARY]


# --- Wrapper functions (Phase 4 Task 7) ---


def get_project_info(args: dict, project_path: str) -> dict:
    """Return project metadata (id, name, workdir, track_count, duration)."""
    from open_edit.agent.tools._helpers import _db_path, load_project
    from open_edit.ir.apply import derive_timeline

    project = load_project(project_path)
    timeline = derive_timeline(project)
    db_path = _db_path(project_path)
    return {
        "project_id": project.project_id,
        "name": project.name,
        "workdir": str(project.workdir) if project.workdir else str(db_path.parent),
        "track_count": len(timeline.tracks),
        "duration_sec": timeline.duration_sec,
        "asset_count": len(project.assets),
        "op_count": len(project.edit_graph),
    }


def get_timeline_summary(args: dict, project_path: str) -> dict:
    """Return tracks/clips/effects/groups summary derived from the timeline."""
    from open_edit.agent.tools._helpers import load_project
    from open_edit.ir.apply import derive_timeline

    project = load_project(project_path)
    timeline = derive_timeline(project)
    tracks = []
    for t in timeline.tracks:
        tracks.append({
            "track_id": t.track_id,
            "kind": t.kind,
            "clip_count": len(t.clips),
            "effect_count": len(t.effects),
        })
    clips = [
        {
            "clip_id": c.clip_id,
            "asset_hash": c.asset_hash,
            "track_id": c.track_id,
            "position_sec": c.position_sec,
            "in_point_sec": c.in_point_sec,
            "out_point_sec": c.out_point_sec,
            "effect_count": len(c.effects),
        }
        for t in timeline.tracks for c in t.clips
    ]
    groups = [op.label for op in project.edit_graph if op.kind == "group_edits"]
    return {
        "project_id": project.project_id,
        "tracks": tracks,
        "clips": clips,
        "groups": groups,
        "duration_sec": timeline.duration_sec,
    }
