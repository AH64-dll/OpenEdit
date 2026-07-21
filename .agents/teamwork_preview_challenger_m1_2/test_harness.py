"""Empirical test harness for Pydantic schema validation & serialization round-tripping.
Tests all 10 operation types:
AddClipOp, RemoveClipOp, MoveClipOp, TrimClipOp, AddTransitionOp,
AddEffectOp, SetKeyframeOp, GroupEditsOp, RawMltXmlOp, FreeFormCodeOp
"""
import sys
import json
import math
from typing import Any, Dict, List
from pydantic import TypeAdapter, ValidationError

from open_edit.ir.types import (
    OperationUnion,
    AddClipOp,
    RemoveClipOp,
    MoveClipOp,
    TrimClipOp,
    AddTransitionOp,
    AddEffectOp,
    SetKeyframeOp,
    GroupEditsOp,
    RawMltXmlOp,
    FreeFormCodeOp,
    new_id,
)

ta = TypeAdapter(OperationUnion)

results = {
    "boundary_tests": [],
    "roundtrip_tests": [],
    "summary": {"total": 0, "passed": 0, "failed": 0, "issues": []}
}

def log_test(category: str, op_kind: str, test_name: str, passed: bool, detail: str = ""):
    results["summary"]["total"] += 1
    if passed:
        results["summary"]["passed"] += 1
    else:
        results["summary"]["failed"] += 1
        results["summary"]["issues"].append(f"[{category}][{op_kind}] {test_name}: {detail}")
    
    entry = {
        "op_kind": op_kind,
        "test_name": test_name,
        "passed": passed,
        "detail": detail
    }
    results[category].append(entry)
    status_str = "PASS" if passed else "FAIL"
    print(f"[{status_str}] [{category}] [{op_kind}] {test_name} - {detail}")


def run_numeric_boundary_tests():
    print("\n--- RUNNING NUMERIC BOUNDARY TESTS ---")

    # 1. AddClipOp (position_sec, in_point_sec, out_point_sec)
    base_add = dict(author="ai", asset_hash="hash1", track_id="v1", track_kind="video", position_sec=0.0)
    
    # Test valid zero/positive
    try:
        op = AddClipOp(**base_add, in_point_sec=0.0, out_point_sec=10.0)
        log_test("boundary_tests", "AddClipOp", "standard zero/positive floats", True, f"in={op.in_point_sec}, out={op.out_point_sec}")
    except Exception as e:
        log_test("boundary_tests", "AddClipOp", "standard zero/positive floats", False, str(e))

    # Test negative floats at schema level
    try:
        op = AddClipOp(author="ai", asset_hash="hash1", track_id="v1", position_sec=-5.0, in_point_sec=-2.0, out_point_sec=-1.0)
        log_test("boundary_tests", "AddClipOp", "negative floats accepted by Pydantic schema", True, f"Pydantic allows negative floats: pos={op.position_sec}, in={op.in_point_sec}, out={op.out_point_sec}")
    except Exception as e:
        log_test("boundary_tests", "AddClipOp", "negative floats accepted by Pydantic schema", False, str(e))

    # Test out_point_sec < in_point_sec at schema level
    try:
        op = AddClipOp(author="ai", asset_hash="hash1", track_id="v1", position_sec=0.0, in_point_sec=10.0, out_point_sec=5.0)
        log_test("boundary_tests", "AddClipOp", "out_point < in_point allowed by schema", True, f"Schema permits out ({op.out_point_sec}) < in ({op.in_point_sec})")
    except Exception as e:
        log_test("boundary_tests", "AddClipOp", "out_point < in_point allowed by schema", False, str(e))

    # Test NaN and Infinity
    try:
        op = AddClipOp(author="ai", asset_hash="hash1", track_id="v1", position_sec=float('inf'), in_point_sec=float('nan'))
        log_test("boundary_tests", "AddClipOp", "inf and nan handling", True, f"Pydantic schema accepts inf and nan floats: pos={op.position_sec}, in={op.in_point_sec}")
    except Exception as e:
        log_test("boundary_tests", "AddClipOp", "inf and nan handling", False, f"Pydantic rejected inf/nan: {e}")

    # Test string numeric coercion
    try:
        op = AddClipOp(author="ai", asset_hash="hash1", track_id="v1", position_sec="12.5", in_point_sec="1.0")
        log_test("boundary_tests", "AddClipOp", "string float coercion", isinstance(op.position_sec, float) and op.position_sec == 12.5, f"Coerced string '12.5' to float {op.position_sec}")
    except Exception as e:
        log_test("boundary_tests", "AddClipOp", "string float coercion", False, str(e))

    # Test non-numeric string rejection
    try:
        AddClipOp(author="ai", asset_hash="hash1", track_id="v1", position_sec="invalid_float")
        log_test("boundary_tests", "AddClipOp", "invalid float string rejection", False, "Failed to reject invalid string")
    except ValidationError:
        log_test("boundary_tests", "AddClipOp", "invalid float string rejection", True, "Successfully raised ValidationError on non-numeric string")
    except Exception as e:
        log_test("boundary_tests", "AddClipOp", "invalid float string rejection", False, f"Unexpected exception: {type(e).__name__}: {e}")

    # 2. MoveClipOp (new_position_sec)
    try:
        op = MoveClipOp(author="user", clip_id="c1", new_track_id="v2", new_position_sec=0.0)
        log_test("boundary_tests", "MoveClipOp", "zero position", True, f"new_position_sec={op.new_position_sec}")
    except Exception as e:
        log_test("boundary_tests", "MoveClipOp", "zero position", False, str(e))

    try:
        op = MoveClipOp(author="user", clip_id="c1", new_track_id="v2", new_position_sec=-10.5)
        log_test("boundary_tests", "MoveClipOp", "negative position", True, f"Pydantic permits negative pos: {op.new_position_sec}")
    except Exception as e:
        log_test("boundary_tests", "MoveClipOp", "negative position", False, str(e))

    # 3. TrimClipOp (new_in_point_sec, new_out_point_sec)
    try:
        op = TrimClipOp(author="ai", clip_id="c1", new_in_point_sec=5.0, new_out_point_sec=15.0)
        log_test("boundary_tests", "TrimClipOp", "valid range", True, f"in={op.new_in_point_sec}, out={op.new_out_point_sec}")
    except Exception as e:
        log_test("boundary_tests", "TrimClipOp", "valid range", False, str(e))

    try:
        op = TrimClipOp(author="ai", clip_id="c1", new_in_point_sec=20.0, new_out_point_sec=10.0)
        log_test("boundary_tests", "TrimClipOp", "inverted trim range allowed by schema", True, f"Schema permits inverted trim: in={op.new_in_point_sec}, out={op.new_out_point_sec}")
    except Exception as e:
        log_test("boundary_tests", "TrimClipOp", "inverted trim range allowed by schema", False, str(e))

    # 4. AddTransitionOp (duration_sec)
    try:
        op = AddTransitionOp(author="ai", clip_a_id="c1", clip_b_id="c2", transition_type="dissolve", duration_sec=1.5)
        log_test("boundary_tests", "AddTransitionOp", "positive duration", True, f"duration={op.duration_sec}")
    except Exception as e:
        log_test("boundary_tests", "AddTransitionOp", "positive duration", False, str(e))

    try:
        op = AddTransitionOp(author="ai", clip_a_id="c1", clip_b_id="c2", transition_type="fade", duration_sec=-1.0)
        log_test("boundary_tests", "AddTransitionOp", "negative duration allowed by schema", True, f"Schema permits negative duration: {op.duration_sec}")
    except Exception as e:
        log_test("boundary_tests", "AddTransitionOp", "negative duration allowed by schema", False, str(e))

    # 5. SetKeyframeOp (keyframes: list[tuple[float, float, str]])
    try:
        op = SetKeyframeOp(author="ai", effect_id="e1", param="opacity", keyframes=[(0.0, 1.0, "linear"), (2.5, 0.0, "ease")])
        log_test("boundary_tests", "SetKeyframeOp", "valid keyframe tuple list", True, f"keyframes={op.keyframes}")
    except Exception as e:
        log_test("boundary_tests", "SetKeyframeOp", "valid keyframe tuple list", False, str(e))

    # Keyframe invalid tuple size testing (2 elements instead of 3)
    try:
        SetKeyframeOp(author="ai", effect_id="e1", param="opacity", keyframes=[(0.0, 1.0)])
        log_test("boundary_tests", "SetKeyframeOp", "rejects 2-element tuple", False, "Allowed 2-element tuple")
    except ValidationError:
        log_test("boundary_tests", "SetKeyframeOp", "rejects 2-element tuple", True, "Successfully rejected 2-element tuple for tuple[float, float, str]")
    except Exception as e:
        log_test("boundary_tests", "SetKeyframeOp", "rejects 2-element tuple", False, str(e))

    # Keyframe invalid tuple size testing (4 elements instead of 3)
    try:
        SetKeyframeOp(author="ai", effect_id="e1", param="opacity", keyframes=[(0.0, 1.0, "linear", "extra")])
        log_test("boundary_tests", "SetKeyframeOp", "rejects 4-element tuple", False, "Allowed 4-element tuple")
    except ValidationError:
        log_test("boundary_tests", "SetKeyframeOp", "rejects 4-element tuple", True, "Successfully rejected 4-element tuple")
    except Exception as e:
        log_test("boundary_tests", "SetKeyframeOp", "rejects 4-element tuple", False, str(e))

    # Keyframe tuple float bounds
    try:
        op = SetKeyframeOp(author="ai", effect_id="e1", param="opacity", keyframes=[(-1.0, -999.0, "linear")])
        log_test("boundary_tests", "SetKeyframeOp", "negative keyframe time & value", True, f"Keyframes: {op.keyframes}")
    except Exception as e:
        log_test("boundary_tests", "SetKeyframeOp", "negative keyframe time & value", False, str(e))

    # 6. FreeFormCodeOp (timeout_sec: int, mem_mb: int)
    try:
        op = FreeFormCodeOp(author="ai", code="print('hi')", timeout_sec=60, mem_mb=1024)
        log_test("boundary_tests", "FreeFormCodeOp", "standard ints", True, f"timeout={op.timeout_sec}, mem={op.mem_mb}")
    except Exception as e:
        log_test("boundary_tests", "FreeFormCodeOp", "standard ints", False, str(e))

    try:
        op = FreeFormCodeOp(author="ai", code="pass", timeout_sec=-10, mem_mb=-512)
        log_test("boundary_tests", "FreeFormCodeOp", "negative int boundary", True, f"Schema permits negative ints: timeout={op.timeout_sec}, mem={op.mem_mb}")
    except Exception as e:
        log_test("boundary_tests", "FreeFormCodeOp", "negative int boundary", False, str(e))

    # Float passed to int field in FreeFormCodeOp
    try:
        op = FreeFormCodeOp(author="ai", code="pass", timeout_sec=10.7) # type: ignore
        log_test("boundary_tests", "FreeFormCodeOp", "float to int behavior", True, f"Pydantic coerced/rejected float 10.7 to int: {op.timeout_sec}")
    except ValidationError:
        log_test("boundary_tests", "FreeFormCodeOp", "float to int behavior", True, "Pydantic strict int validation rejected float 10.7")
    except Exception as e:
        log_test("boundary_tests", "FreeFormCodeOp", "float to int behavior", False, str(e))


def run_serialization_roundtrip_tests():
    print("\n--- RUNNING SERIALIZATION ROUNDTRIP TESTS ---")

    # Sample operations for all 10 types
    samples: Dict[str, Any] = {
        "AddClipOp": AddClipOp(
            author="ai", asset_hash="a1b2c3d4", track_id="track_v1", track_kind="video",
            position_sec=10.5, in_point_sec=1.0, out_point_sec=15.0
        ),
        "AddClipOp_NoneOutPoint": AddClipOp(
            author="user", asset_hash="a1b2c3d4", track_id="track_a1", track_kind="audio",
            position_sec=0.0, in_point_sec=0.0, out_point_sec=None
        ),
        "RemoveClipOp": RemoveClipOp(
            author="user", clip_id="clip_123"
        ),
        "MoveClipOp": MoveClipOp(
            author="ai", clip_id="clip_123", new_track_id="track_v2", new_position_sec=25.0
        ),
        "TrimClipOp": TrimClipOp(
            author="ai", clip_id="clip_123", new_in_point_sec=2.5, new_out_point_sec=12.0
        ),
        "AddTransitionOp": AddTransitionOp(
            author="ai", clip_a_id="clip_1", clip_b_id="clip_2", transition_type="dissolve", duration_sec=2.0
        ),
        "AddEffectOp": AddEffectOp(
            author="user", target_kind="clip", target_id="clip_1", effect_type="blur", params={"radius": 15, "mode": "gaussian"}
        ),
        "SetKeyframeOp": SetKeyframeOp(
            author="ai", effect_id="eff_99", param="brightness", keyframes=[(0.0, 100.0, "linear"), (3.0, 50.0, "smooth")]
        ),
        "GroupEditsOp": GroupEditsOp(
            author="ai", edit_ids=["e1", "e2", "e3"], label="Intro Sequence"
        ),
        "RawMltXmlOp": RawMltXmlOp(
            author="user", xml="<mlt><producer id='p1'/></mlt>", description="Custom XML producer"
        ),
        "FreeFormCodeOp": FreeFormCodeOp(
            author="ai", code="project.add_clip('h1', 'v1')", timeout_sec=45, mem_mb=1024, label="script_op_1"
        )
    }

    for name, orig_op in samples.items():
        kind = orig_op.kind
        try:
            # Step 1: Serialize using model_dump_json()
            json_str = orig_op.model_dump_json()
            
            # Step 2: Deserialize using TypeAdapter(OperationUnion).validate_json()
            deserialized = ta.validate_json(json_str)

            # Step 3: Check types and equality
            is_same_type = type(deserialized) is type(orig_op)
            
            # Check dict equality
            orig_dict = orig_op.model_dump()
            deser_dict = deserialized.model_dump()
            is_equal = orig_dict == deser_dict

            if is_same_type and is_equal:
                log_test("roundtrip_tests", kind, f"{name} roundtrip", True, "Successfully round-tripped and matched model_dump()")
            else:
                log_test("roundtrip_tests", kind, f"{name} roundtrip", False, f"Mismatch: same_type={is_same_type}, equal={is_equal}. Diff: orig={orig_dict}, deser={deser_dict}")

        except Exception as e:
            log_test("roundtrip_tests", kind, f"{name} roundtrip", False, f"Exception during roundtrip: {type(e).__name__}: {e}")

    # Special Edge Case: Roundtripping JSON string directly (e.g. from network or database)
    raw_json_add_clip = json.dumps({
        "kind": "add_clip",
        "edit_id": new_id(),
        "author": "ai",
        "timestamp": "2026-07-21T00:00:00Z",
        "status": "applied",
        "asset_hash": "abc12345",
        "track_id": "v1",
        "track_kind": "video",
        "position_sec": 0.0,
        "in_point_sec": 0.0,
        "out_point_sec": None,
        "clip_id": new_id()
    })
    
    try:
        deser_op = ta.validate_json(raw_json_add_clip)
        log_test("roundtrip_tests", "AddClipOp", "Raw JSON string via TypeAdapter", isinstance(deser_op, AddClipOp), f"Parsed correctly as {type(deser_op).__name__}")
    except Exception as e:
        log_test("roundtrip_tests", "AddClipOp", "Raw JSON string via TypeAdapter", False, str(e))

    # Invalid discriminator test
    invalid_kind_json = json.dumps({
        "kind": "non_existent_op_type",
        "author": "ai"
    })
    try:
        ta.validate_json(invalid_kind_json)
        log_test("roundtrip_tests", "UnknownOp", "Invalid kind discriminator rejection", False, "Failed to reject invalid kind discriminator")
    except ValidationError:
        log_test("roundtrip_tests", "UnknownOp", "Invalid kind discriminator rejection", True, "Successfully raised ValidationError on invalid kind")
    except Exception as e:
        log_test("roundtrip_tests", "UnknownOp", "Invalid kind discriminator rejection", False, str(e))

if __name__ == "__main__":
    run_numeric_boundary_tests()
    run_serialization_roundtrip_tests()
    
    print("\n================ FINAL RESULTS SUMMARY ================")
    print(f"Total Tests Run: {results['summary']['total']}")
    print(f"Passed: {results['summary']['passed']}")
    print(f"Failed: {results['summary']['failed']}")
    if results['summary']['issues']:
        print("Issues found:")
        for issue in results['summary']['issues']:
            print(f"  - {issue}")
    else:
        print("All tests passed with zero failures!")
