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
    "set_pinned_value, import_asset). Use ``generate`` to produce "
    "creative suggestions (SFX, music, visuals, silence cuts) that "
    "are returned for review — commit them later via "
    "``operation=\"apply_generated_ops\"``."
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
    "the final cut'. Modes: 'proxy' (fast, low-res preview), "
    "'final' (full quality), or 'overlay' (v1.6 HTML overlay "
    "composited pipeline; requires at least one HtmlOverlay in "
    "the timeline). Returns the output path when done. This is a "
    "server-side tool — it is handled by the agent loop, not by "
    "open_edit.agent.tools."
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
    ]
    params: dict = {}


class EditProjectArgs(BaseModel):
    model_config = ConfigDict(
        extra="forbid", title="edit_project", description=_EDIT_PROJECT_DESC
    )
    operation: Optional[str] = None
    params: dict = {}
    generate: Optional[Literal["sfx", "music", "visual", "silence_cuts"]] = None
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
