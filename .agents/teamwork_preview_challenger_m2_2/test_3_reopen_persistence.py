#!/usr/bin/env python3
"""Empirical test 3: Database reopen persistence of project_id and edit logs across multiple instances.

Tests:
1. Persistence of project_id across sequential database reopens.
2. Persistence of edit log (operations, sequence order, updated statuses) across reopens.
3. Concurrent WAL read/write access between two active EditGraphStore instances on the same DB file.
4. Project isolation across separate DB files (distinct project_ids and distinct edit logs).
"""
import tempfile
import sys
from pathlib import Path

from open_edit.storage.edit_graph import EditGraphStore
from open_edit.ir.types import (
    AddClipOp,
    TrimClipOp,
    GroupEditsOp,
)


def run_tests():
    print("=== TEST 3: Database Reopen Persistence Verification ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "persistent_edit_graph.db"
        
        # Phase 1: Initial Instance - Append Ops and get project_id
        print("[1/4] Creating Store Instance 1, generating project_id and initial edits...")
        store1 = EditGraphStore(db_path)
        pid_inst1 = store1.project_id
        print(f"  -> Generated project_id: {pid_inst1}")
        
        op1 = AddClipOp(author="user", asset_hash="h1", track_id="v1", position_sec=0.0)
        op2 = TrimClipOp(author="ai", clip_id=op1.clip_id, new_in_point_sec=1.0, new_out_point_sec=5.0)
        
        seq1 = store1.append(op1)
        seq2 = store1.append(op2)
        store1.update_status(op1.edit_id, "reverted")
        
        ops_inst1 = store1.load_all()
        assert len(ops_inst1) == 2
        assert ops_inst1[0].status == "reverted"
        
        # Destroy store1 reference
        del store1
        
        # Phase 2: Sequential Reopen - Instance 2
        print("[2/4] Reopening DB with Store Instance 2...")
        store2 = EditGraphStore(db_path)
        pid_inst2 = store2.project_id
        print(f"  -> Read project_id: {pid_inst2}")
        assert pid_inst2 == pid_inst1, f"project_id changed across reopen! Expected {pid_inst1}, got {pid_inst2}"
        
        ops_inst2 = store2.load_all()
        assert len(ops_inst2) == 2, f"Expected 2 operations, got {len(ops_inst2)}"
        assert ops_inst2[0].edit_id == op1.edit_id
        assert ops_inst2[0].status == "reverted"
        assert ops_inst2[1].edit_id == op2.edit_id
        
        # Append 3rd op in store2
        op3 = GroupEditsOp(author="user", edit_ids=[op1.edit_id, op2.edit_id], label="Group 1")
        seq3 = store2.append(op3)
        assert seq3 == 2, f"Expected sequence_num 2, got {seq3}"
        
        del store2
        
        # Phase 3: Sequential Reopen - Instance 3
        print("[3/4] Reopening DB with Store Instance 3...")
        store3 = EditGraphStore(db_path)
        assert store3.project_id == pid_inst1
        ops_inst3 = store3.load_all()
        assert len(ops_inst3) == 3
        assert ops_inst3[2].edit_id == op3.edit_id
        assert ops_inst3[2].label == "Group 1"
        
        # Phase 4: Concurrent Instances & Project Isolation
        print("[4/4] Testing concurrent connections on same DB and project isolation on separate DB...")
        conn_a = EditGraphStore(db_path)
        conn_b = EditGraphStore(db_path)
        
        assert conn_a.project_id == conn_b.project_id == pid_inst1
        
        op4 = AddClipOp(author="ai", asset_hash="h2", track_id="a1", position_sec=10.0)
        conn_a.append(op4)
        
        # Immediate read from conn_b
        loaded_b = conn_b.load_all()
        assert len(loaded_b) == 4, f"Concurrent read failed: conn_b saw {len(loaded_b)} ops instead of 4"
        assert loaded_b[3].edit_id == op4.edit_id
        
        # Distinct DB isolation
        db_path_other = Path(tmpdir) / "isolated_edit_graph.db"
        store_other = EditGraphStore(db_path_other)
        pid_other = store_other.project_id
        assert pid_other != pid_inst1, f"Project IDs collided! {pid_other} == {pid_inst1}"
        assert len(store_other.load_all()) == 0
        
    print("\nSUCCESS: Database reopen persistence and project_id stability empirically verified!")


if __name__ == "__main__":
    try:
        run_tests()
    except Exception as e:
        print(f"\nTEST FAILED: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
