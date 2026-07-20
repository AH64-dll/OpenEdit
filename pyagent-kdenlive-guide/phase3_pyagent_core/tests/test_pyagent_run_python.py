"""Phase 4 Task 7: pyagent_run_python tool."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from open_edit.agent.exceptions import FreeFormResult
from open_edit.agent.tools.pyagent_run_python import run_python


def _make_project_dir(tmp_path: Path) -> Path:
    project_path = tmp_path / "project"
    project_path.mkdir()
    (project_path / "edit_graph.db").touch()
    return project_path


def test_run_python_success(tmp_path):
    project_path = _make_project_dir(tmp_path)
    args = {
        "code": "ir.add_clip(asset_hash='abc', track_id='t1', position_sec=0.0)",
        "project_id": "p1",
        "project_path": str(project_path / "fake.kdenlive"),
    }
    fake_result = FreeFormResult.ok(ops=[], duration_s=0.1)
    with patch(
        "open_edit.agent.tools.pyagent_run_python.run_free_form",
        return_value=fake_result,
    ) as mock_run:
        response = run_python(args, str(project_path))
    assert response["status"] == "ok"
    assert response["ops"] == []
    assert response["error"] is None
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["code"] == args["code"]
    assert call_kwargs["project_id"] == "p1"


def test_run_python_failure(tmp_path):
    project_path = _make_project_dir(tmp_path)
    args = {
        "code": "raise RuntimeError('boom')",
        "project_id": "p1",
        "project_path": str(project_path / "fake.kdenlive"),
    }
    fake_result = FreeFormResult.fail("sandbox_protocol_error", "no JSON")
    with patch(
        "open_edit.agent.tools.pyagent_run_python.run_free_form",
        return_value=fake_result,
    ):
        response = run_python(args, str(project_path))
    assert response["status"] == "error"
    assert "sandbox_protocol_error" in response["error"]


def test_run_python_passes_timeout_and_mem(tmp_path):
    project_path = _make_project_dir(tmp_path)
    args = {
        "code": "ir.add_clip(asset_hash='abc', track_id='t1')",
        "project_id": "p1",
        "project_path": str(project_path / "fake.kdenlive"),
        "timeout_sec": 60,
        "mem_mb": 1024,
    }
    fake_result = FreeFormResult.ok(ops=[], duration_s=0.0)
    with patch(
        "open_edit.agent.tools.pyagent_run_python.run_free_form",
        return_value=fake_result,
    ) as mock_run:
        run_python(args, str(project_path))
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["timeout"] == 60
    assert call_kwargs["mem_mb"] == 1024
