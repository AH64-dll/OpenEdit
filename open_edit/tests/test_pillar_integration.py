"""Integration tests for the 4 pillar tools through the dispatch layer."""
from __future__ import annotations

import pytest

from open_edit.serve.schema_validator import validate_or_error
from open_edit.serve.tool_executor import execute_tool
from open_edit.serve.tool_schemas import TOOL_SCHEMAS


def test_4_pillar_schemas():
    assert len(TOOL_SCHEMAS) == 4
    names = {t["name"] for t in TOOL_SCHEMAS}
    assert names == {"query_project", "edit_project", "run_script", "trigger_render"}


def test_query_project_unknown_query(tmp_path):
    result = execute_tool("query_project", {"query": "nonexistent"}, tmp_path)
    assert result.get("status") == "error"
    assert "unknown query" in result.get("error", "")


def test_edit_project_unknown_operation(tmp_path):
    result = execute_tool("edit_project", {"operation": "nonexistent"}, tmp_path)
    assert result.get("status") == "error"
    assert "unknown operation" in result.get("error", "")


def test_edit_project_generate_unknown(tmp_path):
    result = execute_tool("edit_project", {"generate": "nonexistent"}, tmp_path)
    assert result.get("status") == "error"
    assert "unknown generate kind" in result.get("error", "")


def test_run_script_validate(tmp_path):
    err = validate_or_error("run_script", {"code": "print('hello')"})
    assert err is None


def test_run_script_validate_missing_code():
    err = validate_or_error("run_script", {})
    assert err is not None
    assert "missing required" in str(err).lower()



