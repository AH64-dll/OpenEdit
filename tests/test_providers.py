"""Tests for the LLM provider registry."""
from __future__ import annotations

import pytest

from open_edit.serve.providers import (
    PROVIDERS,
    ProviderSpec,
    list_provider_specs,
    list_visible_providers,
    provider_default_model,
    resolve_provider,
)


def test_all_known_providers_registered():
    names = {p.name for p in PROVIDERS.values()}
    assert names == {"anthropic", "openai", "pi", "opencode", "antigravity", "jcode"}


def test_resolve_provider_known():
    spec = resolve_provider("opencode")
    assert isinstance(spec, ProviderSpec)
    assert spec.name == "opencode"
    assert spec.transport == "cli"
    assert spec.stream is not None


def test_resolve_provider_unknown_raises():
    with pytest.raises(KeyError) as exc:
        resolve_provider("not-a-provider")
    assert "not-a-provider" in str(exc.value)


def test_anthropic_uses_sdk_not_cli():
    spec = resolve_provider("anthropic")
    assert spec.transport == "sdk"


def test_list_provider_specs_sorted_by_name():
    specs = list_provider_specs()
    assert [s.name for s in specs] == sorted(s.name for s in specs)


def test_cli_providers_have_callable_stream():
    for name in ("pi", "opencode", "antigravity", "jcode"):
        spec = resolve_provider(name)
        assert spec.transport == "cli"
        assert callable(spec.stream)


def test_jcode_is_hidden():
    spec = resolve_provider("jcode")
    assert spec.hidden is True


def test_visible_providers_excludes_hidden():
    visible = {s.name for s in list_visible_providers()}
    assert "jcode" not in visible
    assert "anthropic" in visible
    assert "openai" in visible


def test_provider_default_model():
    assert provider_default_model("anthropic") == "claude-sonnet-4-5"
    assert provider_default_model("openai") == "gpt-4o"
    assert provider_default_model("unknown") == ""


def test_provider_model_endpoint_handles_all_providers():
    from fastapi.testclient import TestClient
    from open_edit.serve.app import app
    client = TestClient(app)
    for spec in list_provider_specs():
        resp = client.get(f"/api/llm/providers/{spec.name}/models")
        assert resp.status_code in (200, 404), (
            f"{spec.name}: {resp.status_code} {resp.text}"
        )


def test_all_providers_have_label():
    for spec in PROVIDERS.values():
        assert spec.label, f"{spec.name} missing label"


def test_context_strategies_match_capabilities():
    """OE-P1-007: every provider declares an explicit context strategy."""
    assert resolve_provider("pi").context_strategy == "native_session"
    assert resolve_provider("opencode").context_strategy == "full_history"
    assert resolve_provider("antigravity").context_strategy == "full_history"
    assert resolve_provider("anthropic").context_strategy == "full_history"
    assert resolve_provider("openai").context_strategy == "full_history"
    assert resolve_provider("jcode").context_strategy == "stateless"
    for spec in list_visible_providers():
        assert spec.context_strategy in {
            "native_session",
            "full_history",
            "stateless",
        }


def test_sdk_providers_require_no_binary():
    for spec in PROVIDERS.values():
        if spec.transport == "sdk":
            assert len(spec.binary_names) == 0, (
                f"{spec.name}: SDK provider should not list binaries"
            )


def test_every_runtime_registry_entry_derives_from_provider():
    from open_edit.serve.runtimes.registry import discover_runtimes
    runtimes = discover_runtimes()
    runtime_ids = {r.id for r in runtimes}
    provider_ids = set(PROVIDERS)
    assert runtime_ids == provider_ids, (
        f"runtime ids {runtime_ids} != provider ids {provider_ids}"
    )
    for rt in runtimes:
        pspec = PROVIDERS[rt.id]
        assert rt.name == pspec.label


def test_every_provider_has_adapter_and_env_keys():
    from open_edit.serve.providers import PROVIDERS
    from open_edit.serve.cli_adapter import get_adapter
    from open_edit.serve.runtimes.keys_store import env_map
    for pid in PROVIDERS:
        assert get_adapter(pid) is not None, pid
        assert pid in env_map, pid


def test_anthropic_and_openai_appear_in_api_llm_config():
    """Regression: Anthropic and OpenAI must be in the available_providers
    list returned by the GET llm-config endpoint."""
    from fastapi.testclient import TestClient
    from open_edit.serve.app import app
    from open_edit.serve import projects as projects_mod
    import asyncio, tempfile, os

    tmp = tempfile.mkdtemp()
    os.environ["OPEN_EDIT_PROJECTS_ROOT"] = tmp
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        info = loop.run_until_complete(projects_mod.create_project("regr_test"))
        pid = info.id
    finally:
        loop.close()
    client = TestClient(app)
    r = client.get(f"/api/projects/{pid}/llm-config")
    assert r.status_code == 200, r.text
    provs = r.json()["available_providers"]
    assert "anthropic" in provs, f"anthropic missing from {provs}"
    assert "openai" in provs, f"openai missing from {provs}"
    assert "jcode" not in provs, "jcode must be hidden"
