"""Empirical Pytest Suite for Pydantic Schema Boundary Conditions & Roundtripping.

Tests all 10 operation types required by Milestone 1:
1. AddClipOp
2. RemoveClipOp
3. MoveClipOp
4. TrimClipOp
5. AddTransitionOp
6. AddEffectOp
7. SetKeyframeOp
8. GroupEditsOp
9. RawMltXmlOp
10. FreeFormCodeOp
"""

import math
import pytest
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


# ===== 1. NUMERIC FIELD BOUNDARY TESTS =====

class TestNumericBoundaries:

    def test_add_clip_op_numeric_boundaries(self):
        # Valid standard floats
        op = AddClipOp(author="ai", asset_hash="h1", track_id="v1", position_sec=0.0, in_point_sec=0.0, out_point_sec=10.0)
        assert op.position_sec == 0.0
        assert op.in_point_sec == 0.0
        assert op.out_point_sec == 10.0

        # Negative floats accepted at Pydantic schema level (unconstrained float)
        op_neg = AddClipOp(author="ai", asset_hash="h1", track_id="v1", position_sec=-5.0, in_point_sec=-1.0, out_point_sec=-0.5)
        assert op_neg.position_sec == -5.0

        # Inverted range (out_point_sec < in_point_sec) accepted at schema level
        op_inv = AddClipOp(author="ai", asset_hash="h1", track_id="v1", position_sec=0.0, in_point_sec=10.0, out_point_sec=2.0)
        assert op_inv.in_point_sec == 10.0 and op_inv.out_point_sec == 2.0

        # String coercion
        op_str = AddClipOp(author="ai", asset_hash="h1", track_id="v1", position_sec="15.5")
        assert op_str.position_sec == 15.5

        # Rejection of invalid non-numeric string
        with pytest.raises(ValidationError):
            AddClipOp(author="ai", asset_hash="h1", track_id="v1", position_sec="not_a_number")

    def test_move_clip_op_numeric_boundaries(self):
        op = MoveClipOp(author="user", clip_id="c1", new_track_id="v2", new_position_sec=0.0)
        assert op.new_position_sec == 0.0

        op_neg = MoveClipOp(author="user", clip_id="c1", new_track_id="v2", new_position_sec=-12.5)
        assert op_neg.new_position_sec == -12.5

    def test_trim_clip_op_numeric_boundaries(self):
        op = TrimClipOp(author="ai", clip_id="c1", new_in_point_sec=5.0, new_out_point_sec=15.0)
        assert op.new_in_point_sec == 5.0 and op.new_out_point_sec == 15.0

        # Inverted trim range allowed by Pydantic schema
        op_inv = TrimClipOp(author="ai", clip_id="c1", new_in_point_sec=20.0, new_out_point_sec=10.0)
        assert op_inv.new_in_point_sec == 20.0 and op_inv.new_out_point_sec == 10.0

    def test_add_transition_op_numeric_boundaries(self):
        op = AddTransitionOp(author="ai", clip_a_id="c1", clip_b_id="c2", transition_type="dissolve", duration_sec=1.5)
        assert op.duration_sec == 1.5

        # Invalid transition_type literal rejected
        with pytest.raises(ValidationError):
            AddTransitionOp(author="ai", clip_a_id="c1", clip_b_id="c2", transition_type="invalid_type", duration_sec=1.0) # type: ignore

    def test_set_keyframe_op_tuple_boundaries(self):
        # Valid keyframe tuple list (3-element tuples)
        op = SetKeyframeOp(author="ai", effect_id="e1", param="opacity", keyframes=[(0.0, 1.0, "linear"), (5.0, 0.0, "ease")])
        assert len(op.keyframes) == 2
        assert op.keyframes[0] == (0.0, 1.0, "linear")

        # Rejects 2-element tuple
        with pytest.raises(ValidationError):
            SetKeyframeOp(author="ai", effect_id="e1", param="opacity", keyframes=[(0.0, 1.0)]) # type: ignore

        # Rejects 4-element tuple
        with pytest.raises(ValidationError):
            SetKeyframeOp(author="ai", effect_id="e1", param="opacity", keyframes=[(0.0, 1.0, "linear", "extra")]) # type: ignore

    def test_free_form_code_op_int_boundaries(self):
        op = FreeFormCodeOp(author="ai", code="x=1", timeout_sec=60, mem_mb=1024)
        assert op.timeout_sec == 60 and op.mem_mb == 1024

        # Coercion from string int and whole float
        op_coerced = FreeFormCodeOp(author="ai", code="x=1", timeout_sec="45", mem_mb=512.0) # type: ignore
        assert op_coerced.timeout_sec == 45 and op_coerced.mem_mb == 512

        # Rejection of float with fractional component for int field
        with pytest.raises(ValidationError):
            FreeFormCodeOp(author="ai", code="x=1", timeout_sec=12.7) # type: ignore


# ===== 2. SERIALIZATION ROUND-TRIPPING TESTS =====

class TestSerializationRoundtrip:

    @pytest.mark.parametrize("op_instance", [
        AddClipOp(author="ai", asset_hash="hash_1", track_id="v1", track_kind="video", position_sec=10.0, in_point_sec=1.0, out_point_sec=20.0),
        AddClipOp(author="user", asset_hash="hash_2", track_id="a1", track_kind="audio", position_sec=0.0, in_point_sec=0.0, out_point_sec=None),
        RemoveClipOp(author="user", clip_id="clip_abc"),
        MoveClipOp(author="ai", clip_id="clip_abc", new_track_id="v2", new_position_sec=15.0),
        TrimClipOp(author="ai", clip_id="clip_abc", new_in_point_sec=2.0, new_out_point_sec=18.0),
        AddTransitionOp(author="ai", clip_a_id="c1", clip_b_id="c2", transition_type="dissolve", duration_sec=2.5),
        AddEffectOp(author="user", target_kind="clip", target_id="c1", effect_type="brightness", params={"factor": 1.2}),
        SetKeyframeOp(author="ai", effect_id="eff_1", param="blur", keyframes=[(0.0, 0.0, "linear"), (2.0, 10.0, "smooth")]),
        GroupEditsOp(author="ai", edit_ids=["e1", "e2"], label="Group 1"),
        RawMltXmlOp(author="user", xml="<mlt/>", description="Raw XML op"),
        FreeFormCodeOp(author="ai", code="print('hello')", timeout_sec=30, mem_mb=512, label="freeform_1"),
    ])
    def test_roundtrip_all_10_ops(self, op_instance):
        json_repr = op_instance.model_dump_json()
        deserialized = ta.validate_json(json_repr)
        
        assert type(deserialized) is type(op_instance)
        assert deserialized.model_dump() == op_instance.model_dump()

    def test_float_inf_nan_roundtrip_limitation(self):
        """Document empirical finding: Pydantic model_dump_json() serializes float('inf') as null,

        causing validate_json() to fail for required float fields.
        """
        op_inf = AddClipOp(author="ai", asset_hash="h1", track_id="v1", position_sec=float("inf"))
        json_str = op_inf.model_dump_json()
        assert '"position_sec":null' in json_str

        with pytest.raises(ValidationError) as excinfo:
            ta.validate_json(json_str)
        assert "Input should be a valid number" in str(excinfo.value)
