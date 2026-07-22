"""LLM provider registry (Wave 3).

Centralizes the provider name → streaming-implementation mapping that
used to live as a 6-branch if/elif in ``stream_chat``. Adding a new
provider is one entry here, not a surgery in ``llm.py``.

The :class:`ProviderSpec` dataclass captures everything the dispatcher
needs:
- ``name`` — canonical provider name (matches ``ProviderName`` in
  ``llm_config.py``)
- ``is_cli`` — True for the four providers that shell out to a CLI
  binary (pi, opencode, antigravity, jcode); False for SDK providers
  (anthropic, openai)
- ``stream`` — async generator function matching the
  ``_stream_openai`` / ``_stream_anthropic`` / ``_stream_cli`` /
  ``_stream_pi`` shape. For CLI providers the dispatcher pulls the
  matching ``CLIAdapter`` and passes it to ``_stream_cli``; for SDK
  providers the registered stream function is called directly.
- ``missing_error`` — message yielded by ``stream_chat`` when the
  provider is selected but cannot run (missing SDK, missing API key,
  missing CLI binary). The dispatcher wraps the stream call in the
  same try/except pattern that used to be copy-pasted per branch.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    is_cli: bool
    stream: Callable[..., Awaitable[Iterator[dict]]]
    missing_error: str  # yielded as {"type": "error", "message": ...}


# --- Imported lazily so a missing SDK doesn't break server startup. ---

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
        is_cli=False,
        stream=_anthropic_stream(),
        missing_error=(
            "anthropic provider: required package not installed or "
            "ANTHROPIC_API_KEY missing. Install with `pip install anthropic` "
            "and set the key in Settings or as ANTHROPIC_API_KEY env var."
        ),
    ),
    "openai": ProviderSpec(
        name="openai",
        is_cli=False,
        stream=_openai_stream(),
        missing_error=(
            "openai provider: required package not installed or "
            "OPENAI_API_KEY missing. Install with `pip install openai` "
            "and set the key in Settings or as OPENAI_API_KEY env var."
        ),
    ),
    "pi": ProviderSpec(
        name="pi",
        is_cli=True,
        stream=_pi_stream(),
        missing_error=(
            "pi provider: `pi` binary not found on PATH. Install pi "
            "(see https://github.com/badlogic/pi-mono) and ensure the "
            "binary is on PATH, or set OPEN_EDIT_PI_BINARY."
        ),
    ),
    "opencode": ProviderSpec(
        name="opencode",
        is_cli=True,
        stream=_cli_stream(),
        missing_error=(
            "opencode provider: `opencode` binary not found on PATH. "
            "Install opencode (see https://opencode.ai) and ensure the "
            "binary is on PATH."
        ),
    ),
    "antigravity": ProviderSpec(
        name="antigravity",
        is_cli=True,
        stream=_cli_stream(),
        missing_error=(
            "antigravity provider: `antigravity` binary not found on "
            "PATH. Install antigravity and ensure the binary is on PATH."
        ),
    ),
    "jcode": ProviderSpec(
        name="jcode",
        is_cli=True,
        stream=_cli_stream(),
        missing_error=(
            "jcode provider: `jcode` binary not found on PATH. Install "
            "jcode and ensure the binary is on PATH."
        ),
    ),
}


def resolve_provider(name: str) -> ProviderSpec:
    """Return the :class:`ProviderSpec` for ``name``. Raises ``KeyError``
    with a helpful message if the name is not registered."""
    if name not in PROVIDERS:
        registered = ", ".join(sorted(PROVIDERS))
        raise KeyError(
            f"unknown LLM provider: {name!r}; expected one of: {registered}"
        )
    return PROVIDERS[name]


def list_provider_specs() -> list[ProviderSpec]:
    """All registered providers, sorted by name. Used by the UI to render
    the provider dropdown without re-implementing the list elsewhere."""
    return sorted(PROVIDERS.values(), key=lambda s: s.name)
