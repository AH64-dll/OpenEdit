"""Validate JSON argument types and the registry's Pydantic constraints."""
from __future__ import annotations

import math
from typing import Any

from pydantic import ValidationError

from .tool_registry import TOOL_REGISTRY
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
    "null": type(None),
}


def _check_type(value: Any, expected_type: str, path: str) -> None:
    """Check that ``value`` matches ``expected_type``.

    ``number`` accepts both ``int`` and ``float`` (JSON Schema convention).
    """
    expected = _TYPE_MAP.get(expected_type)
    if expected is None:
        return  # unknown type — skip (lenient)
    if expected_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or (isinstance(value, float) and not math.isfinite(value)):
            raise SchemaValidationError(
                f"{path}: expected number, got {type(value).__name__}"
            )
    elif expected_type == "integer":
        # JSON Schema: an ``integer`` value may be serialized as an
        # integral float (e.g. ``30.0``) — accept it, matching the
        # Pydantic-generated schemas' coercion.
        if isinstance(value, bool) or not isinstance(value, (int, float)) or (isinstance(value, float) and (not math.isfinite(value) or not value.is_integer())):
            raise SchemaValidationError(
                f"{path}: expected integer, got {type(value).__name__}"
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
    - JSON types, nested constraints, enums and model-level invariants
    """
    schema = TOOL_BY_NAME.get(name)
    if schema is None:
        return  # unknown tool — dispatch layer handles this with ToolNotFound

    if not isinstance(args, dict):
        raise SchemaValidationError(f"{name}: expected an object of arguments")

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

    # Do not let Pydantic coercion admit JSON strings/bools as numbers, even
    # inside nullable fields or nested preview ranges.
    _check_json_types(args, input_schema, name, input_schema)

    # The registry validates enums, nullable fields, nested ranges and bounds.
    # A shallow JSON type check alone silently accepted invalid operations.
    model = TOOL_REGISTRY.get(name)
    if model is not None:
        try:
            model.model_validate(args)
        except ValidationError as exc:
            errors = exc.errors(include_url=False, include_input=False)
            detail = "; ".join(
                f"{name}.{'.'.join(map(str, error['loc']))}: {error['msg']}"
                for error in errors
            )
            raise SchemaValidationError(detail) from exc


def _check_json_types(value: Any, schema: dict, path: str, root: dict) -> None:
    ref = schema.get("$ref")
    if ref and ref.startswith("#/$defs/"):
        schema = root.get("$defs", {}).get(ref.rsplit("/", 1)[-1], schema)
    alternatives = schema.get("anyOf")
    if alternatives:
        for candidate in alternatives:
            try:
                _check_json_types(value, candidate, path, root)
                return
            except SchemaValidationError:
                continue
        raise SchemaValidationError(f"{path}: value does not match any allowed JSON type")
    expected = schema.get("type")
    if expected:
        _check_type(value, expected, path)
    if isinstance(value, dict):
        for key, item in value.items():
            prop = schema.get("properties", {}).get(key)
            if prop:
                _check_json_types(item, prop, f"{path}.{key}", root)
    elif isinstance(value, list) and schema.get("items"):
        for index, item in enumerate(value):
            _check_json_types(item, schema["items"], f"{path}[{index}]", root)


def validate_or_error(name: str, args: dict[str, Any]) -> dict[str, Any] | None:
    """Return an error dict if validation fails, or None if valid."""
    try:
        validate_tool_args(name, args)
    except SchemaValidationError as exc:
        return {
            "ok": False,
            "status": "error",
            "error": "schema_validation_failed",
            "error_code": "schema_validation_failed",
            "detail": str(exc),
            "expected_keys": [
                key for key, field in TOOL_REGISTRY[name].model_fields.items()
                if field.is_required() and key not in args
            ] if isinstance(args, dict) and name in TOOL_REGISTRY else [],
        }
    return None
