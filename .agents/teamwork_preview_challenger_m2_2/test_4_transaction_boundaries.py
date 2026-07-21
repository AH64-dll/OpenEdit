#!/usr/bin/env python3
"""Empirical test 4: Transaction safety, schema boundary conditions, foreign keys, and rollbacks.

Tests:
1. Transaction rollback on PRIMARY KEY violation (duplicate edit_id).
2. Verification of sequence_num monotonicity after rolled-back transactions.
3. Foreign key constraint enforcement on parent_id referencing edits(edit_id).
4. CHECK constraint enforcement on status column.
5. Boundary conditions and error handling in reorder() (same ID, missing ID, non-adjacent gap).
"""
import sqlite3
import tempfile
import sys
from pathlib import Path

from open_edit.storage.edit_graph import EditGraphStore
from open_edit.ir.types import (
    AddClipOp,
    TrimClipOp,
    RemoveClipOp,
)


def run_tests():
    print("=== TEST 4: Transaction Safety & Schema Boundary Verification ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "boundary_test.db"
        store = EditGraphStore(db_path)
        
        # Test 1: Foreign Key Enforcement on parent_id
        print("[1/5] Testing Foreign Key constraint on parent_id...")
        # 1a. parent_id = None (NULL) -> Should succeed
        op_valid_parent_none = AddClipOp(
            author="user",
            asset_hash="h1",
            track_id="v1",
            position_sec=0.0,
            parent_id=None,
        )
        seq0 = store.append(op_valid_parent_none)
        assert seq0 == 0
        
        # 1b. parent_id = op_valid_parent_none.edit_id -> Should succeed
        op_valid_parent_exists = TrimClipOp(
            author="ai",
            clip_id=op_valid_parent_none.clip_id,
            new_in_point_sec=1.0,
            new_out_point_sec=3.0,
            parent_id=op_valid_parent_none.edit_id,
        )
        seq1 = store.append(op_valid_parent_exists)
        assert seq1 == 1
        
        # 1c. parent_id = "non_existent_edit_id_9999" -> Should fail due to Foreign Key constraint
        op_invalid_parent = RemoveClipOp(
            author="user",
            clip_id=op_valid_parent_none.clip_id,
            parent_id="non_existent_edit_id_9999",
        )
        
        fk_failed = False
        try:
            store.append(op_invalid_parent)
        except sqlite3.IntegrityError as e:
            fk_failed = True
            print(f"  -> Foreign Key constraint correctly enforced: {e}")
            
        assert fk_failed, "Foreign Key constraint failed to block invalid parent_id!"
        
        # Verify DB state after FK rollback
        loaded = store.load_all()
        assert len(loaded) == 2, f"Expected 2 ops in DB after rollback, found {len(loaded)}"
        print("  -> Passed Foreign Key constraint test.")
        
        # Test 2: Primary Key violation & Sequence Number continuity after rollback
        print("[2/5] Testing Primary Key violation rollback & sequence_num continuity...")
        # Attempt to insert op with duplicate edit_id
        op_duplicate_id = AddClipOp(
            edit_id=op_valid_parent_none.edit_id, # Duplicate!
            author="user",
            asset_hash="h2",
            track_id="v2",
            position_sec=5.0,
        )
        
        pk_failed = False
        try:
            store.append(op_duplicate_id)
        except sqlite3.IntegrityError as e:
            pk_failed = True
            print(f"  -> Primary Key constraint correctly enforced: {e}")
            
        assert pk_failed, "Primary Key constraint failed to block duplicate edit_id!"
        
        # Next valid append should receive sequence_num 2 (not skip or conflict)
        op_next_valid = AddClipOp(
            author="user",
            asset_hash="h3",
            track_id="v1",
            position_sec=10.0,
        )
        seq2 = store.append(op_next_valid)
        assert seq2 == 2, f"Expected sequence_num 2 after rollback, got {seq2}"
        
        loaded_after_pk = store.load_all()
        assert len(loaded_after_pk) == 3
        print("  -> Passed Primary Key rollback & sequence_num continuity test.")
        
        # Test 3: CHECK constraint enforcement on status column
        print("[3/5] Testing CHECK constraint enforcement on status column...")
        # Direct raw execution of invalid status
        check_failed = False
        try:
            with store._conn() as conn:
                conn.execute(
                    "INSERT INTO edits (edit_id, parent_id, kind, author, timestamp, status, sequence_num, payload) "
                    "VALUES ('invalid_status_op', NULL, 'add_clip', 'user', '2026-07-21T00:00:00Z', 'invalid_status_value', 99, '{}')"
                )
        except sqlite3.IntegrityError as e:
            check_failed = True
            print(f"  -> CHECK constraint correctly enforced: {e}")
            
        assert check_failed, "CHECK constraint failed to block invalid status!"
        print("  -> Passed CHECK constraint test.")
        
        # Test 4: Boundary conditions in reorder()
        print("[4/5] Testing reorder() boundary conditions...")
        ops = store.load_all()
        id0 = ops[0].edit_id
        id1 = ops[1].edit_id
        id2 = ops[2].edit_id
        
        # 4a. Same edit_id twice: reorder(id0, id0)
        try:
            store.reorder(id0, id0)
            assert False, "reorder(id0, id0) should have raised ValueError"
        except ValueError as e:
            assert "Both edits must exist" in str(e)
            print(f"  -> reorder duplicate ID rejected: {e}")
            
        # 4b. Non-adjacent edit_ids: reorder(id0, id2) (gap is 2 - 0 = 2)
        try:
            store.reorder(id0, id2)
            assert False, "reorder(id0, id2) non-adjacent should have raised ValueError"
        except ValueError as e:
            assert "Edits must be adjacent to reorder" in str(e)
            print(f"  -> reorder non-adjacent IDs rejected: {e}")
            
        # 4c. Valid adjacent swap: reorder(id0, id1)
        store.reorder(id0, id1)
        swapped_ops = store.load_all()
        assert swapped_ops[0].edit_id == id1
        assert swapped_ops[1].edit_id == id0
        print("  -> reorder adjacent IDs successfully swapped.")
        print("  -> Passed reorder() boundary condition test.")
        
        # Test 5: Verify transaction atomicity under unhandled exceptions
        print("[5/5] Testing contextmanager transaction rollback on exception...")
        try:
            with store._conn() as conn:
                conn.execute(
                    "INSERT INTO edits (edit_id, parent_id, kind, author, timestamp, status, sequence_num, payload) "
                    "VALUES ('temp_id_atomic', NULL, 'add_clip', 'user', '2026-07-21T00:00:00Z', 'applied', 100, '{}')"
                )
                # Intentionally raise an exception mid-transaction
                raise RuntimeError("Simulated internal error before commit")
        except RuntimeError as e:
            print(f"  -> Caught expected error: {e}")
            
        # Verify 'temp_id_atomic' was rolled back and is NOT in DB
        with store._conn() as conn:
            row = conn.execute("SELECT count(*) FROM edits WHERE edit_id = 'temp_id_atomic'").fetchone()
            assert row[0] == 0, "Transaction was NOT rolled back upon exception!"
        print("  -> Passed transaction atomicity test.")
        
    print("\nSUCCESS: Transaction safety and schema boundary conditions empirically verified!")


if __name__ == "__main__":
    try:
        run_tests()
    except Exception as e:
        print(f"\nTEST FAILED: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
