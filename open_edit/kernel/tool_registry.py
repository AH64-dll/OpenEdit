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
    "Read-only project queries; params per query are in skill open-edit-ops. "
    "get_readiness: installed capabilities and exact fixes (call on missing_dependency). "
    "list_assets: hash/filename/duration_s, paged offset/limit (detail=true for metadata). "
    "get_transcript_packed / get_silence_gaps {asset_hash}: words with silences / silence+filler spans. "
    "get_timeline_view: filmstrip+waveform PNG for a time range. "
    "get_editing_context: compact targets, marks, region and counts; include_timeline=true adds a "
    "compact clip/track index (IDs for edits). get_studio: full objects (fetch before replacing one). "
    "get_history {limit}: revision and next undo/redo. get_pending_notes, get_style_profile "
    "{op_type: AddClip|AddTransition|AddEffect|...}, search_assets {query}, analyze_narrative, "
    "get_graphics_view / get_authoring_view (Diffusion source), get_tracking_job {job_id}."
)

_EDIT_PROJECT_DESC = (
    "Apply edits (operation + params) or request suggestions (generate + generate_params); "
    "exact params in skill open-edit-ops. Timeline: ingest_local {paths}, import_asset, add_clip, "
    "trim_clip, remove_clip, replace_clip_source, change_clip_speed, set_audio_gain, "
    "apply_silence_gaps, auto_color_grade, add_marker. Graphics: commit_graphics (after "
    "trigger_render mode=graphics), apply_graphics_edits, apply_studio_changes (documents, "
    "captions, styles), rewrite_graphics_source, add_hyperframes_overlay (advanced HTML; returns "
    "lint). Media: apply_authoring_edit, retime_asset. Tracking: start_tracking, apply_tracking_job, "
    "cancel_tracking, edit_object_track. History: undo/redo {expected_revision}, revert_request. "
    "Style: capture_style_hint (confirmed only), set_pinned_value. generate=silence_cuts|music|sfx|"
    "visual returns ops; commit with apply_generated_ops (or apply_silence_gaps). Prefer these "
    "over run_script; remotion generate kinds are legacy migration only."
)

_RUN_SCRIPT_DESC = (
    "Run Python in the trusted Python subprocess for complex edits. "
    "The IR version header is injected automatically — do NOT add it "
    "manually. Use this when no single edit_project operation fits "
    "— e.g. multi-step edits that need to fetch state, compose "
    "ops, and append them programmatically."
)

_TRIGGER_RENDER_DESC = (
    "Render the current edit graph as a durable job; returns job_id (poll get_render_job). "
    "Modes: proxy (whole-file review MP4), final (full-quality export, after approval), "
    "preview-chunks (range cache: ranges/media/priority), graphics (Diffusion JSX to CAS: "
    "graphics={source,duration_sec,fps} + expected_revision, then edit_project commit_graphics), "
    "overlay (legacy). Fails fast with error_code=missing_dependency when melt or the graphics "
    "worker is unavailable. Leave encoder overrides unset unless the user asks."
)

_GET_RENDER_JOB_DESC = (
    "Poll a durable render job by job_id. Use after trigger_render "
    "when you need status without blocking. Set include_details=true "
    "only when full diagnostics and logs are needed."
)

_CANCEL_RENDER_JOB_DESC = (
    "Cancel a queued or running render job by job_id."
)


class QueryProjectArgs(BaseModel):
    model_config = ConfigDict(
        extra="forbid", title="query_project", description=_QUERY_PROJECT_DESC
    )
    query: Literal[
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
        "get_readiness",
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
    encoder: Literal["gpu", "cpu"] | None = Field(
        default=None, description="gpu (default) probes NVENC/QSV/AMF and falls back to libx264.")
    wait: bool = Field(default=False, description="Block until done; default returns job_id at once.")
    ranges: list[PreviewRange] = Field(default_factory=list, description="preview-chunks: project-second ranges.")
    media: Literal["video", "audio", "both"] = "both"
    priority: Literal["interactive", "background"] = "interactive"
    quality: Literal["fast", "standard", "high", "archival"] | None = None
    profile: str | None = Field(default=None, description="Render profile name, e.g. 720p30 or 1080p30.")
    crf: int | None = Field(default=None, ge=0, le=51, description="Quality override (lower is better).")
    vb: str | None = Field(default=None, description="Video bitrate override, e.g. 10M.")
    preset: str | None = Field(default=None, description="Encoder preset override.")
    scale: str | None = Field(default=None, description="Output size override, e.g. 1280x720.")
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
