"""Tests for the per-domain tool definitions.

These tests load every ToolDef registered across phase3_pyagent_core/tools/
and assert structural invariants. The data is consumed by Task 2.3
(extension.ts) to register the tools with pi, so a misnamed field
breaks the LLM-facing tool surface.
"""
from phase3_pyagent_core.tools import all_tools


def test_all_tools_count_is_19():
    tools = all_tools()
    assert len(tools) == 19


def test_all_tools_have_unique_names():
    tools = all_tools()
    names = [t.name for t in tools]
    assert len(names) == len(set(names)), f"duplicates: {names}"


def test_all_tools_have_required_fields():
    for t in all_tools():
        assert t.name.startswith("pyagent_"), t.name
        assert t.label, f"{t.name}: empty label"
        assert t.description, f"{t.name}: empty description"
        # Backend-routed tools have an op; render_qc tools call phase6
        # directly and have op="". Either is fine, but the field must
        # exist and be a string.
        assert isinstance(t.op, str), f"{t.name}: op not a string"
        assert isinstance(t.is_mutating, bool), f"{t.name}: is_mutating not a bool"
        assert isinstance(t.parameters_schema, dict), f"{t.name}: parameters_schema not a dict"
