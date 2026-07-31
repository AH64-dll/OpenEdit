"""Pydantic-backed registry of Open Edit tool argument schemas.

Single source of truth for the 4 pillar tools' plus the 2 render-job
helper tools' argument shapes, JSON schema generation, and LLM
tool-call validation.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


_QUERY_PROJECT_DESC = (
    "Read-only queries about the project. Use this for ALL "
    "read-only operations — listing assets, pending notes, style "
    "profile, narrative analysis, asset search, and packed transcript. "
    "list_assets is compact by default (hash/filename/duration); pass "
    "params.detail=true for full metadata, params.include_derivatives=true "
    "to include Remotion rematerialized CAS."
)

_EDIT_PROJECT_DESC = (
    "Apply edits to the project or generate creative suggestions. "
    "Use ``operation`` for immediate mutations: add_marker, "
    "set_pinned_value, import_asset, ingest_local, "
    "add_clip, trim_clip, replace_clip_source, change_clip_speed, "
    "remove_clip, set_audio_gain, apply_silence_gaps, apply_generated_ops. "
    "Prefer these timeline ops over run_script. "
    "Use ``generate`` for creative suggestions (SFX, music, visuals, "
    "remotion, silence_cuts) — review then commit via "
    "``operation=\"apply_generated_ops\"`` (or apply_silence_gaps for cuts). "
    "``operation=ingest_local`` ingests absolute local media paths "
    "(project dir or OPEN_EDIT_INGEST_ALLOWLIST). "
    "``generate=remotion`` appends an AddRemotionCompositionOp "
    "(materializes on proxy/final render; graphics burned via ffmpeg). "
    "``generate=init_remotion`` scaffolds ``.open_edit/remotion/``. "
    "``generate=write_remotion`` writes a TSX composition file."
)

_RUN_SCRIPT_DESC = (
    "Run Python in the bwrap+seccomp sandbox for complex edits. "
    "The sandbox header is injected automatically — do NOT add it "
    "manually. Use this when no single edit_project operation fits "
    "— e.g. multi-step edits that need to fetch state, compose "
    "ops, and append them programmatically."
)

_TRIGGER_RENDER_DESC = (
    "Trigger a render of the current edit graph. Use this when "
    "the user says 'render it', 'give me a preview', or 'export "
    "the final cut'. Modes: 'proxy' (fast, low-res preview; also "
    "materializes Remotion compositions and burns them onto the "
    "melt output via ffmpeg), 'final' (full quality; re-bakes "
    "Remotion at full profile), or 'overlay' (HyperFrames "
    "HTML overlays only — Remotion does NOT use this mode). "
    "encoder: 'gpu' (default) or 'cpu' for video encoding backend. "
    "wait: defaults to false so agents return immediately with job_id "
    "(poll with get_render_job). Pass wait=true only when a synchronous "
    "result path is required. "
    "Returns job_id when wait=false, or the output path when wait=true."
)

_GET_RENDER_JOB_DESC = (
    "Poll a durable render job by job_id. Use after trigger_render "
    "when you need status without blocking, or to inspect a prior job."
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
    ]
    params: dict = {}


class EditProjectArgs(BaseModel):
    model_config = ConfigDict(
        extra="forbid", title="edit_project", description=_EDIT_PROJECT_DESC
    )
    operation: Optional[str] = None
    params: dict = {}
    generate: Optional[Literal[
        "sfx", "music", "visual", "silence_cuts",
        "remotion", "init_remotion", "write_remotion",
    ]] = None
    generate_params: dict = {}


class RunScriptArgs(BaseModel):
    model_config = ConfigDict(
        extra="forbid", title="run_script", description=_RUN_SCRIPT_DESC
    )
    code: str
    timeout_sec: int = 30


class TriggerRenderArgs(BaseModel):
    model_config = ConfigDict(
        extra="forbid", title="trigger_render", description=_TRIGGER_RENDER_DESC
    )
    mode: Literal["proxy", "final", "overlay"] = "proxy"
    encoder: Literal["gpu", "cpu"] | None = None
    wait: bool = False
    quality: str | None = None
    profile: str | None = None
    crf: int | None = None
    vb: str | None = None
    preset: str | None = None
    scale: str | None = None
    codec: str | None = None


class GetRenderJobArgs(BaseModel):
    model_config = ConfigDict(
        extra="forbid", title="get_render_job", description=_GET_RENDER_JOB_DESC
    )
    job_id: str


class CancelRenderJobArgs(BaseModel):
    model_config = ConfigDict(
        extra="forbid", title="cancel_render_job", description=_CANCEL_RENDER_JOB_DESC
    )
    job_id: str


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
    return [
        {
            "name": name,
            "description": TOOL_DESCRIPTIONS[name],
            "input_schema": model.model_json_schema(),
        }
        for name, model in TOOL_REGISTRY.items()
    ]
