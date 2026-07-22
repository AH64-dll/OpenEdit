"""Tests for the shared tool executor (Wave 3.2)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest import mock

import pytest

from open_edit.serve.tool_executor import (
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
    assert "assets" in result or "items" in result or "ok" in result


def test_execute_tool_unknown_raises(tmp_path: Path):
    with pytest.raises(ToolNotFound) as exc:
        execute_tool(name="definitely_not_a_tool", args={}, project_path=tmp_path)
    assert "definitely_not_a_tool" in str(exc.value)


def test_execute_trigger_render_missing_args(tmp_path: Path):
    """Server-side virtual tool: subprocess failure must surface as a
    clear error (not 500). We mock ``subprocess.run`` to force the
    error path so the test is deterministic regardless of whether
    the real ``open_edit`` CLI is installed in the test env.

    v1.6 behavior: an empty ``args`` dict defaults ``mode`` to
    ``"proxy"`` and shells out. The RuntimeError is what
    ``test_serve_agent.py::test_execute_trigger_render_in_process_*``
    relies on — it must still be raised.
    """
    boom = subprocess.CalledProcessError(returncode=1, cmd=["open_edit", "render"], stderr="boom")
    with mock.patch("subprocess.run", side_effect=boom), \
         pytest.raises((ValueError, KeyError, RuntimeError)) as exc:
        execute_trigger_render(args={}, project_path=tmp_path)
    assert "open_edit render" in str(exc.value)
