"""Tests for the JobLock (in-flight sandbox / render / migration lock)."""
import tempfile
import unittest
from pathlib import Path

from open_edit.storage.edit_graph import EditGraphStore
from open_edit.storage.job_lock import JobLock


class TestJobLock(unittest.TestCase):
    """Unit tests for JobLock."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_try_acquire_returns_job_id(self) -> None:
        store = EditGraphStore(self.tmp_path / "p.db")
        lock = JobLock(store)
        job_id = lock.try_acquire("free_form_python")
        self.assertIsNotNone(job_id)
        self.assertGreater(len(job_id), 0)

    def test_try_acquire_returns_none_when_busy(self) -> None:
        store = EditGraphStore(self.tmp_path / "p.db")
        lock = JobLock(store)
        first = lock.try_acquire("free_form_python")
        self.assertIsNotNone(first)
        second = lock.try_acquire("free_form_python")
        self.assertIsNone(second)

    def test_release_makes_lock_available_again(self) -> None:
        store = EditGraphStore(self.tmp_path / "p.db")
        lock = JobLock(store)
        job_id = lock.try_acquire("free_form_python")
        lock.release(job_id, "completed")
        new_id = lock.try_acquire("free_form_python")
        self.assertIsNotNone(new_id)
        self.assertNotEqual(new_id, job_id)

    def test_release_with_error_marks_failed(self) -> None:
        store = EditGraphStore(self.tmp_path / "p.db")
        lock = JobLock(store)
        job_id = lock.try_acquire("render")
        lock.release(job_id, "failed", error="melt returned non-zero")
        new_id = lock.try_acquire("render")
        self.assertIsNotNone(new_id)

    def test_list_running_returns_only_in_flight_jobs(self) -> None:
        store = EditGraphStore(self.tmp_path / "p.db")
        lock = JobLock(store)
        job_id = lock.try_acquire("free_form_python")
        running = lock.list_running()
        self.assertEqual(len(running), 1)
        self.assertEqual(running[0]["job_id"], job_id)
        self.assertEqual(running[0]["kind"], "free_form_python")
        self.assertEqual(running[0]["status"], "running")
        lock.release(job_id, "completed")
        self.assertEqual(lock.list_running(), [])

    def test_concurrent_acquire_with_different_kinds(self) -> None:
        store = EditGraphStore(self.tmp_path / "p.db")
        lock = JobLock(store)
        job_id = lock.try_acquire("free_form_python")
        second = lock.try_acquire("render")
        self.assertIsNone(second)
        lock.release(job_id, "completed")
        third = lock.try_acquire("render")
        self.assertIsNotNone(third)


if __name__ == "__main__":
    unittest.main()
