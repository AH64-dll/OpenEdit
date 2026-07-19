"""Tests for phase2_project_engine._keyframes — animation string parse/serialize."""
from __future__ import annotations

import pytest

from phase2_project_engine._keyframes import (
    Keyframe,
    parse_animation_string,
    serialize_keyframes,
    is_keyframable_param,
    coerce_param_value,
    CURVE_LINEAR,
    CURVE_DISCRETE,
    CURVE_HOLD,
    CURVE_SMOOTH,
)


def test_parse_empty_string():
    assert parse_animation_string("") == []


def test_parse_simple_no_curve():
    kfs = parse_animation_string("0=1.0; 25=0.5; 50=0.0")
    assert kfs == [
        Keyframe(frame=0, value="1.0", type=""),
        Keyframe(frame=25, value="0.5", type=""),
        Keyframe(frame=50, value="0.0", type=""),
    ]


def test_parse_with_curve_chars():
    kfs = parse_animation_string("0=1.0; 25~0.5; 50|0.0; 75!1.0")
    assert [k.type for k in kfs] == ["", CURVE_SMOOTH, CURVE_DISCRETE, CURVE_HOLD]


def test_serialize_round_trip():
    kfs = [Keyframe(frame=0, value="1.0", type=""),
           Keyframe(frame=25, value="0.5", type=CURVE_SMOOTH)]
    s = serialize_keyframes(kfs)
    assert s == "0=1.0; 25~0.5"
    # Round-trip back
    assert parse_animation_string(s) == kfs


def test_serialize_empty():
    assert serialize_keyframes([]) == ""


def test_is_keyframable_param_true():
    cat = [
        {"kdenlive_id": "vignette", "parameters": [
            {"name": "opacity", "type": "animated", "keyframes": True},
        ]}
    ]
    assert is_keyframable_param(cat, "vignette", "opacity") is True


def test_is_keyframable_param_simplekeyframe():
    cat = [
        {"kdenlive_id": "rotation_keyframable", "parameters": [
            {"name": "transition.rotate_x", "type": "simplekeyframe",
             "keyframes": "simplekeyframe"},
        ]}
    ]
    assert is_keyframable_param(cat, "rotation_keyframable", "transition.rotate_x") == "simplekeyframe"


def test_is_keyframable_param_false():
    cat = [
        {"kdenlive_id": "sepia", "parameters": [
            {"name": "level", "type": "constant"},  # no keyframes field
        ]}
    ]
    assert is_keyframable_param(cat, "sepia", "level") is False


def test_is_keyframable_param_unknown_effect():
    cat = []
    assert is_keyframable_param(cat, "unknown", "x") is False


def test_coerce_param_value_constant_passthrough():
    # Constant type accepts any string value.
    assert coerce_param_value("constant", "0.5") == "0.5"


def test_coerce_param_value_double_validates():
    # Double type must be a valid float.
    assert coerce_param_value("double", "0.5") == "0.5"
    with pytest.raises(ValueError):
        coerce_param_value("double", "not a number")


def test_coerce_param_value_integer():
    assert coerce_param_value("integer", "42") == "42"
    with pytest.raises(ValueError):
        coerce_param_value("integer", "42.5")
