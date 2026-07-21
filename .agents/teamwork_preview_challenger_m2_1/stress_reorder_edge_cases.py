"""Stress test 4: Edge cases in reorder() (non-adjacent sequence numbers, invalid edit IDs)."""
import os
import sys
import tempfile
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "open_edit"))

from open_edit.ir.types import AddClipOp
from open_edit.storage.edit_graph import EditGraphStore


def test_reorder_valid_swap():
    print("=== Test 4.1: Valid Swap of Adjacent Ops ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "reorder_valid.db"
        store = EditGraphStore(db_path)

        op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
        op2 = AddClipOp(author="user", asset_hash="b", track_id="v1", position_sec=1.0)
        op3 = AddClipOp(author="user", asset_hash="c", track_id="v1", position_sec=2.0)

        store.append(op1) # seq 0
        store.append(op2) # seq 1
        store.append(op3) # seq 2

        store.reorder(op1.edit_id, op2.edit_id)
        loaded = store.load_all()
        assert [op.asset_hash for op in loaded] == ["b", "a", "c"]
        print("Valid swap check: PASSED")


def test_reorder_same_edit_id():
    print("=== Test 4.2: reorder() with Same Edit ID Twice ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "reorder_same.db"
        store = EditGraphStore(db_path)

        op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
        store.append(op1)

        try:
            store.reorder(op1.edit_id, op1.edit_id)
            assert False, "Expected ValueError when swapping an edit ID with itself"
        except ValueError as e:
            print(f"PASSED: ValueError raised as expected: {e}")


def test_reorder_invalid_edit_ids():
    print("=== Test 4.3: reorder() with Invalid Edit IDs ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "reorder_invalid.db"
        store = EditGraphStore(db_path)

        op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
        store.append(op1)

        # One invalid ID
        try:
            store.reorder(op1.edit_id, "non-existent-id-123")
            assert False, "Expected ValueError for one invalid ID"
        except ValueError as e:
            print(f"PASSED (one invalid ID): ValueError: {e}")

        # Two invalid IDs
        try:
            store.reorder("invalid-id-1", "invalid-id-2")
            assert False, "Expected ValueError for two invalid IDs"
        except ValueError as e:
            print(f"PASSED (two invalid IDs): ValueError: {e}")


def test_reorder_non_adjacent_sequence_numbers():
    print("=== Test 4.4: reorder() with Non-Adjacent Sequence Numbers ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "reorder_non_adj.db"
        store = EditGraphStore(db_path)

        op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
        op2 = AddClipOp(author="user", asset_hash="b", track_id="v1", position_sec=1.0)
        op3 = AddClipOp(author="user", asset_hash="c", track_id="v1", position_sec=2.0)

        store.append(op1) # seq 0
        store.append(op2) # seq 1
        store.append(op3) # seq 2

        try:
            store.reorder(op1.edit_id, op3.edit_id) # gap = 2
            assert False, "Expected ValueError for non-adjacent ops"
        except ValueError as e:
            print(f"PASSED (gap = 2): ValueError: {e}")


def test_reorder_gapped_sequence_numbers():
    print("=== Test 4.5: reorder() with Gapped Sequence Numbers (no intermediate op) ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "reorder_gap_no_op.db"
        store = EditGraphStore(db_path)

        op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
        op2 = AddClipOp(author="user", asset_hash="b", track_id="v1", position_sec=1.0)

        store.append(op1, sequence_num=0)
        store.append(op2, sequence_num=2) # seq 1 is missing/deleted

        try:
            store.reorder(op1.edit_id, op2.edit_id)
            print("Observation: reorder() allowed swapping ops with seq gap 2!")
        except ValueError as e:
            print(f"Observation: reorder() rejected swapping ops because numeric sequence_num difference is {e}")


def test_reorder_duplicate_sequence_numbers():
    print("=== Test 4.6: reorder() with Duplicate Sequence Numbers ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "reorder_dup.db"
        store = EditGraphStore(db_path)

        op1 = AddClipOp(author="user", asset_hash="a", track_id="v1", position_sec=0.0)
        op2 = AddClipOp(author="user", asset_hash="b", track_id="v1", position_sec=1.0)

        store.append(op1, sequence_num=5)
        store.append(op2, sequence_num=5)

        try:
            store.reorder(op1.edit_id, op2.edit_id)
            print("Observation: reorder() succeeded for duplicate seq numbers!")
        except ValueError as e:
            print(f"Observation: reorder() rejected duplicate sequence numbers because abs(seq1 - seq2) == 0 != 1: {e}")


if __name__ == "__main__":
    test_reorder_valid_swap()
    test_reorder_same_edit_id()
    test_reorder_invalid_edit_ids()
    test_reorder_non_adjacent_sequence_numbers()
    test_reorder_gapped_sequence_numbers()
    test_reorder_duplicate_sequence_numbers()
