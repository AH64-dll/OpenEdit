"""Pydantic-backed registry of Open Edit pillar tool argument schemas.

Single source of truth for the 4 pillar tools' argument shapes, JSON
schema generation, and LLM tool-call validation.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


_QUERY_PROJECT_DESC = (
    "Read-only queries about the project. Use this for ALL "
    "read-only operations — listing assets, pending notes, style "
    "profile, narrative analysis, and asset search."
)

_EDIT_PROJECT_DESC = (
    "Apply edits to the project or generate creative suggestions. "
    "Use ``operation`` for immediate mutations (add_marker, "
    "set_pinned_value, import_asset, ingest_local). Use ``generate`` to produce "
    "creative suggestions (SFX, music, visuals, remotion, silence cuts) "
    "that are returned for review — commit them later via "
    "``operation=\"apply_generated_ops\"``. "
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
    "Returns the output path when done. This is a server-side tool "
    "— it is handled by the agent loop, not by open_edit.agent.tools."
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


TOOL_REGISTRY: dict[str, type[BaseModel]] = {
    "query_project": QueryProjectArgs,
    "edit_project": EditProjectArgs,
    "run_script": RunScriptArgs,
    "trigger_render": TriggerRenderArgs,
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


def validate_tool_args(name: str, args: dict) -> dict:
    """Validate LLM tool-call args against the registered model.

    Raises ``ValueError`` for unknown tool names or invalid arguments.
    """
    model = TOOL_REGISTRY.get(name)
    if model is None:
        raise ValueError(f"Unknown tool: {name!r}")
    try:
        parsed = model(**args)
    except Exception as exc:
        raise ValueError(f"Invalid arguments for tool {name!r}: {exc}") from exc
    return parsed.model_dump()
