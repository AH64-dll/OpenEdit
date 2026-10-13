"""Pydantic-backed registry of Open Edit tool argument schemas.

Single source of truth for the 4 pillar tools' plus the 2 render-job
helper tools' argument shapes, JSON schema generation, and LLM
tool-call validation.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from open_edit.render.preview_manifest import PreviewRange

_QUERY_PROJECT_DESC = (
    "Inspect project state with get_editing_context (selection, region, revision), list_assets, "
    "inspect_media (asset_hash, optional start_sec/end_sec, frames 1..12, transcript_limit 0..500), "
    "or get_history. inspect_media returns timestamped visual references and a bounded transcript. "
    "Use describe with params.name for operation parameters; omit name to list capabilities. "
    "Fetch source, full timelines and specialized analysis only when needed."
)
_EDIT_PROJECT_DESC = (
    "Edit the project. Common operations: ingest_local, add_clip, trim_clip, remove_clip, "
    "change_clip_speed, set_audio_gain. apply_studio_changes batches IR ops and objects "
    "atomically with expected_revision, changes, ops and label. undo/redo use expected_revision. "
    "Use query_project describe for parameters and other capabilities. "
    "run_script supports arbitrary IR edits. Existing project formats remain supported."
)
_RUN_SCRIPT_DESC = (
    "Execute trusted Python for complex IR edits in a timed subprocess. "
    "The IR version header is supplied automatically. Changes validate and commit atomically."
)
_TRIGGER_RENDER_DESC = (
    "Preview or export through the media engine. preview-chunks renders changed ranges "
    "in project seconds; final exports original media at high quality; proxy is a whole preview. "
    "Returns job_id unless wait=true. Poll get_render_job; cancel obsolete jobs. "
    "graphics renders editable JSX without committing; commit_graphics publishes the checked result. "
    "Encoder selection is automatic unless cpu/gpu is specified."
)
_GET_RENDER_JOB_DESC = "Read render job status. include_details=true adds diagnostics and logs."
_CANCEL_RENDER_JOB_DESC = "Cancel a queued or running render job."


class QueryProjectArgs(BaseModel):
    model_config = ConfigDict(
        extra="forbid", title="query_project", description=_QUERY_PROJECT_DESC
    )
    query: Literal[
        "describe",
        "inspect_media",
        "list_assets",
        "get_pending_notes",
        "get_style_profile",
        "analyze_narrative",
        "search_assets",
        "get_transcript_packed",
        "get_silence_gaps",
        "get_timeline_view",
        "get_authoring_view",
        "get_graphics_view",
        "get_history",
        "get_studio",
        "get_editing_context",
        "get_tracking_job",
    ]
    params: dict = {}


class EditProjectArgs(BaseModel):
    model_config = ConfigDict(
        extra="forbid", title="edit_project", description=_EDIT_PROJECT_DESC
    )
    operation: str | None = Field(default=None, min_length=1)
    params: dict = {}
    generate: Literal["sfx", "music", "visual", "silence_cuts", "remotion", "init_remotion", "write_remotion"] | None = None
    generate_params: dict = {}

    @model_validator(mode="after")
    def _one_edit_mode(self) -> EditProjectArgs:
        if bool(self.operation) == bool(self.generate):
            raise ValueError("provide exactly one of operation or generate")
        return self


class RunScriptArgs(BaseModel):
    model_config = ConfigDict(
        extra="forbid", title="run_script", description=_RUN_SCRIPT_DESC
    )
    code: str
    timeout_sec: int = Field(default=30, gt=0, le=300)


class TriggerRenderArgs(BaseModel):
    model_config = ConfigDict(
        extra="forbid", title="trigger_render", description=_TRIGGER_RENDER_DESC
    )
    mode: Literal["proxy", "final", "overlay", "preview-chunks", "graphics"] = "proxy"
    expected_revision: int | None = Field(default=None, ge=0)
    graphics: dict | None = Field(default=None, description='Graphics source, duration_sec and fps; requires expected_revision.')
    encoder: Literal["gpu", "cpu"] | None = None
    wait: bool = False
    ranges: list[PreviewRange] = Field(default_factory=list)
    media: Literal["video", "audio", "both"] = "both"
    priority: Literal["interactive", "background"] = "interactive"
    quality: Literal["fast", "standard", "high", "archival"] | None = None
    profile: str | None = None
    crf: int | None = Field(default=None, ge=0, le=51)
    vb: str | None = None
    preset: str | None = None
    scale: str | None = None
    codec: Literal["h264", "hevc", "av1"] | None = None


class GetRenderJobArgs(BaseModel):
    model_config = ConfigDict(
        extra="forbid", title="get_render_job", description=_GET_RENDER_JOB_DESC
    )
    job_id: str = Field(min_length=1)
    include_details: bool = Field(default=False, description="Include full render diagnostics and logs.")


class CancelRenderJobArgs(BaseModel):
    model_config = ConfigDict(
        extra="forbid", title="cancel_render_job", description=_CANCEL_RENDER_JOB_DESC
    )
    job_id: str = Field(min_length=1)


TOOL_REGISTRY: dict[str, type[BaseModel]] = {
    "query_project": QueryProjectArgs,
    "edit_project": EditProjectArgs,
    "run_script": RunScriptArgs,
    "trigger_render": TriggerRenderArgs,
    "get_render_job": GetRenderJobArgs,
    "cancel_render_job": CancelRenderJobArgs,
}

TOOL_DESCRIPTIONS: dict[str, str] = {
    name: (model.model_config.get("description") or "")
    for name, model in TOOL_REGISTRY.items()
}


def build_tool_schemas() -> list[dict]:
    """Return Anthropic-shaped tool schemas generated from the registry."""
    def compact(schema):
        if isinstance(schema, dict):
            return {key: compact(value) for key, value in schema.items() if key != "title"}
        if isinstance(schema, list):
            return [compact(value) for value in schema]
        return schema

    return [
        {
            "name": name,
            "description": TOOL_DESCRIPTIONS[name],
            "input_schema": compact({key: value for key, value in model.model_json_schema().items() if key != "description"}),
        }
        for name, model in TOOL_REGISTRY.items()
    ]
