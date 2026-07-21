"""Stress test 1: Bulk operation insertion performance (1000+ ops) and sequence numbering."""
import os
import sys
import time
import tempfile
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "open_edit"))

from open_edit.ir.types import AddClipOp, RemoveClipOp, TrimClipOp
from open_edit.storage.edit_graph import EditGraphStore


def test_bulk_insertion_1000():
    print("=== Test 1.1: Bulk Insertion of 1000 operations ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "bulk_test.db"
        store = EditGraphStore(db_path)

        start_time = time.perf_counter()
        count = 1000
        seq_nums = []
        for i in range(count):
            op = AddClipOp(
                author="user",
                asset_hash=f"hash_{i}",
                track_id="v1",
                position_sec=float(i),
            )
            seq = store.append(op)
            seq_nums.append(seq)
        end_time = time.perf_counter()

        duration = end_time - start_time
        ops_per_sec = count / duration
        print(f"Inserted {count} ops in {duration:.4f}s ({ops_per_sec:.2f} ops/sec)")

        # Verify sequence numbers
        expected_seqs = list(range(count))
        assert seq_nums == expected_seqs, f"Sequence numbers mismatch! Expected 0..{count-1}, got {seq_nums[:5]}...{seq_nums[-5:]}"

        # Verify load_all() length and sequence order
        loaded = store.load_all()
        assert len(loaded) == count, f"Expected {count} loaded ops, got {len(loaded)}"
        for idx, op in enumerate(loaded):
            assert op.asset_hash == f"hash_{idx}", f"Mismatch at index {idx}: expected hash_{idx}, got {op.asset_hash}"

        print("Bulk 1000 insertion check: PASSED")


def test_custom_sequence_numbering():
    print("=== Test 1.2: Custom and Non-Sequential Sequence Numbering ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "custom_seq.db"
        store = EditGraphStore(db_path)

        # Append with explicit sequence_num
        op1 = AddClipOp(author="user", asset_hash="h1", track_id="v1", position_sec=0.0)
        seq1 = store.append(op1, sequence_num=100)
        assert seq1 == 100

        # Append next op without sequence_num (should derive MAX(sequence_num) + 1 = 101)
        op2 = AddClipOp(author="user", asset_hash="h2", track_id="v1", position_sec=1.0)
        seq2 = store.append(op2)
        assert seq2 == 101, f"Expected seq 101 after seq 100, got {seq2}"

        # Append explicit gap/out-of-order sequence_num
        op3 = AddClipOp(author="user", asset_hash="h3", track_id="v1", position_sec=2.0)
        seq3 = store.append(op3, sequence_num=50)
        assert seq3 == 50

        # Append without explicit sequence_num now (MAX sequence_num is 101, so next is 102)
        op4 = AddClipOp(author="user", asset_hash="h4", track_id="v1", position_sec=3.0)
        seq4 = store.append(op4)
        assert seq4 == 102, f"Expected 102, got {seq4}"

        # Verify load_all() returns ops ordered by sequence_num (50, 100, 101, 102)
        loaded = store.load_all()
        loaded_hashes = [op.asset_hash for op in loaded]
        assert loaded_hashes == ["h3", "h1", "h2", "h4"], f"Expected ['h3', 'h1', 'h2', 'h4'], got {loaded_hashes}"

        print("Custom sequence numbering check: PASSED")


def test_duplicate_explicit_sequence_numbering():
    print("=== Test 1.3: Duplicate Explicit Sequence Numbers ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "dup_seq.db"
        store = EditGraphStore(db_path)

        op1 = AddClipOp(author="user", asset_hash="h1", track_id="v1", position_sec=0.0)
        store.append(op1, sequence_num=10)

        op2 = AddClipOp(author="user", asset_hash="h2", track_id="v1", position_sec=1.0)
        # Manually append with same sequence_num=10
        store.append(op2, sequence_num=10)

        loaded = store.load_all()
        print(f"Loaded ops count with duplicate sequence_num: {len(loaded)}")

        # Check DB directly
        with store._conn() as conn:
            cur = conn.execute("SELECT edit_id, sequence_num FROM edits WHERE sequence_num = 10")
            rows = cur.fetchall()
            print(f"Rows with sequence_num=10: {len(rows)}")
            assert len(rows) == 2, "Both ops were inserted with identical sequence_num=10 because sequence_num is not UNIQUE!"

        print("Duplicate sequence numbering behavior observed (No UNIQUE constraint on sequence_num).")


if __name__ == "__main__":
    test_bulk_insertion_1000()
    test_custom_sequence_numbering()
    test_duplicate_explicit_sequence_numbering()
