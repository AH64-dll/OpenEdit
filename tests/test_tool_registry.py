from __future__ import annotations

import json

from open_edit.kernel.tool_registry import build_tool_schemas


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


def test_tool_schemas_json_serializable():
    from open_edit.kernel.tool_schemas import TOOL_SCHEMAS

    json.dumps(TOOL_SCHEMAS)
