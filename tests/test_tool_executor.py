"""Tests for the shared tool executor (Wave 3.2)."""
from __future__ import annotations

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
    assert "assets" in result or "items" in result or "ok" in result


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
        "open_edit.kernel.render_service.DEFAULT_RENDER_SERVICE", mock_svc,
    ), pytest.raises(RuntimeError, match="boom"):
        await execute_trigger_render(args={}, project_path=tmp_path)
