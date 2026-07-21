"""Stress test 3: Concurrent store access on the same SQLite database file."""
import os
import sys
import time
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "open_edit"))

from open_edit.ir.types import AddClipOp
from open_edit.storage.edit_graph import EditGraphStore


def _process_append_worker(db_path_str: str, worker_id: int, count_per_worker: int):
    """Worker function for process-based concurrent appends."""
    store = EditGraphStore(Path(db_path_str))
    inserted_ids = []
    errors = []
    for i in range(count_per_worker):
        try:
            op = AddClipOp(
                author="user",
                asset_hash=f"w{worker_id}_clip{i}",
                track_id="v1",
                position_sec=float(i),
            )
            seq = store.append(op)
            inserted_ids.append((op.edit_id, seq))
        except Exception as e:
            errors.append(f"Worker {worker_id} op {i} error: {type(e).__name__}: {e}")
    return inserted_ids, errors


def test_concurrent_threads_append():
    print("=== Test 3.1: Multi-Threaded Concurrent Appends ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "concurrent_threads.db"
        store = EditGraphStore(db_path)

        num_threads = 10
        ops_per_thread = 20
        total_expected = num_threads * ops_per_thread

        errors = []
        assigned_seqs = []

        def worker(thread_idx: int):
            for i in range(ops_per_thread):
                try:
                    op = AddClipOp(
                        author="user",
                        asset_hash=f"t{thread_idx}_clip{i}",
                        track_id="v1",
                        position_sec=float(i),
                    )
                    seq = store.append(op)
                    assigned_seqs.append(seq)
                except Exception as e:
                    errors.append(f"Thread {thread_idx} error: {type(e).__name__}: {e}")

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, t) for t in range(num_threads)]
            for f in futures:
                f.result()

        print(f"Total appends attempted: {total_expected}")
        print(f"Total errors: {len(errors)}")
        if errors:
            print(f"Sample errors: {errors[:5]}")

        # Check DB rows
        loaded = store.load_all()
        print(f"Total ops loaded from DB: {len(loaded)}")

        # Check for sequence_num duplicates
        with store._conn() as conn:
            cur = conn.execute("SELECT sequence_num, COUNT(*) FROM edits GROUP BY sequence_num HAVING COUNT(*) > 1")
            duplicates = cur.fetchall()
            print(f"Duplicate sequence_num count: {len(duplicates)}")
            if duplicates:
                print(f"Sample duplicate sequence_nums (seq, count): {duplicates[:10]}")


def test_concurrent_processes_append():
    print("=== Test 3.2: Multi-Process Concurrent Appends ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "concurrent_procs.db"
        # Init store first
        store = EditGraphStore(db_path)

        num_processes = 5
        ops_per_proc = 20
        total_expected = num_processes * ops_per_proc

        all_inserted = []
        all_errors = []

        with ProcessPoolExecutor(max_workers=num_processes) as executor:
            futures = [
                executor.submit(_process_append_worker, str(db_path), p, ops_per_proc)
                for p in range(num_processes)
            ]
            for f in as_completed(futures):
                inserted, errors = f.result()
                all_inserted.extend(inserted)
                all_errors.extend(errors)

        print(f"Total appends attempted: {total_expected}")
        print(f"Total process errors: {len(all_errors)}")
        if all_errors:
            print(f"Sample process errors: {all_errors[:5]}")

        loaded = store.load_all()
        print(f"Total ops loaded from DB: {len(loaded)}")

        # Check sequence_num uniqueness
        with store._conn() as conn:
            cur = conn.execute("SELECT sequence_num, COUNT(*) FROM edits GROUP BY sequence_num HAVING COUNT(*) > 1")
            duplicates = cur.fetchall()
            print(f"Duplicate sequence_num count across processes: {len(duplicates)}")
            if duplicates:
                print(f"Sample duplicate sequence_nums: {duplicates[:10]}")


def test_concurrent_read_write():
    print("=== Test 3.3: Concurrent Reads and Writes (WAL Mode Verification) ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "concurrent_rw.db"
        store = EditGraphStore(db_path)

        # Pre-fill 50 ops
        for i in range(50):
            op = AddClipOp(author="user", asset_hash=f"init_{i}", track_id="v1", position_sec=float(i))
            store.append(op)

        read_counts = []
        write_errors = []
        read_errors = []

        stop_flag = False

        def writer():
            nonlocal stop_flag
            for i in range(100):
                try:
                    op = AddClipOp(author="user", asset_hash=f"writer_{i}", track_id="v1", position_sec=float(i))
                    store.append(op)
                    time.sleep(0.001)
                except Exception as e:
                    write_errors.append(str(e))
            stop_flag = True

        def reader():
            while not stop_flag:
                try:
                    ops = store.load_all()
                    read_counts.append(len(ops))
                    time.sleep(0.002)
                except Exception as e:
                    read_errors.append(str(e))

        with ThreadPoolExecutor(max_workers=3) as executor:
            f_w = executor.submit(writer)
            f_r1 = executor.submit(reader)
            f_r2 = executor.submit(reader)
            f_w.result()
            f_r1.result()
            f_r2.result()

        print(f"Writer completed with {len(write_errors)} errors.")
        print(f"Readers completed with {len(read_errors)} errors across {len(read_counts)} read operations.")
        if read_counts:
            print(f"Read operation result sizes range: {min(read_counts)} to {max(read_counts)}")


if __name__ == "__main__":
    test_concurrent_threads_append()
    test_concurrent_processes_append()
    test_concurrent_read_write()
