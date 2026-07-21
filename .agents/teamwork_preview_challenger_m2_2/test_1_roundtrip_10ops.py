#!/usr/bin/env python3
"""Empirical test 1: Round-trip payload fidelity for all 10 operation types in EditGraphStore.

Operation types tested:
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
import tempfile
import sys
from pathlib import Path

from open_edit.storage.edit_graph import EditGraphStore
from open_edit.ir.types import (
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


def run_tests():
    print("=== TEST 1: Round-Trip Payload Fidelity for 10 Op Types ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_10ops.db"
        store = EditGraphStore(db_path)
        
        # Prepare 10 concrete operations with varied and complex data
        op1 = AddClipOp(
            author="user",
            asset_hash="abc123hash_video_test",
            track_id="track_v1",
            track_kind="video",
            position_sec=12.5,
            in_point_sec=1.0,
            out_point_sec=15.5,
            originating_note_id="note_999",
        )
        
        op2 = RemoveClipOp(
            author="ai",
            clip_id=op1.clip_id,
            parent_id=op1.edit_id,
        )
        
        op3 = MoveClipOp(
            author="user",
            clip_id="clip_move_1",
            new_track_id="track_v2",
            new_position_sec=45.25,
        )
        
        op4 = TrimClipOp(
            author="ai",
            clip_id="clip_trim_1",
            new_in_point_sec=2.5,
            new_out_point_sec=10.0,
        )
        
        op5 = AddTransitionOp(
            author="user",
            clip_a_id="clip_a",
            clip_b_id="clip_b",
            transition_type="dissolve",
            duration_sec=1.5,
        )
        
        op6 = AddEffectOp(
            author="ai",
            target_kind="clip",
            target_id="clip_eff_1",
            effect_type="color_grading",
            params={
                "brightness": 1.2,
                "contrast": 0.9,
                "lookup_table": "cinematic_v1.cube",
                "nested_config": {"enabled": True, "channels": [1, 2, 3]},
                "special_chars": "Quote: ' Double: \" Slash: \\ Unicode: 🎬 MLT: <property name=\"k\">v</property>",
            },
        )
        
        op7 = SetKeyframeOp(
            author="user",
            effect_id=op6.effect_id,
            param="brightness",
            keyframes=[
                (0.0, 1.0, "linear"),
                (2.5, 1.5, "smooth"),
                (5.0, 0.8, "discrete"),
            ],
        )
        
        op8 = GroupEditsOp(
            author="ai",
            edit_ids=[op1.edit_id, op2.edit_id, op3.edit_id],
            label="Batch edit for scene cut",
        )
        
        op9 = RawMltXmlOp(
            author="user",
            xml="""<mlt version="7.0">
  <playlist id="main">
    <entry producer="prod1" in="0" out="100"/>
  </playlist>
</mlt>""",
            description="Raw XML injection test string with <tags> & 'quotes'",
        )
        
        op10 = FreeFormCodeOp(
            author="ai",
            code="""def apply_effect(timeline):\n    for track in timeline.tracks:\n        print(f"Processing track {track.track_id}")\n""",
            timeout_sec=45,
            mem_mb=1024,
            label="Python automation code block",
        )
        
        all_ops = [op1, op2, op3, op4, op5, op6, op7, op8, op9, op10]
        
        # Append each op sequentially
        seq_nums = []
        for op in all_ops:
            seq = store.append(op)
            seq_nums.append(seq)
            
        print(f"Appended {len(all_ops)} operations. Sequence numbers: {seq_nums}")
        assert seq_nums == list(range(10)), f"Sequence numbers mismatch: {seq_nums}"
        
        # Load all operations from store
        loaded_ops = store.load_all()
        print(f"Loaded {len(loaded_ops)} operations from DB.")
        assert len(loaded_ops) == 10, f"Expected 10 operations, got {len(loaded_ops)}"
        
        # Verify fidelity for every operation
        for i, (orig, loaded) in enumerate(zip(all_ops, loaded_ops)):
            print(f"Checking op {i+1}: kind={orig.kind}, edit_id={orig.edit_id}")
            assert type(orig) is type(loaded), f"Type mismatch at {i}: {type(orig)} vs {type(loaded)}"
            assert orig.edit_id == loaded.edit_id, f"edit_id mismatch at {i}"
            assert orig.author == loaded.author, f"author mismatch at {i}"
            assert orig.kind == loaded.kind, f"kind mismatch at {i}"
            assert orig.status == loaded.status, f"status mismatch at {i}"
            assert orig.timestamp == loaded.timestamp, f"timestamp mismatch at {i}"
            
            # Compare model dump dicts
            orig_dict = orig.model_dump()
            loaded_dict = loaded.model_dump()
            assert orig_dict == loaded_dict, f"Model dump discrepancy at op {i+1} ({orig.kind}):\nOrig:   {orig_dict}\nLoaded: {loaded_dict}"
            
        print("\nSUCCESS: All 10 operation types demonstrated exact 100% round-trip fidelity!")


if __name__ == "__main__":
    try:
        run_tests()
    except Exception as e:
        print(f"\nTEST FAILED: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
