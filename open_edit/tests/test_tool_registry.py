from __future__ import annotations

import json

import pytest

from open_edit.serve.tool_registry import build_tool_schemas, validate_tool_args


def test_build_tool_schemas_names():
    schemas = build_tool_schemas()
    assert len(schemas) == 4
    names = {s["name"] for s in schemas}
    assert names == {"query_project", "edit_project", "run_script", "trigger_render"}


def test_schema_additional_properties_and_required():
    by_name = {s["name"]: s["input_schema"] for s in build_tool_schemas()}
    for schema in by_name.values():
        assert schema["additionalProperties"] is False
        assert schema["type"] == "object"
    assert set(by_name["run_script"]["required"]) == {"code"}
    assert set(by_name["query_project"]["required"]) == {"query"}


def test_validate_run_script_defaults():
    assert validate_tool_args("run_script", {"code": "x"}) == {
        "code": "x",
        "timeout_sec": 30,
    }


def test_validate_run_script_extra_forbidden():
    with pytest.raises(ValueError):
        validate_tool_args("run_script", {"code": "x", "bogus": 1})


def test_validate_query_project_bad_enum():
    with pytest.raises(ValueError):
        validate_tool_args("query_project", {"query": "bogus"})


def test_validate_unknown_tool():
    with pytest.raises(ValueError):
        validate_tool_args("unknown", {})


def test_tool_schemas_json_serializable():
    from open_edit.serve.tool_schemas import TOOL_SCHEMAS

    json.dumps(TOOL_SCHEMAS)
