"""Tests for the JobLock (in-flight sandbox / render / migration lock)."""
from pathlib import Path

from open_edit.storage.edit_graph import EditGraphStore
from open_edit.storage.job_lock import JobLock


def test_try_acquire_returns_job_id(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    lock = JobLock(store)
    job_id = lock.try_acquire("free_form_python")
    assert job_id is not None
    assert len(job_id) > 0


def test_try_acquire_returns_none_when_busy(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    lock = JobLock(store)
    first = lock.try_acquire("free_form_python")
    assert first is not None
    second = lock.try_acquire("free_form_python")
    assert second is None


def test_release_makes_lock_available_again(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    lock = JobLock(store)
    job_id = lock.try_acquire("free_form_python")
    lock.release(job_id, "completed")
    new_id = lock.try_acquire("free_form_python")
    assert new_id is not None
    assert new_id != job_id


def test_release_with_error_marks_failed(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    lock = JobLock(store)
    job_id = lock.try_acquire("render")
    lock.release(job_id, "failed", error="melt returned non-zero")
    new_id = lock.try_acquire("render")
    assert new_id is not None


def test_list_running_returns_only_in_flight_jobs(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    lock = JobLock(store)
    job_id = lock.try_acquire("free_form_python")
    running = lock.list_running()
    assert len(running) == 1
    assert running[0]["job_id"] == job_id
    assert running[0]["kind"] == "free_form_python"
    assert running[0]["status"] == "running"
    lock.release(job_id, "completed")
    assert lock.list_running() == []


def test_concurrent_acquire_with_different_kinds(tmp_path: Path) -> None:
    store = EditGraphStore(tmp_path / "p.db")
    lock = JobLock(store)
    job_id = lock.try_acquire("free_form_python")
    second = lock.try_acquire("render")
    assert second is None
    lock.release(job_id, "completed")
    third = lock.try_acquire("render")
    assert third is not None
