"""Tests for the shared tool executor (Wave 3.2)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest import mock

import pytest

from open_edit.kernel.tool_executor import (
    ToolNotFound,
    execute_tool,
    execute_trigger_render,
)


def test_execute_tool_dispatches_to_module(tmp_path: Path):
    """A tool function in open_edit.agent.tools is called with (args, project_path_str)."""
    result = execute_tool(
        name="list_assets",
        args={},
        project_path=tmp_path,
    )
    assert isinstance(result, dict)
    assert result["status"] == "ok"
    assert "assets" in result


def test_registry_tools_accept_injected_project_id(tmp_path: Path):
    """Registry-schema tools strip the agent-loop-injected project_id before validation."""
    res = execute_tool(
        "query_project",
        {"query": "list_assets", "params": {}, "project_id": "injected"},
        tmp_path,
    )
    assert res.get("status") != "error"  # no schema_validation_failed


def test_non_registry_tools_keep_injected_project_id(tmp_path: Path):
    """The TOOL_TABLE lookup still receives project_id (callables may rely on it)."""
    captured: list[tuple[dict, str]] = []

    def fake_tool(args: dict, project_path: str) -> dict:
        captured.append((args, project_path))
        return {"ok": True}

    with mock.patch.dict("open_edit.agent.tools.TOOL_TABLE", {"list_assets": fake_tool}):
        execute_tool("list_assets", {"project_id": "injected"}, tmp_path)
    assert captured and captured[0][0].get("project_id") == "injected"


@dataclass
class _FakeRenderJob:
    """Mirror of the RenderJob dataclass fields public_job() serializes."""

    job_id: str
    project_id: str
    mode: str
    status: str
    created_at: float
    updated_at: float
    output_path: str | None = None
    error: str | None = None
    result: dict | None = None
    graph_revision: int | None = None
    edit_graph_hash: str | None = None


def test_get_render_job_dispatches_to_service(tmp_path: Path):
    """get_render_job routes to DEFAULT_RENDER_JOB_SERVICE.get + public_job envelope."""
    fake = _FakeRenderJob("j1", "proj", "proxy", "succeeded", 1.0, 2.0)
    mock_svc = mock.MagicMock()
    mock_svc.get.return_value = fake
    with mock.patch("open_edit.kernel.render_jobs.DEFAULT_RENDER_JOB_SERVICE", mock_svc):
        res = execute_tool(
            "get_render_job", {"job_id": "j1", "project_id": "injected"}, tmp_path,
        )
    assert res["ok"] is True
    assert res["job_id"] == "j1"
    assert res["status"] == "succeeded"
    mock_svc.get.assert_called_once_with(tmp_path, "j1")


def test_get_render_job_missing_job(tmp_path: Path):
    mock_svc = mock.MagicMock()
    mock_svc.get.return_value = None
    with mock.patch("open_edit.kernel.render_jobs.DEFAULT_RENDER_JOB_SERVICE", mock_svc):
        res = execute_tool("get_render_job", {"job_id": "nope"}, tmp_path)
    assert res["ok"] is False
    assert "not found" in res["error"]


def test_get_render_job_missing_id(tmp_path: Path):
    res = execute_tool("get_render_job", {}, tmp_path)
    assert res.get("ok") is False or res.get("status") == "error"
    assert "job_id" in str(res)


def test_cancel_render_job_dispatches_to_service(tmp_path: Path):
    """cancel_render_job routes to DEFAULT_RENDER_JOB_SERVICE.cancel + public_job envelope."""
    fake = _FakeRenderJob("j1", "proj", "proxy", "cancelled", 1.0, 2.0)
    mock_svc = mock.MagicMock()
    mock_svc.cancel = mock.AsyncMock(return_value=fake)
    with mock.patch("open_edit.kernel.render_jobs.DEFAULT_RENDER_JOB_SERVICE", mock_svc):
        res = execute_tool(
            "cancel_render_job", {"job_id": "j1", "project_id": "injected"}, tmp_path,
        )
    assert res["ok"] is True
    assert res["status"] == "cancelled"
    mock_svc.cancel.assert_awaited_once_with(tmp_path, "j1")


def test_cancel_render_job_missing_job(tmp_path: Path):
    mock_svc = mock.MagicMock()
    mock_svc.cancel = mock.AsyncMock(return_value=None)
    with mock.patch("open_edit.kernel.render_jobs.DEFAULT_RENDER_JOB_SERVICE", mock_svc):
        res = execute_tool("cancel_render_job", {"job_id": "nope"}, tmp_path)
    assert res["ok"] is False
    assert "not found" in res["error"]


def test_cancel_render_job_missing_id(tmp_path: Path):
    res = execute_tool("cancel_render_job", {}, tmp_path)
    assert res.get("ok") is False or res.get("status") == "error"
    assert "job_id" in str(res)


def test_execute_tool_unknown_raises(tmp_path: Path):
    with pytest.raises(ToolNotFound) as exc:
        execute_tool(name="definitely_not_a_tool", args={}, project_path=tmp_path)
    assert "definitely_not_a_tool" in str(exc.value)


@pytest.mark.asyncio
async def test_execute_trigger_render_missing_args(tmp_path: Path):
    """Enqueue rejection or render failure surfaces as RuntimeError."""
    mock_svc = mock.MagicMock()
    mock_svc.enqueue.side_effect = RuntimeError("boom")
    with mock.patch(
        "open_edit.kernel.render_jobs.DEFAULT_RENDER_JOB_SERVICE", mock_svc,
    ), pytest.raises(RuntimeError, match="boom"):
        await execute_trigger_render(args={}, project_path=tmp_path)


@pytest.mark.asyncio
async def test_execute_trigger_render_accepts_injected_project_id(tmp_path: Path):
    """trigger_render (registry-schema) strips injected project_id before validation."""
    mock_svc = mock.MagicMock()
    mock_svc.enqueue.side_effect = RuntimeError("boom")
    with mock.patch(
        "open_edit.kernel.render_jobs.DEFAULT_RENDER_JOB_SERVICE", mock_svc,
    ), pytest.raises(RuntimeError, match="boom"):
        await execute_trigger_render(
            args={"mode": "proxy", "project_id": "injected"}, project_path=tmp_path,
        )


def test_trigger_render_forwards_quality_params(tmp_path: Path, monkeypatch) -> None:
    import asyncio

    from open_edit.kernel import tool_executor
    from open_edit.kernel.render_jobs import RenderJobService

    captured: dict = {}

    def fake_enqueue(self, project_id, project_path, mode, **kwargs):
        captured.update(kwargs)
        import uuid

        from open_edit.kernel.render_jobs import RenderJob

        return RenderJob(uuid.uuid4().hex, project_id, mode, "queued", 0.0, 0.0)

    monkeypatch.setattr(RenderJobService, "enqueue", fake_enqueue)
    monkeypatch.setattr(tool_executor, "validate_or_error", lambda *a, **k: None)
    monkeypatch.setattr(tool_executor, "_strip_injected_project_id", lambda t, a: a)
    result = asyncio.run(tool_executor._run_trigger_render(
        {"mode": "final", "quality": "high", "crf": 20, "scale": "640x360", "codec": "hevc", "wait": False},
        tmp_path,
    ))
    assert result.get("ok") is True
    params = captured.get("params", {})
    assert params["quality"] == "high" and params["crf"] == 20
    assert params["codec"] == "hevc"
