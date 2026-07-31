from __future__ import annotations

import json

from open_edit.kernel.tool_registry import build_tool_schemas


def test_build_tool_schemas_names():
    schemas = build_tool_schemas()
    assert len(schemas) == 6
    names = {s["name"] for s in schemas}
    assert names == {
        "query_project",
        "edit_project",
        "run_script",
        "trigger_render",
        "get_render_job",
        "cancel_render_job",
    }


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


def test_every_schema_tool_resolves_in_tool_table():
    """Every TOOL_SCHEMAS name is a plain TOOL_TABLE entry or kernel-handled.

    Kernel-handled names (pillar dispatchers, render-service branches, the
    virtual trigger_render) live in ``kernel.tool_executor`` — the set is
    pinned there as ``_KERNEL_HANDLED_TOOLS`` so the two can never drift.
    """
    from open_edit.agent.tools import TOOL_TABLE
    from open_edit.kernel.tool_executor import _KERNEL_HANDLED_TOOLS
    from open_edit.kernel.tool_schemas import TOOL_SCHEMAS

    for schema in TOOL_SCHEMAS:
        name = schema["name"]
        assert name in TOOL_TABLE or name in _KERNEL_HANDLED_TOOLS, name
    assert not (set(TOOL_TABLE) & set(_KERNEL_HANDLED_TOOLS))


def test_tool_table_entries_all_callable():
    from open_edit.agent.tools import TOOL_TABLE

    assert len(TOOL_TABLE) == 26
    for name, fn in TOOL_TABLE.items():
        assert callable(fn), name


def test_tool_table_covers_all_reexports():
    from open_edit.agent.tools import TOOL_TABLE, __all__

    assert set(__all__) <= set(TOOL_TABLE)
