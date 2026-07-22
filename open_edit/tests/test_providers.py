"""Tests for the LLM provider registry."""
from __future__ import annotations

import pytest

from open_edit.serve.providers import (
    PROVIDERS,
    ProviderSpec,
    list_provider_specs,
    resolve_provider,
)


def test_all_known_providers_registered():
    names = {p.name for p in PROVIDERS.values()}
    assert names == {"anthropic", "openai", "pi", "opencode", "antigravity", "jcode"}


def test_resolve_provider_known():
    spec = resolve_provider("opencode")
    assert isinstance(spec, ProviderSpec)
    assert spec.name == "opencode"
    assert spec.is_cli is True
    assert spec.stream is not None


def test_resolve_provider_unknown_raises():
    with pytest.raises(KeyError) as exc:
        resolve_provider("not-a-provider")
    assert "not-a-provider" in str(exc.value)


def test_anthropic_uses_sdk_not_cli():
    spec = resolve_provider("anthropic")
    assert spec.is_cli is False


def test_list_provider_specs_sorted_by_name():
    specs = list_provider_specs()
    assert [s.name for s in specs] == sorted(s.name for s in specs)


def test_cli_providers_have_callable_stream():
    """All CLI providers have a stream function; the dispatcher calls it
    with the matching CLIAdapter. The pi provider uses _stream_pi (which
    wraps _stream_cli to add cost extraction); the other three use
    _stream_cli directly. The test only asserts the contract surface."""
    for name in ("pi", "opencode", "antigravity", "jcode"):
        spec = resolve_provider(name)
        assert spec.is_cli is True
        assert callable(spec.stream)
