"""Tests for the v1.7 CLIAdapter interface and registry."""
from __future__ import annotations

import pytest

from open_edit.serve.cli_adapter import (
    get_adapter,
    list_adapters,
)


def test_get_adapter_returns_opencode() -> None:
    a = get_adapter("opencode")
    assert a.name == "opencode"
    assert a.default_timeout_s > 0


def test_get_adapter_unknown_raises() -> None:
    with pytest.raises(KeyError, match="does_not_exist"):
        get_adapter("does_not_exist")


def test_get_adapter_unknown_raises_for_arbitrary() -> None:
    with pytest.raises(KeyError):
        get_adapter("nope")


def test_list_adapters_includes_all_providers() -> None:
    names = sorted(list_adapters())
    assert names == ["anthropic", "antigravity", "jcode", "openai", "opencode"]




def test_opencode_default_timeout_s_is_set() -> None:
    a = get_adapter("opencode")
    assert isinstance(a.default_timeout_s, int)
    assert a.default_timeout_s > 0
    assert a.default_timeout_s <= 86400




def test_opencode_supports_tools_is_false() -> None:
    """Opencode has no open_edit extension yet (v1.8+)."""
    assert get_adapter("opencode").supports_tools() is False


def test_both_adapters_manage_own_auth() -> None:
    """Q3: OpenCode reads from its own auth files."""
    assert get_adapter("opencode").manages_own_auth() is True




def test_opencode_default_model_is_opencode_go_minimax_m3() -> None:
    assert get_adapter("opencode").default_model() == "opencode-go/minimax-m3"




def test_opencode_available_models_is_list() -> None:
    """opencode.available_models shells out to `opencode models`; if the
    binary is missing on CI, it should return an empty list (not raise)."""
    models = get_adapter("opencode").available_models()
    assert isinstance(models, list)
