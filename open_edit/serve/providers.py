"""LLM provider registry — single source of truth.

Centralises the provider name → implementation mapping that used to
live as a 6-branch if/elif in ``stream_chat`` or duplicated across
``cli_adapter.py``, ``llm_config.py``, and ``runtimes/registry.py``.

Every provider appears in exactly one place (here). API validation,
UI dropdowns, model discovery, auth configuration, and runtime
dispatch all derive from this registry.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class ProviderSpec:
    """One LLM backend.

    All metadata the server, UI, and dispatcher need to work with
    this provider lives in this dataclass.  No other file should
    hardcode a provider name or model list.
    """

    name: str
    label: str
    transport: Literal["sdk", "cli"]

    agent_mode: str = "openedit_loop"
    hidden: bool = False

    stream: Callable[..., Awaitable[Iterator[dict]]] | None = None
    missing_error: str = ""

    default_model: str = ""
    models: tuple[str, ...] = ()

    binary_names: tuple[str, ...] = ()
    env_keys: tuple[str, ...] = ()

    supports_tools: bool = False
    supports_images: bool = False
    supports_sessions: bool = False
    # How prior turns are supplied to the model:
    # - native_session: provider keeps state via session_id (send last turn)
    # - full_history: serialize role-separated messages each turn
    # - stateless: no conversational memory (must not be an editing agent)
    context_strategy: Literal["native_session", "full_history", "stateless"] = "full_history"


def _anthropic_stream():
    from .llm import _stream_anthropic
    return _stream_anthropic


def _openai_stream():
    from .llm import _stream_openai
    return _stream_openai


def _pi_stream():
    from .llm import _stream_pi
    return _stream_pi


def _cli_stream():
    from .llm import _stream_cli
    return _stream_cli


PROVIDERS: dict[str, ProviderSpec] = {
    "anthropic": ProviderSpec(
        name="anthropic",
        label="Anthropic Claude API",
        transport="sdk",
        agent_mode="openedit_loop",
        stream=_anthropic_stream(),
        missing_error=(
            "anthropic provider: required package not installed or "
            "ANTHROPIC_API_KEY missing. Install with `pip install anthropic` "
            "and set the key in Settings or as ANTHROPIC_API_KEY env var."
        ),
        default_model="claude-sonnet-4-5",
        models=(
            "claude-sonnet-4-5",
            "claude-3-5-sonnet-latest",
            "claude-3-5-haiku-latest",
            "claude-3-opus-latest",
        ),
        env_keys=("ANTHROPIC_API_KEY",),
        supports_tools=True,
        supports_images=True,
        context_strategy="full_history",
    ),
    "openai": ProviderSpec(
        name="openai",
        label="OpenAI API",
        transport="sdk",
        agent_mode="openedit_loop",
        stream=_openai_stream(),
        missing_error=(
            "openai provider: required package not installed or "
            "OPENAI_API_KEY missing. Install with `pip install openai` "
            "and set the key in Settings or as OPENAI_API_KEY env var."
        ),
        default_model="gpt-4o",
        models=("gpt-4o", "gpt-4o-mini", "o3-mini"),
        env_keys=("OPENAI_API_KEY",),
        supports_tools=True,
        supports_images=True,
        context_strategy="full_history",
    ),
    "pi": ProviderSpec(
        name="pi",
        label="Pi Agent Engine",
        transport="cli",
        agent_mode="external_loop",
        stream=_pi_stream(),
        missing_error=(
            "pi provider: `pi` binary not found on PATH. Install pi "
            "(see https://github.com/badlogic/pi-mono) and ensure the "
            "binary is on PATH, or set OPEN_EDIT_PI_BINARY."
        ),
        default_model="minimax-m3",
        models=(
            "minimax-m3",
            "minimax-m2.7",
            "deepseek-v4-flash",
            "deepseek-v4-pro",
        ),
        binary_names=("pi",),
        env_keys=("PI_API_KEY",),
        supports_tools=True,
        supports_images=True,
        supports_sessions=True,
        context_strategy="native_session",
    ),
    "opencode": ProviderSpec(
        name="opencode",
        label="OpenCode CLI",
        transport="cli",
        agent_mode="chat_only",
        stream=_cli_stream(),
        missing_error=(
            "opencode provider: `opencode` binary not found on PATH. "
            "Install opencode (see https://opencode.ai) and ensure the "
            "binary is on PATH."
        ),
        default_model="opencode-go/minimax-m3",
        models=(
            "opencode-go/minimax-m3",
            "opencode-go/claude-sonnet-4-5",
            "opencode-go/deepseek-v4-pro",
        ),
        binary_names=("opencode",),
        env_keys=("OPENCODE_API_KEY", "OPEN_EDIT_LLM_API_KEY"),
        supports_tools=False,
        supports_images=False,
        context_strategy="full_history",
    ),
    "antigravity": ProviderSpec(
        name="antigravity",
        label="Antigravity (Google)",
        transport="cli",
        agent_mode="chat_only",
        stream=_cli_stream(),
        missing_error=(
            "antigravity provider: `antigravity` binary not found on "
            "PATH. Install antigravity and ensure the binary is on PATH."
        ),
        default_model="gemini-2.5-flash",
        models=(
            "gemini-2.5-flash",
            "gemini-3.5-flash-high",
            "gemini-3.5-flash-medium",
            "gemini-3.6-flash-high",
            "gemini-3.1-pro-high",
            "claude-sonnet-4.6",
            "claude-opus-4.6",
            "gpt-oss-120b",
        ),
        binary_names=("agy", "antigravity"),
        env_keys=("ANTIGRAVITY_API_KEY", "OPEN_EDIT_ANTIGRAVITY_KEY"),
        supports_tools=False,
        supports_images=False,
        context_strategy="full_history",
    ),
    "jcode": ProviderSpec(
        name="jcode",
        label="JCode CLI",
        transport="cli",
        agent_mode="chat_only",
        hidden=True,
        stream=_cli_stream(),
        missing_error=(
            "jcode provider: `jcode` binary not found on PATH. Install "
            "jcode and ensure the binary is on PATH."
        ),
        default_model="jcode-default",
        models=("jcode-default",),
        binary_names=("jcode",),
        env_keys=("JCODE_API_KEY",),
        supports_tools=False,
        supports_images=False,
        context_strategy="stateless",
    ),
}


def resolve_provider(name: str) -> ProviderSpec:
    """Return the :class:`ProviderSpec` for ``name``.

    Raises ``KeyError`` with a helpful message if not registered.
    """
    if name not in PROVIDERS:
        registered = ", ".join(sorted(PROVIDERS))
        raise KeyError(
            f"unknown LLM provider: {name!r}; expected one of: {registered}"
        )
    return PROVIDERS[name]


def list_provider_specs() -> list[ProviderSpec]:
    """All registered providers, sorted by name (including hidden)."""
    return sorted(PROVIDERS.values(), key=lambda s: s.name)


def list_visible_providers() -> list[ProviderSpec]:
    """Non-hidden providers, sorted by name.

    This is the list shown in the UI dropdown and exposed over the API.
    """
    return sorted(
        (s for s in PROVIDERS.values() if not s.hidden),
        key=lambda s: s.name,
    )


def list_provider_ids() -> list[str]:
    """Sorted provider ids (including hidden)."""
    return sorted(PROVIDERS)


def provider_default_model(name: str) -> str:
    """Return the default model for a provider, or ``""`` if unknown."""
    spec = PROVIDERS.get(name)
    return spec.default_model if spec else ""


def get_provider_models(name: str) -> list[str]:
    """Return the model list for a provider.

    For CLI providers, this may shell out to discover models
    (e.g. ``opencode models``).  Returns an empty list for unknown
    providers.
    """
    spec = PROVIDERS.get(name)
    if spec is None:
        return []
    if spec.transport == "cli":
        from .cli_adapter import get_adapter
        try:
            adapter = get_adapter(name)
            return list(adapter.available_models())
        except KeyError:
            pass
    return list(spec.models)
