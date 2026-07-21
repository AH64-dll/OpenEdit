"""Tests for the v1.6 render-job registry pruning (P5).

Background: ``_RENDER_JOBS`` in ``open_edit.serve.app`` is an unbounded
in-memory dict keyed by job_id. Every render registers an entry; the
entry's ``status`` flips to ``complete`` or ``failed`` when the run
finishes, but the entry is never removed. A long-running server
(process for days) would accumulate tens of thousands of dead entries,
and the polling endpoint ``GET /api/projects/{id}/render_jobs/{job_id}``
would have to scan them all on every request.

Fix: prune completed/failed entries older than ``_RENDER_JOB_TTL_S``
on every write. Only terminal states are pruned; queued and running
entries are kept regardless of age so in-flight jobs are never
accidentally GC'd.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from open_edit.serve import app as app_mod  # noqa: E402
from open_edit.serve.app import RenderJobResponse  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_jobs():
    """Wipe the module-level job dict between tests so they're isolated."""
    app_mod._RENDER_JOBS.clear()
    yield
    app_mod._RENDER_JOBS.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_render_jobs_have_created_at_field():
    """Every registered job carries a ``created_at`` timestamp (float)."""
    job = app_mod._register_job("proj", "proxy")
    assert hasattr(job, "created_at"), "RenderJobResponse must expose created_at for pruning"
    assert isinstance(job.created_at, float)


def test_prune_removes_old_terminal_jobs(monkeypatch):
    """Jobs in a terminal state (``complete``/``failed``) older than
    the TTL are removed; everything else stays."""
    # Use a 60-second TTL so we can fake "old" by setting created_at
    # in the past without timing the test.
    monkeypatch.setattr(app_mod, "_RENDER_JOB_TTL_S", 60)
    now = time.time()

    # Plant entries directly so the per-register prune doesn't disturb
    # the test's careful setup.
    def _plant(job_id: str, status: str, age_s: float) -> RenderJobResponse:
        j = RenderJobResponse(
            job_id=job_id,
            project_id="p",
            mode="proxy",
            status=status,
            created_at=now - age_s,
        )
        app_mod._RENDER_JOBS[job_id] = j
        return j

    # Terminal & old → should be pruned.
    old_done = _plant("old-done", "complete", 120)
    old_failed = _plant("old-failed", "failed", 999)

    # Terminal & fresh → kept.
    fresh_done = _plant("fresh-done", "complete", 5)

    # Non-terminal & old → kept (in-flight).
    old_queued = _plant("old-queued", "queued", 999)
    old_running = _plant("old-running", "running", 999)

    assert len(app_mod._RENDER_JOBS) == 5

    removed = app_mod._prune_render_jobs()
    assert removed == 2, f"expected 2 pruned, got {removed}"

    remaining_ids = set(app_mod._RENDER_JOBS.keys())
    assert old_done.job_id not in remaining_ids
    assert old_failed.job_id not in remaining_ids
    assert fresh_done.job_id in remaining_ids
    assert old_queued.job_id in remaining_ids
    assert old_running.job_id in remaining_ids
    assert len(app_mod._RENDER_JOBS) == 3


def test_register_job_triggers_prune(monkeypatch):
    """Every ``_register_job`` write also prunes, so the dict can't
    grow without bound across many renders."""
    monkeypatch.setattr(app_mod, "_RENDER_JOB_TTL_S", 60)
    now = time.time()

    # Plant an old terminal entry; it should be pruned on the next register.
    stale = app_mod._register_job("p", "proxy")
    stale.status = "complete"
    stale.created_at = now - 120
    assert stale.job_id in app_mod._RENDER_JOBS

    # Registering a new job should evict it.
    fresh = app_mod._register_job("p", "proxy")
    assert stale.job_id not in app_mod._RENDER_JOBS
    assert fresh.job_id in app_mod._RENDER_JOBS
    assert len(app_mod._RENDER_JOBS) == 1


def test_bounded_size_under_load(monkeypatch):
    """After N renders where each finishes immediately as a terminal
    entry, the dict size is bounded (≤ 1 in this setup: each new
    register prunes the previous terminal entry)."""
    monkeypatch.setattr(app_mod, "_RENDER_JOB_TTL_S", 0)  # any age counts as stale
    # 100 jobs, each transitions to "complete" before the next is registered.
    for i in range(100):
        j = app_mod._register_job("p", "proxy")
        j.status = "complete"
        # Re-registering prunes, so each new job sees an empty dict at most
        # briefly. We don't sleep; the test is a unit test of the prune
        # contract, not a perf benchmark.
    # Final size: 1 (the last job), because every previous terminal entry
    # was pruned when the next job was registered.
    assert len(app_mod._RENDER_JOBS) == 1


def test_prune_no_op_when_nothing_to_prune():
    """A fresh dict (no terminal entries) is a no-op."""
    j = app_mod._register_job("p", "proxy")
    j.status = "running"
    removed = app_mod._prune_render_jobs()
    assert removed == 0
    assert j.job_id in app_mod._RENDER_JOBS
