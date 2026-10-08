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
    "Read-only queries about the project. Use this for ALL "
    "read-only operations — listing assets, pending notes, style "
    "profile, narrative analysis, asset search, and packed transcript. "
    "get_silence_gaps returns structured silence + filler spans for cutting; "
    "get_timeline_view renders an on-demand filmstrip+waveform+word-label PNG "
    "(the transcript-first visual layer). "
    "list_assets is compact by default (hash/filename/duration); pass "
    "params.detail=true for full metadata, params.include_derivatives=true "
    "to include Remotion rematerialized CAS."
    " Use params.offset/limit for paged assets (default limit 50); follow next_offset."
    " Packed transcripts use word offset/limit (default 500, max 2000); follow next_offset."
    " get_authoring_view exports an optional Diffusion JSX media view; params.include_source=true returns source."
)

_EDIT_PROJECT_DESC = (
    "Apply edits to the project or generate creative suggestions. "
    "Use ``operation`` for immediate mutations: add_marker, "
    "set_pinned_value, capture_style_hint, import_asset, ingest_local, "
    "add_clip, add_hyperframes_overlay, trim_clip, replace_clip_source, "
    "change_clip_speed, remove_clip, set_audio_gain, apply_silence_gaps, "
    "auto_color_grade, apply_generated_ops. Prefer these timeline ops over "
    "run_script. "
    "apply_authoring_edit accepts an exported expected_revision plus source or source edits for the optional Diffusion adapter. "
    "Use ``generate`` for creative suggestions (SFX, music, visuals, "
    "remotion, silence_cuts) — review then commit via "
    "``operation=\"apply_generated_ops\"`` (or apply_silence_gaps for cuts). "
    "``operation=ingest_local`` ingests any readable absolute local media "
    "path and copies it into the project CAS. "
    "``operation=add_hyperframes_overlay`` adds native HTML/CSS/JS "
    "graphics. New motion graphics should use HyperFrames, not Remotion. "
    "``generate=remotion`` appends a legacy AddRemotionCompositionOp "
    "(materializes on proxy/final render; graphics burned via ffmpeg). "
    "``generate=init_remotion`` scaffolds ``.open_edit/remotion/``. "
    "``generate=write_remotion`` writes a TSX composition file."
)

_RUN_SCRIPT_DESC = (
    "Run Python in the trusted Python subprocess for complex edits. "
    "The IR version header is injected automatically — do NOT add it "
    "manually. Use this when no single edit_project operation fits "
    "— e.g. multi-step edits that need to fetch state, compose "
    "ops, and append them programmatically."
)

_TRIGGER_RENDER_DESC = (
    "Trigger a render of the current edit graph. Use this when "
    "the user says 'render it', 'give me a preview', or 'export "
    "the final cut'. Modes: 'proxy' (fast, low-res review artifact), "
    "'final' (full quality export), 'overlay' (legacy HyperFrames "
    "composite mode), or 'preview-chunks' (range-limited, "
    "manifest-backed video/audio artifacts). Motion graphics should use "
    "the native HyperFrames composition path; legacy Remotion operations "
    "remain migration inputs only. "
    "encoder: 'gpu' (default) or 'cpu' for video encoding backend. "
    "wait: defaults to false so agents return immediately with job_id "
    "(poll with get_render_job). Pass wait=true only when a synchronous "
    "result path is required. For preview-chunks, ranges are project "
    "seconds, media is video/audio/both, and priority is interactive or "
    "background. Returns job_id when wait=false, or the manifest-oriented "
    "result when wait=true."
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
    mode: Literal["proxy", "final", "overlay", "preview-chunks"] = "proxy"
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
