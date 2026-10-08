"""Tests for schema validation layer."""
from __future__ import annotations

import pytest

from open_edit.kernel.schema_validator import (
    SchemaValidationError,
    validate_or_error,
    validate_tool_args,
)


def test_valid_args_pass():
    """query_project requires 'query' — empty args should fail."""
    err = validate_or_error("query_project", {})
    assert err is not None
    assert "missing required" in err.get("detail", "")


def test_missing_required_field():
    with pytest.raises(SchemaValidationError, match="missing required"):
        validate_tool_args("query_project", {})
    err = validate_or_error("query_project", {})
    assert err is not None
    assert err["status"] == "error"
    assert "missing required" in err["detail"]


def test_extra_field_with_additional_properties_false():
    """query_project has additionalProperties: false."""
    with pytest.raises(SchemaValidationError, match="unexpected"):
        validate_tool_args("query_project", {"query": "list_assets", "unknown_field": "value"})


def test_unknown_tool_passes_through():
    """Unknown tool names are not caught by validation — dispatch layer handles them."""
    validate_tool_args("non_existent_tool", {})
    assert validate_or_error("non_existent_tool", {}) is None


def test_type_mismatch():
    """query_project expects query as string."""
    with pytest.raises(SchemaValidationError, match="expected string"):
        validate_tool_args("query_project", {"query": 42})


def test_all_schemas_valid():
    """Every schema can be validated with the tool's own schema rules."""
    from open_edit.kernel.tool_schemas import TOOL_SCHEMAS
    for t in TOOL_SCHEMAS:
        name = t["name"]
        props = t["input_schema"].get("properties", {})
        required = t["input_schema"].get("required", [])
        # Build minimal valid args
        args = {}
        if name == "edit_project":
            args["operation"] = "add_clip"
        for field in required:
            prop = props[field]
            ptype = prop.get("type", "string")
            if ptype == "string":
                args[field] = prop.get("enum", ["test_value"])[0]
            elif ptype == "integer":
                args[field] = 1
            elif ptype == "number":
                args[field] = 1.0
            elif ptype == "boolean":
                args[field] = False
            elif ptype == "object":
                args[field] = {}
            elif ptype == "array":
                args[field] = []
            else:
                args[field] = None
        # Should validate without error
        try:
            validate_tool_args(name, args)
        except SchemaValidationError as e:
            pytest.fail(f"{name}: {e}")
