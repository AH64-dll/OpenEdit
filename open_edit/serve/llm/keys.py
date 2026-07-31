"""Key / model / provider resolution for the LLM client."""
from __future__ import annotations

import os
from pathlib import Path


def _api_key(provider: str | None = None) -> str:
    """Resolve an API key for *provider*.

    Resolution order (first non-empty wins):
    1. ``<PROVIDER>_API_KEY`` env var (e.g. ``ANTHROPIC_API_KEY``).
    2. ``OPEN_EDIT_LLM_API_KEY`` only when ``OPEN_EDIT_LLM_API_KEY_PROVIDER``
       explicitly names this provider.
    3. Per-provider stored key from ``~/.open_edit/keys.json``.

    Never falls through to another provider's key or env var.
    """
    if not provider:
        raise RuntimeError("_api_key requires a provider name")
    # 1. Provider-specific env var.
    provider_upper = provider.upper().replace("-", "_")
    for var in (f"{provider_upper}_API_KEY", f"OPEN_EDIT_{provider_upper}_KEY"):
        val = os.environ.get(var, "").strip()
        if val:
            return val
    # 2. A generic override is intentionally provider-scoped.  Without the
    # companion selector, a key left over for another provider could be sent
    # to the wrong SDK.
    val = os.environ.get("OPEN_EDIT_LLM_API_KEY", "").strip()
    override_provider = os.environ.get("OPEN_EDIT_LLM_API_KEY_PROVIDER", "").strip().lower()
    # OPEN_EDIT_LLM_PROVIDER is the legacy explicit global selection. It is
    # safe as an override scope only when it names the same provider; per-
    # project callers should set OPEN_EDIT_LLM_API_KEY_PROVIDER explicitly.
    selected_provider = _provider()
    if val and (override_provider == provider.lower() or (
        not override_provider and selected_provider == provider.lower()
    )):
        return val
    # 3. Stored key.
    from ..runtimes.keys_store import get_stored_key
    val = get_stored_key(provider) or ""
    if val:
        return val
    p_title = provider.lower()
    raise RuntimeError(
        f"{p_title} provider: no API key found. "
        f"Set {provider_upper}_API_KEY or configure a key in Settings (⚙️)."
    )


def _model() -> str:
    return os.environ.get("OPEN_EDIT_LLM_MODEL", "claude-sonnet-4-5").strip()


def _provider() -> str:
    return os.environ.get("OPEN_EDIT_LLM_PROVIDER", "anthropic").strip().lower()


def _max_tokens() -> int:
    try:
        return int(os.environ.get("OPEN_EDIT_LLM_MAX_TOKENS", "4096"))
    except ValueError:
        return 4096


def effective_provider(project_path: str | None) -> str:
    """Resolve the provider that ``stream_chat`` would use for this project.

    Mirrors the resolution order inside ``stream_chat``: per-project
    ``.open_edit/config.toml`` (if present and valid) beats the
    ``OPEN_EDIT_LLM_PROVIDER`` env var. The agent loop needs this to
    decide whether the provider owns the agent loop (CLI providers)
    before it starts streaming — it cannot learn it from the event
    stream itself.
    """
    if project_path is not None:
        try:
            proj_dir = Path(project_path)
        except (TypeError, ValueError):
            proj_dir = None  # type: ignore[assignment]
        if proj_dir is not None and (proj_dir / ".open_edit" / "config.toml").is_file():
            try:
                from ..llm_config import load_llm_config
                cfg = load_llm_config(proj_dir)
                if cfg.provider:
                    return cfg.provider
            except Exception:
                pass  # fall back to env on any error
    return _provider()
