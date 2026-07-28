"""Hand-rolled schema validation for Open Edit tool arguments.

Validates tool arguments against the schemas in tool_schemas.py.
Does NOT depend on the ``jsonschema`` library — the schemas
are simple enough that a fast hand-rolled check suffices.
"""
from __future__ import annotations

from typing import Any

from .tool_schemas import TOOL_BY_NAME


class SchemaValidationError(ValueError):
    """Raised when tool arguments don't match the schema."""


_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "object": dict,
    "array": list,
}


def _check_type(value: Any, expected_type: str, path: str) -> None:
    """Check that ``value`` matches ``expected_type``.

    ``number`` accepts both ``int`` and ``float`` (JSON Schema convention).
    """
    expected = _TYPE_MAP.get(expected_type)
    if expected is None:
        return  # unknown type — skip (lenient)
    if expected_type == "number":
        if not isinstance(value, (int, float)):
            raise SchemaValidationError(
                f"{path}: expected number, got {type(value).__name__}"
            )
    elif not isinstance(value, expected):
        raise SchemaValidationError(
            f"{path}: expected {expected_type}, got {type(value).__name__}"
        )


def validate_tool_args(name: str, args: dict[str, Any]) -> None:
    """Validate ``args`` against the schema for ``name``.

    Raises ``SchemaValidationError`` on the first mismatch.

    Checks:
    - Tool exists
    - ``additionalProperties: false`` → no unknown keys
    - Required fields present
    - Type matches (simple, no deep recursion)
    """
    schema = TOOL_BY_NAME.get(name)
    if schema is None:
        return  # unknown tool — dispatch layer handles this with ToolNotFound

    input_schema = schema["input_schema"]
    props = input_schema.get("properties", {})
    required = input_schema.get("required", [])
    additional = input_schema.get("additionalProperties", True)

    # 1. Required fields
    for field in required:
        if field not in args:
            raise SchemaValidationError(
                f"{name}: missing required field {field!r}"
            )

    # 2. No extra fields (additionalProperties: false)
    if additional is False:
        for key in args:
            if key not in props:
                raise SchemaValidationError(
                    f"{name}: unexpected field {key!r} (additionalProperties: false)"
                )

    # 3. Type checks
    for key, value in args.items():
        prop_schema = props.get(key)
        if prop_schema is None:
            continue
        expected_type = prop_schema.get("type")
        if expected_type:
            _check_type(value, expected_type, f"{name}.{key}")


def validate_or_error(name: str, args: dict[str, Any]) -> dict[str, Any] | None:
    """Return an error dict if validation fails, or None if valid."""
    try:
        validate_tool_args(name, args)
    except SchemaValidationError as exc:
        return {
            "status": "error",
            "error": "schema_validation_failed",
            "detail": str(exc),
        }
    return None
