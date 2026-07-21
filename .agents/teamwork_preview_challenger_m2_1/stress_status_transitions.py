"""Stress test 2: Status update transitions ("applied" -> "reverted" -> "superseded") and status filtering in load_all()."""
import os
import sys
import tempfile
from pathlib import Path
import sqlite3

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "open_edit"))

from open_edit.ir.types import AddClipOp, RemoveClipOp
from open_edit.storage.edit_graph import EditGraphStore


def test_status_transitions():
    print("=== Test 2.1: Valid Status Transitions ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "status.db"
        store = EditGraphStore(db_path)

        op = AddClipOp(author="user", asset_hash="h1", track_id="v1", position_sec=0.0)
        store.append(op)

        # Initial status
        ops = store.load_all()
        assert ops[0].status == "applied", f"Expected initial status 'applied', got {ops[0].status}"

        #applied -> reverted
        store.update_status(op.edit_id, "reverted")
        ops = store.load_all()
        assert ops[0].status == "reverted", f"Expected 'reverted', got {ops[0].status}"

        # reverted -> superseded
        store.update_status(op.edit_id, "superseded")
        ops = store.load_all()
        assert ops[0].status == "superseded", f"Expected 'superseded', got {ops[0].status}"

        # superseded -> applied
        store.update_status(op.edit_id, "applied")
        ops = store.load_all()
        assert ops[0].status == "applied", f"Expected 'applied', got {ops[0].status}"

        print("Valid status transitions check: PASSED")


def test_invalid_status_value():
    print("=== Test 2.2: Invalid Status Value (CHECK constraint) ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "invalid_status.db"
        store = EditGraphStore(db_path)

        op = AddClipOp(author="user", asset_hash="h1", track_id="v1", position_sec=0.0)
        store.append(op)

        try:
            store.update_status(op.edit_id, "invalid_status_xyz")
            print("FAILED: update_status allowed invalid status value without error!")
            assert False, "Expected sqlite3.IntegrityError for invalid status value"
        except sqlite3.IntegrityError as e:
            print(f"PASSED: sqlite3.IntegrityError caught as expected: {e}")


def test_update_status_nonexistent_id():
    print("=== Test 2.3: update_status on Non-existent edit_id ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "nonexistent_status.db"
        store = EditGraphStore(db_path)

        # Calling update_status on a non-existent ID
        # Does it raise KeyError/ValueError or silently do nothing?
        store.update_status("non-existent-id", "reverted")
        print("Behavior noted: update_status on non-existent edit_id completes silently with 0 rows updated.")


def test_status_filtering_in_load_all():
    print("=== Test 2.4: Status Filtering in load_all() ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "filter_status.db"
        store = EditGraphStore(db_path)

        op1 = AddClipOp(author="user", asset_hash="h1", track_id="v1", position_sec=0.0)
        op2 = AddClipOp(author="user", asset_hash="h2", track_id="v1", position_sec=1.0)
        op3 = AddClipOp(author="user", asset_hash="h3", track_id="v1", position_sec=2.0)

        store.append(op1)
        store.append(op2)
        store.append(op3)

        store.update_status(op2.edit_id, "reverted")
        store.update_status(op3.edit_id, "superseded")

        # Check if load_all accepts any status filter argument
        try:
            # Attempting load_all(status="applied")
            store.load_all(status="applied")
            print("load_all accepts status argument!")
        except TypeError as e:
            print(f"Observation: load_all() does NOT accept filter arguments (TypeError: {e}).")

        # Check returned ops
        all_ops = store.load_all()
        assert len(all_ops) == 3, f"Expected 3 ops, got {len(all_ops)}"
        statuses = [op.status for op in all_ops]
        assert statuses == ["applied", "reverted", "superseded"], f"Expected ['applied', 'reverted', 'superseded'], got {statuses}"
        print("Observation: load_all() returns ALL operations regardless of status. Consumers must filter manually in Python.")


if __name__ == "__main__":
    test_status_transitions()
    test_invalid_status_value()
    test_update_status_nonexistent_id()
    test_status_filtering_in_load_all()
