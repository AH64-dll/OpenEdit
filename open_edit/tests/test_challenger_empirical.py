"""Empirical verification test suite written by Challenger 2.

Covers:
- GET /api/health returning 200 OK {"status": "ok"}
- PUT /api/projects/{id}/llm-config OSError handling & structured 500 JSON response
- stream_chat transient network error retry handling (ConnectionError, TimeoutError, APIConnectionError)
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from open_edit.serve import llm_config
from open_edit.serve.app import app
from open_edit.serve.llm import stream_chat
from open_edit.serve.providers import ProviderSpec, PROVIDERS


@pytest.fixture
def client_and_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, str, str]:
    monkeypatch.setenv("OPEN_EDIT_PROJECTS_ROOT", str(tmp_path))
    from open_edit.serve import projects as projects_mod

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        info = loop.run_until_complete(projects_mod.create_project("challenger_test_proj"))
        state = loop.run_until_complete(projects_mod.get_project_state(info.id))
    finally:
        loop.close()
    return TestClient(app), state.path, info.id


def test_health_endpoint_returns_200_ok(client_and_project: tuple[TestClient, str, str]) -> None:
    client, _, _ = client_and_project
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_put_llm_config_oserror_handling(
    client_and_project: tuple[TestClient, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _, project_id = client_and_project

    def failing_save(*args, **kwargs):
        raise OSError("[Errno 13] Permission denied: '/dummy/config.toml'")

    monkeypatch.setattr(llm_config, "save_llm_config", failing_save)

    res = client.put(
        f"/api/projects/{project_id}/llm-config",
        json={"provider": "pi", "model": "minimax-m3"},
    )
    assert res.status_code == 500
    body = res.json()
    assert "error" in body
    assert "failed to save LLM config: [Errno 13] Permission denied" in body["error"]


@pytest.mark.asyncio
async def test_llm_transient_network_error_retry_and_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test stream_chat retries transient network errors when events_yielded == 0."""
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "mock_transient_provider")
    monkeypatch.setenv("OPEN_EDIT_LLM_MODEL", "mock-model")

    call_count = 0

    async def mock_stream(messages, tools, system, model):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("Flaky network connection lost")
        elif call_count == 2:
            raise TimeoutError("Read timeout")
        yield {"type": "text_delta", "text": "Success after retry"}

    spec = ProviderSpec(
        name="mock_transient_provider",
        is_cli=False,
        stream=mock_stream,
        missing_error="mock error"
    )

    with patch.dict(PROVIDERS, {"mock_transient_provider": spec}):
        events = []
        async for ev in stream_chat(messages=[], tools=[], system=""):
            events.append(ev)

        assert call_count == 3
        assert len(events) == 1
        assert events[0] == {"type": "text_delta", "text": "Success after retry"}


@pytest.mark.asyncio
async def test_llm_transient_network_error_retry_exhaustion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test stream_chat yields structured error after retries exhausted (3 attempts total)."""
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "mock_transient_exhaust")
    monkeypatch.setenv("OPEN_EDIT_LLM_MODEL", "mock-model")

    call_count = 0

    async def mock_stream(messages, tools, system, model):
        nonlocal call_count
        call_count += 1
        if False:
            yield {}
        raise ConnectionError("Persistent network outage")

    spec = ProviderSpec(
        name="mock_transient_exhaust",
        is_cli=False,
        stream=mock_stream,
        missing_error="mock error"
    )

    with patch.dict(PROVIDERS, {"mock_transient_exhaust": spec}):
        events = []
        async for ev in stream_chat(messages=[], tools=[], system=""):
            events.append(ev)

        assert call_count == 3  # Initial + 2 retries
        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert "mock_transient_exhaust network error: Persistent network outage" in events[0]["message"]


@pytest.mark.asyncio
async def test_llm_no_retry_if_events_already_yielded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test stream_chat does NOT retry if error occurs mid-stream (events_yielded > 0)."""
    monkeypatch.setenv("OPEN_EDIT_LLM_PROVIDER", "mock_mid_stream_fail")

    call_count = 0

    async def mock_stream(messages, tools, system, model):
        nonlocal call_count
        call_count += 1
        yield {"type": "text_delta", "text": "Partial message"}
        raise ConnectionError("Broken connection mid-stream")

    spec = ProviderSpec(
        name="mock_mid_stream_fail",
        is_cli=False,
        stream=mock_stream,
        missing_error="mock error"
    )

    with patch.dict(PROVIDERS, {"mock_mid_stream_fail": spec}):
        events = []
        async for ev in stream_chat(messages=[], tools=[], system=""):
            events.append(ev)

        assert call_count == 1  # No retry because events_yielded > 0
        assert len(events) == 2
        assert events[0] == {"type": "text_delta", "text": "Partial message"}
        assert events[1]["type"] == "error"
