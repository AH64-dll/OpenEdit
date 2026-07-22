import tempfile
from pathlib import Path
from open_edit.storage.edit_graph import EditGraphStore
from open_edit.storage.job_lock import JobLock


def test_try_acquire_no_race():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "edit_graph.db"
        store = EditGraphStore(db)
        lock1 = JobLock(store)
        lock2 = JobLock(store)

        r1 = lock1.try_acquire("render")
        r2 = lock2.try_acquire("render")

        assert r1 is not None, "First acquire should succeed"
        assert r2 is None, "Second concurrent acquire should fail"


def test_release_allows_new_acquire():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "edit_graph.db"
        store = EditGraphStore(db)
        lock = JobLock(store)

        jid = lock.try_acquire("render")
        assert jid is not None
        lock.release(jid, "completed")
        jid2 = lock.try_acquire("render")
        assert jid2 is not None
