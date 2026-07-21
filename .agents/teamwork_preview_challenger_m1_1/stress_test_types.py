"""Empirical Stress Testing Harness for Open Edit IR Types and OperationUnion.

This script executes thorough tests on:
1. Malformed JSON payloads, missing discriminator kind fields, invalid literal values.
2. Bulk serialization and deserialization performance (1,000, 5,000, 10,000 operations).
3. Type coercion edge cases (strings as floats, booleans as floats, NaN, Inf, negative bounds, keyframe formats).
"""

import sys
import time
import json
import math
import pytest
from typing import Any, Dict, List
from pydantic import TypeAdapter, ValidationError

from open_edit.ir.types import (
    OperationUnion,
    Operation,
    Project,
    AddClipOp,
    RemoveClipOp,
    MoveClipOp,
    TrimClipOp,
    AddTransitionOp,
    RemoveTransitionOp,
    SetTransitionPropertyOp,
    AddEffectOp,
    RemoveEffectOp,
    SetEffectParamOp,
    SetKeyframeOp,
    RemoveKeyframeOp,
    SlipClipOp,
    RippleDeleteClipOp,
    ChangeClipSpeedOp,
    SplitClipOp,
    ReplaceClipSourceOp,
    SetClipSpeedRampOp,
    SetAudioGainOp,
    NormalizeAudioOp,
    GroupEditsOp,
    UngroupEditsOp,
    RawMltXmlOp,
    FreeFormCodeOp,
    Effect,
    Clip,
    Track,
    Timeline,
    Asset,
    WordAlignment,
    new_id,
    now_iso8601,
)

op_adapter = TypeAdapter(OperationUnion)

def test_malformed_json_and_discriminator():
    """Test 1: Malformed JSON, missing discriminator, and invalid literal values."""
    print("\n=== TEST GROUP 1: Malformed JSON & Discriminator Stress Tests ===")

    # 1.1 Non-JSON string syntax
    malformed_json_inputs = [
        "{invalid_json:",
        "",
        "   ",
        "12345",
        "true",
        "[\"just\", \"a\", \"list\"]",
        "\"just a string\"",
        "{\"kind\": \"add_clip\",", # incomplete
    ]
    for raw in malformed_json_inputs:
        with pytest.raises((ValidationError, ValueError)):
            op_adapter.validate_json(raw)

    # 1.2 Missing discriminator field 'kind'
    missing_kind_payloads = [
        {},
        {"author": "ai"},
        {"author": "user", "asset_hash": "abc", "track_id": "v1", "position_sec": 0.0},
        {"kind": None, "author": "ai"},
    ]
    for p in missing_kind_payloads:
        with pytest.raises(ValidationError):
            op_adapter.validate_python(p)

    # 1.3 Unknown or invalid kind literal values
    invalid_kind_payloads = [
        {"kind": "unknown_op", "author": "ai"},
        {"kind": "ADD_CLIP", "author": "ai", "asset_hash": "abc", "track_id": "v1", "position_sec": 0.0}, # uppercase
        {"kind": "add_clip ", "author": "ai", "asset_hash": "abc", "track_id": "v1", "position_sec": 0.0}, # whitespace
        {"kind": 123, "author": "ai"}, # int kind
        {"kind": True, "author": "ai"}, # bool kind
        {"kind": [], "author": "ai"}, # list kind
    ]
    for p in invalid_kind_payloads:
        with pytest.raises(ValidationError):
            op_adapter.validate_python(p)

    # 1.4 Invalid Literals for fields other than kind
    invalid_literal_payloads = [
        # invalid author
        {"kind": "add_clip", "author": "robot", "asset_hash": "abc", "track_id": "v1", "position_sec": 0.0},
        {"kind": "add_clip", "author": "AI", "asset_hash": "abc", "track_id": "v1", "position_sec": 0.0},
        {"kind": "add_clip", "author": "", "asset_hash": "abc", "track_id": "v1", "position_sec": 0.0},
        # invalid status
        {"kind": "add_clip", "author": "ai", "status": "deleted", "asset_hash": "abc", "track_id": "v1", "position_sec": 0.0},
        # invalid track_kind
        {"kind": "add_clip", "author": "ai", "track_kind": "text", "asset_hash": "abc", "track_id": "v1", "position_sec": 0.0},
        # invalid transition_type
        {"kind": "add_transition", "author": "ai", "clip_a_id": "c1", "clip_b_id": "c2", "transition_type": "star_wipe", "duration_sec": 1.0},
        # invalid target_kind in add_effect
        {"kind": "add_effect", "author": "ai", "target_kind": "project", "target_id": "p1", "effect_type": "blur"},
        # invalid target_kind in normalize_audio
        {"kind": "normalize_audio", "author": "ai", "target_kind": "effect", "target_id": "fx1"},
    ]
    for p in invalid_literal_payloads:
        with pytest.raises(ValidationError):
            op_adapter.validate_python(p)


def test_type_coercion_and_edge_cases():
    """Test 2: Type Coercion & Boundary Edge Cases."""
    print("\n=== TEST GROUP 2: Type Coercion & Boundary Edge Cases ===")

    # 2.1 String to Float coercion (Lax vs Strict mode behavior)
    # Valid string float converts to float
    op1 = op_adapter.validate_python({"kind": "add_clip", "author": "ai", "asset_hash": "abc", "track_id": "v1", "position_sec": "12.34"})
    assert isinstance(op1.position_sec, float) and op1.position_sec == 12.34

    # Valid string integer converts to float
    op2 = op_adapter.validate_python({"kind": "add_clip", "author": "ai", "asset_hash": "abc", "track_id": "v1", "position_sec": "100"})
    assert isinstance(op2.position_sec, float) and op2.position_sec == 100.0

    # Non-numeric string is rejected
    with pytest.raises(ValidationError):
        op_adapter.validate_python({"kind": "add_clip", "author": "ai", "asset_hash": "abc", "track_id": "v1", "position_sec": "abc"})

    # Empty string is rejected
    with pytest.raises(ValidationError):
        op_adapter.validate_python({"kind": "add_clip", "author": "ai", "asset_hash": "abc", "track_id": "v1", "position_sec": ""})

    # Booleans coerce to float in lax mode (1.0 / 0.0)
    op3 = op_adapter.validate_python({"kind": "add_clip", "author": "ai", "asset_hash": "abc", "track_id": "v1", "position_sec": True})
    assert op3.position_sec == 1.0

    # 2.2 Special Floats (NaN / Inf): Accepted initially by validate_python/validate_json,
    # BUT serializes to null in JSON, breaking subsequent JSON deserialization round-trip.
    special_floats = ["nan", "inf", "-inf", float("nan"), float("inf"), float("-inf")]
    for sf in special_floats:
        op_sf = op_adapter.validate_python({"kind": "add_clip", "author": "ai", "asset_hash": "abc", "track_id": "v1", "position_sec": sf})
        dumped_json = op_sf.model_dump_json()
        assert '"position_sec":null' in dumped_json
        # Deserializing back from JSON fails because position_sec got turned into null
        with pytest.raises(ValidationError):
            op_adapter.validate_json(dumped_json)

    # 2.3 Semantic edge cases allowed at schema level (validated downstream in ir/validate.py)
    neg_op = op_adapter.validate_python({"kind": "add_clip", "author": "ai", "asset_hash": "abc", "track_id": "v1", "position_sec": -100.0})
    assert neg_op.position_sec == -100.0

    # 2.4 Keyframe data structure checks
    # Missing element in keyframe tuple is rejected
    with pytest.raises(ValidationError):
        op_adapter.validate_python({"kind": "set_keyframe", "author": "ai", "effect_id": "fx1", "param": "gain", "keyframes": [(0.0, 1.0)]})

    # Extra element in keyframe tuple is rejected
    with pytest.raises(ValidationError):
        op_adapter.validate_python({"kind": "set_keyframe", "author": "ai", "effect_id": "fx1", "param": "gain", "keyframes": [(0.0, 1.0, "linear", "extra")]})

    # Valid tuple is accepted
    kf_op = op_adapter.validate_python({"kind": "set_keyframe", "author": "ai", "effect_id": "fx1", "param": "gain", "keyframes": [(0.0, 1.0, "linear")]})
    assert kf_op.keyframes == [(0.0, 1.0, "linear")]


def test_bulk_performance():
    """Test 3: Bulk Serialization & Deserialization Performance (1,000 to 10,000 ops)."""
    print("\n=== TEST GROUP 3: Bulk Serialization & Deserialization Performance ===")
    
    counts = [1000, 5000, 10000]

    for count in counts:
        raw_ops = []
        op_kinds = [
            ("add_clip", {"asset_hash": "hash123", "track_id": "v1", "position_sec": 0.0, "track_kind": "video"}),
            ("move_clip", {"clip_id": "clip_1", "new_track_id": "v2", "new_position_sec": 5.5}),
            ("trim_clip", {"clip_id": "clip_1", "new_in_point_sec": 1.0, "new_out_point_sec": 4.5}),
            ("add_effect", {"target_kind": "clip", "target_id": "clip_1", "effect_type": "brightness", "params": {"val": 1.2}}),
            ("set_audio_gain", {"clip_id": "clip_2", "gain_db": -3.0}),
            ("add_transition", {"clip_a_id": "c1", "clip_b_id": "c2", "transition_type": "dissolve", "duration_sec": 1.0}),
            ("change_clip_speed", {"clip_id": "clip_3", "rate": 1.5}),
            ("split_clip", {"clip_id": "clip_4", "at_sec": 12.0}),
            ("group_edits", {"edit_ids": ["e1", "e2"], "label": "Group 1"}),
            ("normalize_audio", {"target_kind": "track", "target_id": "a1", "target_dbfs": -14.0}),
        ]
        
        for i in range(count):
            kind, extra = op_kinds[i % len(op_kinds)]
            item = {
                "kind": kind,
                "edit_id": f"edit_{i}",
                "author": "ai" if i % 2 == 0 else "user",
                "timestamp": "2026-07-21T07:00:00Z",
                "status": "applied",
                **extra
            }
            raw_ops.append(item)

        # 1. Validation timing
        t0 = time.perf_counter()
        op_objects = [op_adapter.validate_python(item) for item in raw_ops]
        t1 = time.perf_counter()
        py_deserial_time = t1 - t0

        project = Project(name=f"Benchmark Project {count}", edit_graph=op_objects)

        # 2. JSON Serialization
        t2 = time.perf_counter()
        json_data = project.model_dump_json()
        t3 = time.perf_counter()
        json_serial_time = t3 - t2
        json_size_mb = len(json_data.encode('utf-8')) / (1024 * 1024)

        # 3. JSON Deserialization
        t4 = time.perf_counter()
        restored_project = Project.model_validate_json(json_data)
        t5 = time.perf_counter()
        json_deserial_time = t5 - t4

        print(f"  Ops: {count:5d} | JSON: {json_size_mb:.2f} MB | Serial: {json_serial_time*1000:6.2f} ms | Deserial: {json_deserial_time*1000:6.2f} ms")

        assert len(restored_project.edit_graph) == count
        # Ensure deserialization under 1000ms for 10,000 ops
        assert json_deserial_time < 1.0


if __name__ == "__main__":
    test_malformed_json_and_discriminator()
    test_type_coercion_and_edge_cases()
    test_bulk_performance()
    print("\nAll stress tests PASSED successfully!")
