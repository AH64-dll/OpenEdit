"""Tests for the pillar tools dispatch functions."""
from __future__ import annotations

from pathlib import Path

import pytest

from open_edit.serve.pillar_tools import dispatch_query, dispatch_edit, dispatch_generate


def test_dispatch_query_unknown():
    result = dispatch_query("nonexistent", {}, Path("/tmp"))
    assert result["status"] == "error"
    assert "unknown query" in result["error"]


def test_dispatch_edit_unknown():
    result = dispatch_edit("nonexistent", {}, Path("/tmp"))
    assert result["status"] == "error"
    assert "unknown operation" in result["error"]


def test_dispatch_generate_unknown():
    result = dispatch_generate("nonexistent", {}, Path("/tmp"))
    assert result["status"] == "error"
    assert "unknown generate kind" in result["error"]


def test_tool_by_name_has_pillar_names():
    from open_edit.serve.tool_schemas import TOOL_BY_NAME
    assert "query_project" in TOOL_BY_NAME
    assert "edit_project" in TOOL_BY_NAME
    assert "run_script" in TOOL_BY_NAME
    assert "trigger_render" in TOOL_BY_NAME
    # Old names are NOT in TOOL_BY_NAME — they skip validation
    # and resolve via getattr in the dispatch layer.
    assert "list_assets" not in TOOL_BY_NAME
    assert "run_python" not in TOOL_BY_NAME


def test_tool_schemas_has_4():
    from open_edit.serve.tool_schemas import TOOL_SCHEMAS
    assert len(TOOL_SCHEMAS) == 4


def test_run_script_importable():
    from open_edit.agent.tools import run_script
    assert callable(run_script)


def test_run_python_importable():
    from open_edit.agent.tools import run_python
    assert callable(run_python)
