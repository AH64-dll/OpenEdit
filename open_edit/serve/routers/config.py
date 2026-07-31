"""Config routes: llm-config, runtimes, keys, ui-config, provider models."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import llm_config as llm_config_mod
from ..auth import _check_rate_limit
from ..review_mode import auto_proxy_enabled, is_review_only
from .projects import _require_project

router = APIRouter()


class LLMConfigRequest(BaseModel):
    provider: str
    model: str


class LLMConfigResponse(BaseModel):
    provider: str
    model: str
    available_providers: list[str]
    available_models: list[str]
    provider_capabilities: list[dict[str, Any]] = Field(default_factory=list)


class SaveKeyRequest(BaseModel):
    provider: str
    key: str


def _require_agent_mode() -> None:
    if is_review_only():
        raise HTTPException(status_code=404, detail="not available in review-only mode")


@router.get("/api/ui-config")
async def get_ui_config() -> dict[str, Any]:
    """Frontend mode flags (review studio vs full agent UI)."""
    return {
        "mode": "review" if is_review_only() else "full",
        "review_only": is_review_only(),
        "auto_proxy": auto_proxy_enabled(),
    }


@router.get("/api/projects/{project_id}/llm-config")
async def get_llm_config(project_id: str) -> LLMConfigResponse:
    """Return the project's LLM provider + model config."""
    _require_agent_mode()
    state = await _require_project(project_id)
    project_path = Path(state.path)
    from .. import providers as providers_mod

    try:
        cfg = llm_config_mod.load_llm_config(project_path)
    except llm_config_mod.LLMConfigError as exc:
        raise HTTPException(status_code=500, detail=f"invalid LLM config: {exc}") from exc
    available_models = await asyncio.to_thread(providers_mod.get_provider_models, cfg.provider)
    capabilities = [
        {
            "id": spec.name,
            "label": spec.label,
            "agent_mode": spec.agent_mode,
            "supports_tools": spec.supports_tools,
            "supports_sessions": spec.supports_sessions,
            "context_strategy": spec.context_strategy,
        }
        for spec in providers_mod.list_visible_providers()
    ]
    return LLMConfigResponse(
        provider=cfg.provider,
        model=cfg.model,
        available_providers=[s.name for s in providers_mod.list_visible_providers()],
        available_models=available_models,
        provider_capabilities=capabilities,
    )


@router.put("/api/projects/{project_id}/llm-config")
async def put_llm_config(project_id: str, req: LLMConfigRequest) -> LLMConfigResponse:
    """Persist the project's LLM provider + model config."""
    _require_agent_mode()
    from .. import providers as providers_mod

    visible = [s.name for s in providers_mod.list_visible_providers()]
    if req.provider not in visible:
        raise HTTPException(
            status_code=400,
            detail=(
                f"unknown provider {req.provider!r}; "
                f"expected one of: {', '.join(visible)}."
            ),
        )
    if not req.model or not req.model.strip():
        raise HTTPException(status_code=400, detail="model must be a non-empty string")
    state = await _require_project(project_id)
    project_path = Path(state.path)
    cfg = llm_config_mod.LLMConfig(provider=req.provider, model=req.model.strip())
    try:
        llm_config_mod.save_llm_config(project_path, cfg)
    except (llm_config_mod.LLMConfigError, OSError) as exc:
        raise HTTPException(status_code=500, detail=f"failed to save LLM config: {exc}") from exc
    avail_models = await asyncio.to_thread(providers_mod.get_provider_models, cfg.provider)
    capabilities = [
        {
            "id": spec.name,
            "label": spec.label,
            "agent_mode": spec.agent_mode,
            "supports_tools": spec.supports_tools,
            "supports_sessions": spec.supports_sessions,
            "context_strategy": spec.context_strategy,
        }
        for spec in providers_mod.list_visible_providers()
    ]
    return LLMConfigResponse(
        provider=cfg.provider,
        model=cfg.model,
        available_providers=visible,
        available_models=avail_models,
        provider_capabilities=capabilities,
    )


@router.get("/api/runtimes")
async def list_discovered_runtimes() -> JSONResponse:
    """Return auto-discovered CLI runtimes across system PATH and GUI directories."""
    _require_agent_mode()
    from ..runtimes.registry import discover_runtimes
    runtimes = discover_runtimes()
    return JSONResponse({"runtimes": [r.to_dict() for r in runtimes]})


@router.get("/api/settings/keys")
async def get_settings_keys() -> JSONResponse:
    """Return masked status summary of API keys (from env or ~/.open_edit/keys.json)."""
    _require_agent_mode()
    from ..runtimes.keys_store import get_masked_keys_summary
    return JSONResponse(get_masked_keys_summary())


@router.put("/api/settings/keys")
async def put_settings_key(req: SaveKeyRequest) -> JSONResponse:
    """Save an API key to ~/.open_edit/keys.json with 0600 permissions."""
    _require_agent_mode()
    _check_rate_limit("settings:keys", max_requests=10, window_sec=60)
    from ..runtimes.keys_store import get_masked_keys_summary, save_stored_key
    provider = req.provider.strip().lower()
    if not provider:
        raise HTTPException(status_code=400, detail="provider is required")
    save_stored_key(provider, req.key)
    return JSONResponse({
        "status": "saved",
        "provider": provider,
        "keys": get_masked_keys_summary(),
    })


@router.get("/api/llm/providers/{provider}/models")
async def get_provider_models(provider: str) -> dict[str, list[str]]:
    """Return available models for a given provider."""
    _require_agent_mode()
    from .. import providers as providers_mod
    models = await asyncio.to_thread(providers_mod.get_provider_models, provider)
    return {"models": models}
